"""
Combined Image Pipeline Worker
Handles both chunking (Image → base64 chunk) and merging (processed chunks → final JSON).
These two stages never run simultaneously for the same document.
"""
import sys
import os
import time
import tempfile
import base64

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from image_processor.storage import DigitalOceanSpaces
from image_processor.queue_client import QueueClient
from image_processor.llm_engine import ModelEngine
from image_processor.extractor import validate_and_parse_json


def handle_chunking(job, queue, storage, engine):
    """Process an image chunking job: download → base64 → infer schema → upload chunk."""
    doc_id = job['doc_id']
    filename = job.get('filename', 'image.jpg')
    _, ext = os.path.splitext(filename)
    if not ext:
        ext = ".jpg"

    print(f"\n[{doc_id}] Starting chunking/preprocessing for {filename}")

    queue.update_status(doc_id, "downloading_image")

    tmp_path = tempfile.mktemp(suffix=ext)
    try:
        storage.download_image_to_file(doc_id, ext, tmp_path)
        file_size = os.path.getsize(tmp_path)
        print(f"[{doc_id}] Downloaded Image to temp file ({file_size} bytes)")

        # Read for base64 (required by LLM vision API)
        with open(tmp_path, "rb") as f:
            b64_str = base64.b64encode(f.read()).decode('utf-8')

        # Mime type
        mime_type = "image/jpeg"
        if ext.lower() == ".png":
            mime_type = "image/png"
        elif ext.lower() == ".webp":
            mime_type = "image/webp"

        image_context = {"mime_type": mime_type, "base64_data": b64_str}

        # Infer Schema
        queue.update_status(doc_id, "inferring_schema")
        print(f"[{doc_id}] Inferring schema...")

        schema_response = engine.infer_schema(image_context)
        schema = validate_and_parse_json(schema_response)

        if not schema:
            print(f"[{doc_id}] Schema inference failed. Retrying...")
            schema_response = engine.infer_schema(image_context)
            schema = validate_and_parse_json(schema_response)

        if not schema:
            print(f"[{doc_id}] Critical: Failed to infer schema.")
            queue.update_status(doc_id, "failed_schema_inference")
            return

        schema_key = storage.save_schema(doc_id, schema)
        print(f"[{doc_id}] Schema saved to {schema_key}")

        # 1 Image = 1 Chunk
        queue.update_status(doc_id, "chunking")
        chunk_key = storage.upload_chunk_file(doc_id, 1, tmp_path, ext)

        del b64_str

    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

    print(f"[{doc_id}] Generated 1 chunk.")

    # Enqueue chunk job
    queue.set_total_chunks(doc_id, 1)
    queue.enqueue_chunk(doc_id=doc_id, chunk_index=1, chunk_path=chunk_key, schema_path=schema_key)
    print(f"[{doc_id}] chunk enqueued.")


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
    storage.delete_source_image(doc_id)
    storage.delete_schema(doc_id)

    queue.update_status(doc_id, "completed")
    print(f"[{doc_id}] DONE.")


def run_pipeline():
    queue = QueueClient()
    storage = DigitalOceanSpaces()
    engine = ModelEngine()

    print("Image Pipeline Worker Started (chunker + merger). Waiting for jobs...")

    while True:
        job = queue.pop_image_job()
        if job:
            try:
                handle_chunking(job, queue, storage, engine)
            except Exception as e:
                print(f"[{job.get('doc_id', '?')}] Error in chunker: {e}")
                import traceback; traceback.print_exc()
                queue.update_status(job.get('doc_id', ''), f"error: {str(e)}")
            continue

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
