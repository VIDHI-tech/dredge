"""
Unified Processor Worker
Polls all 3 chunk queues (PDF, Image, CSV) and processes chunks using the
appropriate pipeline logic. This replaces the 3 separate processor workers.
"""
import sys
import os
import json
import time
import base64
import math

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# --- PDF Processor imports ---
from pdf_processor.storage import DigitalOceanSpaces as PDFStorage
from pdf_processor.queue_client import QueueClient as PDFQueue
from pdf_processor.llm_engine import ModelEngine as PDFEngine
from pdf_processor.extractor import validate_and_parse_json as pdf_validate

# --- Image Processor imports ---
from image_processor.storage import DigitalOceanSpaces as ImageStorage
from image_processor.queue_client import QueueClient as ImageQueue
from image_processor.llm_engine import ModelEngine as ImageEngine
from image_processor.extractor import validate_and_parse_json as image_validate

# --- CSV Processor imports ---
from csv_importer.storage import DigitalOceanSpaces as CSVStorage
from csv_importer.queue_client import QueueClient as CSVQueue

import pandas as pd
import io


def _extract_records(extracted):
    """Common logic to normalize LLM extraction results into a list of records."""
    if extracted is None:
        return []

    if isinstance(extracted, list):
        return extracted
    elif isinstance(extracted, dict):
        if "data" in extracted and isinstance(extracted["data"], list):
            return extracted["data"]
        else:
            # Find the largest nested array-of-dicts
            best_array = []
            for key, val in extracted.items():
                if isinstance(val, list) and len(val) > len(best_array):
                    if val and isinstance(val[0], dict):
                        best_array = val
            if best_array:
                return best_array
            else:
                return [extracted]
    else:
        return [extracted]


def clean_nan(value):
    """Replace NaN/Infinity with None."""
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
    return value


def process_pdf_chunk(job, pdf_queue, pdf_storage, pdf_engine):
    """Process a single PDF chunk: download text → LLM extract → save result."""
    doc_id = job['doc_id']
    chunk_index = job['chunk_index']

    # Schema (with simple cache)
    schema = pdf_storage.get_schema(doc_id)
    if not schema:
        print(f"[PDF {doc_id}] Error: Schema not found!")
        return
    schema_str = json.dumps(schema)

    # Read chunk text
    key = f"raw_chunks/{doc_id}/{chunk_index}.txt"
    try:
        obj = pdf_storage.client.get_object(Bucket=pdf_storage.bucket, Key=key)
        text_chunk = obj['Body'].read().decode('utf-8')
    except Exception as e:
        print(f"[PDF {doc_id}] Error reading chunk {chunk_index}: {e}")
        return

    # LLM extraction
    response = pdf_engine.extract_data(text_chunk, schema_str)
    extracted = pdf_validate(response)
    data_to_save = _extract_records(extracted)
    if not data_to_save:
        print(f"[PDF {doc_id}] Warning: Extraction failed for chunk {chunk_index}")
        data_to_save = []

    # Save
    pdf_storage.save_processed_chunk(doc_id, chunk_index, data_to_save)

    # Progress
    processed_count, total_count = pdf_queue.increment_processed_chunks(doc_id)
    print(f"[PDF {doc_id}] Chunk {chunk_index} done. Progress: {processed_count}/{total_count}")

    if processed_count >= total_count:
        print(f"[PDF {doc_id}] All chunks processed. Enqueuing merge job.")
        pdf_queue.enqueue_merge(doc_id, job['schema_path'])


