"""
Combined CSV Pipeline Worker
Handles both chunking (CSV → row-based chunks) and merging (processed chunks → final JSON).
These two stages never run simultaneously for the same document.
"""
import sys
import os
import time
import tempfile
import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from csv_importer.storage import DigitalOceanSpaces
from csv_importer.queue_client import QueueClient

CHUNK_SIZE = 10000  # rows per chunk


def handle_chunking(job, queue, storage):
    """Process a CSV chunking job: download CSV → split into row chunks → upload."""
    doc_id = job['doc_id']
    filename = job.get('filename', 'data.csv')

    print(f"\n[{doc_id}] Starting chunking for {filename}")

    queue.update_status(doc_id, "downloading_csv")
    queue.r.hset(f"status:csv:{doc_id}", "phase", "chunking")

    tmp_path = tempfile.mktemp(suffix=".csv")
    try:
        storage.download_csv_to_file(doc_id, tmp_path)
        file_size = os.path.getsize(tmp_path)
        print(f"[{doc_id}] Downloaded CSV to temp file ({file_size} bytes)")

        chunk_idx = 0
        for chunk_df in pd.read_csv(tmp_path, chunksize=CHUNK_SIZE):
            chunk_idx += 1
            chunk_csv_str = chunk_df.to_csv(index=False)
            storage.upload_chunk(doc_id, chunk_idx, chunk_csv_str.encode('utf-8'))
            print(f"[{doc_id}] Uploaded chunk {chunk_idx}")

    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

    print(f"[{doc_id}] Generated {chunk_idx} chunks.")

    # Enqueue chunk jobs
    queue.set_total_chunks(doc_id, chunk_idx)
    for idx in range(1, chunk_idx + 1):
        chunk_path = f"raw_csv_chunks/{doc_id}/{idx}.csv"
        queue.enqueue_chunk(doc_id=doc_id, chunk_index=idx, chunk_path=chunk_path)

    print(f"[{doc_id}] All {chunk_idx} chunk jobs enqueued.")


def handle_merging(job, queue, storage):
    """Process a merge job: assemble processed chunks → final JSON → cleanup."""
    doc_id = job['doc_id']
    print(f"\n[{doc_id}] Starting merge...")

    queue.update_status(doc_id, "merging")

    final_key = storage.stream_assembly_json(doc_id)
    print(f"[{doc_id}] Merged JSON saved to {final_key}")

    # Cleanup
    print(f"[{doc_id}] Cleaning up temporary chunks...")
    storage.delete_chunks(doc_id)
    storage.delete_processed_chunks(doc_id)
    storage.delete_source_csv(doc_id)

    queue.update_status(doc_id, "completed")
    queue.r.hset(f"status:csv:{doc_id}", "phase", "completed")
    print(f"[{doc_id}] DONE.")


def run_pipeline():
    queue = QueueClient()
    storage = DigitalOceanSpaces()

    print("CSV Pipeline Worker Started (chunker + merger). Waiting for jobs...")

    while True:
        job = queue.pop_csv_job()
        if job:
            try:
                handle_chunking(job, queue, storage)
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
