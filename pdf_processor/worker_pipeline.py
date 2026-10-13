"""
Combined PDF Pipeline Worker
Handles both chunking (PDF → text chunks) and merging (processed chunks → final JSON).
These two stages never run simultaneously for the same document.
"""
import sys
import os
import time
import tempfile
import pdfplumber

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pdf_processor.storage import DigitalOceanSpaces
from pdf_processor.queue_client import QueueClient
from pdf_processor.llm_engine import ModelEngine
from pdf_processor.chunker import chunk_text
from pdf_processor.extractor import validate_and_parse_json


def handle_chunking(job, queue, storage, engine):
    """Process a PDF chunking job: download PDF → extract text → chunk → upload."""
    doc_id = job['doc_id']
    filename = job.get('filename', 'document.pdf')
    print(f"\n[{doc_id}] Starting chunking for {filename}")

    queue.update_status(doc_id, "downloading_pdf")

    tmp_path = tempfile.mktemp(suffix=".pdf")
    try:
        storage.download_pdf_to_file(doc_id, tmp_path)
        file_size = os.path.getsize(tmp_path)
        print(f"[{doc_id}] Downloaded PDF to temp file ({file_size} bytes)")

        with pdfplumber.open(tmp_path) as pdf:
            total_pages = len(pdf.pages)

            if total_pages == 0:
                print(f"[{doc_id}] Error: No pages in PDF")
                queue.update_status(doc_id, "failed_no_text")
                return

            # Schema inference from sample pages (first, middle, last)
            sample_indices = {0}
            if total_pages > 2:
                sample_indices.add(total_pages // 2)
            if total_pages > 1:
                sample_indices.add(total_pages - 1)

            queue.update_status(doc_id, "inferring_schema")
            print(f"[{doc_id}] Inferring schema from {len(sample_indices)} sample pages...")

            sample_texts = []
            for idx in sorted(sample_indices):
                text = pdf.pages[idx].extract_text() or ""
                sample_texts.append(text)

            schema_text = "\n\n".join(sample_texts)
            del sample_texts

            schema_response = engine.infer_schema(schema_text)
            schema = validate_and_parse_json(schema_response)

            if not schema:
                print(f"[{doc_id}] Schema inference failed. Retrying...")
                schema_response = engine.infer_schema(schema_text)
                schema = validate_and_parse_json(schema_response)

            del schema_text

            if not schema:
                print(f"[{doc_id}] Critical: Failed to infer schema.")
                queue.update_status(doc_id, "failed_schema_inference")
                return

            schema_key = storage.save_schema(doc_id, schema)
            print(f"[{doc_id}] Schema saved to {schema_key}")

            # Chunk pages incrementally (one page in RAM at a time)
            queue.update_status(doc_id, "chunking")
            chunk_idx = 0
            all_chunks = []

            for page_num, page in enumerate(pdf.pages):
                page_text = page.extract_text() or ""
                if not page_text.strip():
                    continue

                chunks = chunk_text(page_text, chunk_size=3000, overlap=200)

                for text_chunk in chunks:
                    chunk_idx += 1
                    chunk_key = storage.upload_chunk(doc_id, chunk_idx, text_chunk)
                    all_chunks.append({"index": chunk_idx, "key": chunk_key})

            print(f"[{doc_id}] Generated {len(all_chunks)} chunks from {total_pages} pages.")

    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

    if not all_chunks:
        print(f"[{doc_id}] Error: No text extracted from any page")
        queue.update_status(doc_id, "failed_no_text")
        return

    # Enqueue chunk jobs
    queue.set_total_chunks(doc_id, len(all_chunks))
    for chunk_info in all_chunks:
        queue.enqueue_chunk(
            doc_id=doc_id,
            chunk_index=chunk_info['index'],
            chunk_path=chunk_info['key'],
            schema_path=schema_key
        )
    print(f"[{doc_id}] All chunks enqueued.")


def handle_merging(job, queue, storage):
    """Process a merge job: assemble processed chunks → final JSON → cleanup."""
    doc_id = job['doc_id']
    print(f"\n[{doc_id}] Starting merge...")

    queue.update_status(doc_id, "merging")

    schema = storage.get_schema(doc_id)
    if not schema:
        print(f"[{doc_id}] Warning: Schema not found for merge. Using empty.")
        schema = {}

    final_key = storage.stream_assembly_json(doc_id, schema)
    print(f"[{doc_id}] Merged JSON saved to {final_key}")

    # Cleanup S3
    print(f"[{doc_id}] Cleaning up...")
    storage.delete_chunks(doc_id)
    storage.delete_processed_chunks(doc_id)
    storage.delete_source_pdf(doc_id)
    storage.delete_schema(doc_id)

    queue.update_status(doc_id, "completed")
    print(f"[{doc_id}] DONE.")


def run_pipeline():
    queue = QueueClient()
    storage = DigitalOceanSpaces()
    engine = ModelEngine()

    print("PDF Pipeline Worker Started (chunker + merger). Waiting for jobs...")

    while True:
        # Check chunker queue first
        job = queue.pop_pdf_job()
        if job:
            try:
                handle_chunking(job, queue, storage, engine)
            except Exception as e:
                print(f"[{job.get('doc_id', '?')}] Error in chunker: {e}")
                import traceback; traceback.print_exc()
                queue.update_status(job.get('doc_id', ''), f"error: {str(e)}")
            continue

        # Then check merger queue
        job = queue.pop_merge_job()
        if job:
            try:
                handle_merging(job, queue, storage)
            except Exception as e:
                print(f"[{job.get('doc_id', '?')}] Error in merger: {e}")
                import traceback; traceback.print_exc()
                queue.update_status(job.get('doc_id', ''), f"error_merging: {str(e)}")
            continue

        time.sleep(1)


if __name__ == "__main__":
    run_pipeline()