def process_image_chunk(job, image_queue, image_storage, image_engine):
    """Process a single image chunk: download image → base64 → LLM extract → save."""
    doc_id = job['doc_id']
    chunk_index = job['chunk_index']
    chunk_path = job['chunk_path']

    # Schema
    schema = image_storage.get_schema(doc_id)
    if not schema:
        print(f"[IMG {doc_id}] Error: Schema not found!")
        return
    schema_str = json.dumps(schema)

    # Read image
    try:
        obj = image_storage.client.get_object(Bucket=image_storage.bucket, Key=chunk_path)
        image_bytes = obj['Body'].read()
    except Exception as e:
        print(f"[IMG {doc_id}] Error reading chunk {chunk_path}: {e}")
        return

    b64_str = base64.b64encode(image_bytes).decode('utf-8')
    ext = os.path.splitext(chunk_path)[1].lower()
    mime_type = "image/jpeg"
    if ext == ".png":
        mime_type = "image/png"
    elif ext == ".webp":
        mime_type = "image/webp"

    image_context = {"mime_type": mime_type, "base64_data": b64_str}

    # LLM extraction
    response = image_engine.extract_data(image_context, schema_str)
    extracted = image_validate(response)
    data_to_save = _extract_records(extracted)
    if not data_to_save:
        print(f"[IMG {doc_id}] Warning: Extraction failed for chunk {chunk_index}")
        data_to_save = []

    # Save
    image_storage.save_processed_chunk(doc_id, chunk_index, data_to_save)

    # Progress
    processed_count, total_count = image_queue.increment_processed_chunks(doc_id)
    print(f"[IMG {doc_id}] Chunk {chunk_index} done. Progress: {processed_count}/{total_count}")

    if processed_count >= total_count:
        print(f"[IMG {doc_id}] All chunks processed. Enqueuing merge job.")
        image_queue.enqueue_merge(doc_id, job['schema_path'])


def process_csv_chunk(job, csv_queue, csv_storage):
    """Process a single CSV chunk: download → pandas → clean → save JSON."""
    doc_id = job['doc_id']
    chunk_index = job['chunk_index']
    chunk_path = job['chunk_path']

    # Read chunk
    chunk_bytes = csv_storage.client.get_object(Bucket=csv_storage.bucket, Key=chunk_path)['Body'].read()
    csv_string = chunk_bytes.decode('utf-8')

    # Process with pandas
    df = pd.read_csv(io.StringIO(csv_string))
    records = df.to_dict(orient='records')

    # Clean NaN
    cleaned_records = [{k: clean_nan(v) for k, v in record.items()} for record in records]

    # Save
    csv_storage.save_processed_chunk(doc_id, chunk_index, cleaned_records)

    # Progress
    new_count, total = csv_queue.increment_processed_chunks(doc_id)
    print(f"[CSV {doc_id}] Chunk {chunk_index} done. Progress: {new_count}/{total}")

    if new_count >= total:
        print(f"[CSV {doc_id}] All chunks completed. Enqueuing merge job.")
        csv_queue.enqueue_merge(doc_id)


def run_unified_processor():
    # Initialize all 3 pipelines
    pdf_queue = PDFQueue()
    pdf_storage = PDFStorage()
    pdf_engine = PDFEngine()

    image_queue = ImageQueue()
    image_storage = ImageStorage()
    image_engine = ImageEngine()

    csv_queue = CSVQueue()
    csv_storage = CSVStorage()

    print("Unified Processor Started. Polling PDF, Image, and CSV chunk queues...")

    while True:
        # Round-robin across all 3 chunk queues
        # PDF chunks
        job = pdf_queue.pop_chunk_job()
        if job:
            try:
                process_pdf_chunk(job, pdf_queue, pdf_storage, pdf_engine)
            except Exception as e:
                doc_id = job.get('doc_id', '?')
                print(f"[PDF {doc_id}] Error: {e}")
                import traceback; traceback.print_exc()
            continue

        # Image chunks
        job = image_queue.pop_chunk_job()
        if job:
            try:
                process_image_chunk(job, image_queue, image_storage, image_engine)
            except Exception as e:
                doc_id = job.get('doc_id', '?')
                print(f"[IMG {doc_id}] Error: {e}")
                import traceback; traceback.print_exc()
            continue

        # CSV chunks
        job = csv_queue.pop_chunk_job()
        if job:
            try:
                process_csv_chunk(job, csv_queue, csv_storage)
            except Exception as e:
                doc_id = job.get('doc_id', '?')
                print(f"[CSV {doc_id}] Error: {e}")
                import traceback; traceback.print_exc()
            continue

        time.sleep(0.5)


if __name__ == "__main__":
    run_unified_processor()
