import json
from dotenv import load_dotenv, find_dotenv

# Load root .env
load_dotenv(find_dotenv())

import os
import boto3
from botocore.exceptions import ClientError
from typing import List, Optional

class DigitalOceanSpaces:
    def __init__(self):
        self.region = os.getenv("DO_SPACES_REGION", "nyc3")
        self.endpoint_url = os.getenv("DO_SPACES_ENDPOINT", f"https://{self.region}.digitaloceanspaces.com")
        self.key_id = os.getenv("DO_SPACES_KEY")
        self.secret_key = os.getenv("DO_SPACES_SECRET")
        self.bucket = os.getenv("DO_SPACES_BUCKET")
        
        if self.bucket and self.bucket in self.endpoint_url:
            self.endpoint_url = self.endpoint_url.replace(f"{self.bucket}.", "")
            
        self.session = boto3.session.Session()
        self.client = self.session.client('s3',
                                          region_name=self.region,
                                          endpoint_url=self.endpoint_url,
                                          aws_access_key_id=self.key_id,
                                          aws_secret_access_key=self.secret_key)
        
        print(f"DEBUG: CSV Storage Configured with Endpoint='{self.endpoint_url}', Bucket='{self.bucket}'")

    def upload_csv(self, doc_id: str, file_content: bytes) -> str:
        """Uploads the raw CSV to Spaces (from bytes — kept for backward compat)."""
        key = f"raw_csvs/{doc_id}.csv"
        try:
            self.client.put_object(Bucket=self.bucket, Key=key, Body=file_content, ACL='private')
            return key
        except ClientError as e:
            print(f"Error uploading CSV for {doc_id}: {e}")
            raise

    def upload_csv_file(self, doc_id: str, file_path: str) -> str:
        """Streams a CSV file from disk to S3 without loading it into RAM."""
        key = f"raw_csvs/{doc_id}.csv"
        try:
            self.client.upload_file(file_path, self.bucket, key, ExtraArgs={'ACL': 'private'})
            return key
        except ClientError as e:
            print(f"Error uploading CSV file for {doc_id}: {e}")
            raise

    def download_csv(self, doc_id: str) -> bytes:
        """Downloads the raw CSV from Spaces (into RAM — kept for backward compat)."""
        key = f"raw_csvs/{doc_id}.csv"
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
            return response['Body'].read()
        except ClientError as e:
            print(f"Error downloading CSV for {doc_id}: {e}")
            raise

    def download_csv_to_file(self, doc_id: str, file_path: str):
        """Streams a CSV from S3 to a local file without loading it into RAM."""
        key = f"raw_csvs/{doc_id}.csv"
        try:
            self.client.download_file(self.bucket, key, file_path)
        except ClientError as e:
            print(f"Error downloading CSV to file for {doc_id}: {e}")
            raise

    def upload_chunk(self, doc_id: str, index: int, chunk_bytes: bytes) -> str:
        """Uploads a raw CSV chunk to Spaces."""
        key = f"raw_csv_chunks/{doc_id}/{index}.csv"
        try:
            self.client.put_object(Bucket=self.bucket, Key=key, Body=chunk_bytes, ACL='private')
            return key
        except ClientError as e:
            print(f"Error uploading chunk {index} for {doc_id}: {e}")
            raise

    def save_processed_chunk(self, doc_id: str, index: int, data: list) -> str:
        """Saves a processed JSON chunk array to Spaces."""
        key = f"processed_csv_chunks/{doc_id}/{index}.json"
        try:
            json_str = json.dumps(data)
            self.client.put_object(Bucket=self.bucket, Key=key, Body=json_str.encode('utf-8'), ContentType='application/json', ACL='private')
            return key
        except ClientError as e:
            print(f"Error saving processed chunk {index} for {doc_id}: {e}")
            raise

    def stream_assembly_json(self, doc_id: str) -> str:
        """Streams all processed chunk arrays into a single final JSON document."""
        final_key = f"processed_csv_json/{doc_id}.json"
        chunk_prefix = f"processed_csv_chunks/{doc_id}/"

        try:
            paginator = self.client.get_paginator('list_objects_v2')
            all_keys = []
            for page in paginator.paginate(Bucket=self.bucket, Prefix=chunk_prefix):
                if 'Contents' in page:
                    for obj in page['Contents']:
                        all_keys.append(obj['Key'])
            
            def get_index(key):
                try:
                    return int(key.split('/')[-1].replace('.json', ''))
                except ValueError:
                    return 999999
            all_keys.sort(key=get_index)
            
            if not all_keys:
                print(f"No processed chunks found for {doc_id} to assemble.")
                return ""

        except ClientError as e:
            print(f"Error listing processed chunks for {doc_id}: {e}")
            raise

        def json_stream_generator():
            # CSV Importer just exposes an array traditionally. We'll wrap it purely as {"data": [ ... ]}
            yield b'{"data": ['
            
            first_chunk = True
            for key in all_keys:
                try:
                    obj = self.client.get_object(Bucket=self.bucket, Key=key)
                    # This yields an array `[{"a": 1}, {"a": 2}]`
                    content_str = obj['Body'].read().decode('utf-8')
                    
                    # We strip the outer brackets to concatenate cleanly
                    inner_array_content = content_str.strip()
                    if inner_array_content.startswith('[') and inner_array_content.endswith(']'):
                        inner_array_content = inner_array_content[1:-1]
                    
                    # If this chunk was somehow empty array "[]", skip the comma logic
                    if inner_array_content:
                        if not first_chunk:
                            yield b","
                        first_chunk = False
                        yield inner_array_content.encode('utf-8')
                        
                except Exception as e:
                    print(f"Error reading chunk {key} during assembly: {e}")
            
            yield b"]}"

        class GeneratorToFile:
            def __init__(self, generator):
                self.generator = generator
                self.buffer = b""
            
            def read(self, size=None):
                while len(self.buffer) < size if size else True:
                    try:
                        chunk = next(self.generator)
                        self.buffer += chunk
                    except StopIteration:
                        break
                    if size and len(self.buffer) >= size:
                        break
                
                if size:
                    data = self.buffer[:size]
                    self.buffer = self.buffer[size:]
                else:
                    data = self.buffer
                    self.buffer = b""
                return data
                
        try:
            print(f"DEBUG: Starting CSV streaming assembly for {doc_id}...")
            self.client.upload_fileobj(
                GeneratorToFile(json_stream_generator()),
                self.bucket,
                final_key,
                ExtraArgs={'ContentType': 'application/json', 'ACL': 'private'}
            )
            print(f"DEBUG: Streaming assembly complete for {final_key}")
            return final_key
        except Exception as e:
            print(f"Error during streaming assembly for {doc_id}: {e}")
            raise

    def delete_chunks(self, doc_id: str):
        """Deletes chunks."""
        prefix = f"raw_csv_chunks/{doc_id}/"
        self._delete_prefix(prefix)

    def delete_processed_chunks(self, doc_id: str):
        prefix = f"processed_csv_chunks/{doc_id}/"
        self._delete_prefix(prefix)

    def _delete_prefix(self, prefix):
        try:
            paginator = self.client.get_paginator('list_objects_v2')
            objects_to_delete = []
            for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
                if 'Contents' in page:
                    for obj in page['Contents']:
                        objects_to_delete.append({'Key': obj['Key']})
            
            if objects_to_delete:
                # AWS delete_objects accepts max 1000 items at once
                for i in range(0, len(objects_to_delete), 1000):
                    batch = objects_to_delete[i:i+1000]
                    self.client.delete_objects(Bucket=self.bucket, Delete={'Objects': batch})
        except ClientError as e:
            print(f"Error deleting prefix {prefix}: {e}")

    def delete_source_csv(self, doc_id: str):
        """Deletes the original raw CSV from Spaces."""
        key = f"raw_csvs/{doc_id}.csv"
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
            print(f"DEBUG: Deleted source CSV {key}")
        except ClientError as e:
            print(f"Error deleting source CSV for {doc_id}: {e}")

    def delete_result(self, doc_id: str):
        """Deletes the final processed JSON from Spaces."""
        key = f"processed_csv_json/{doc_id}.json"
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
            print(f"DEBUG: Deleted result JSON {key}")
        except ClientError as e:
            print(f"Error deleting result JSON for {doc_id}: {e}")

    def list_processed_documents(self) -> List[str]:
        try:
            doc_ids = []
            paginator = self.client.get_paginator('list_objects_v2')
            for page in paginator.paginate(Bucket=self.bucket, Prefix='processed_csv_json/'):
                if 'Contents' in page:
                    for obj in page['Contents']:
                        doc_id = obj['Key'].split('/')[-1].replace('.json', '')
                        if doc_id:
                            doc_ids.append(doc_id)
            return doc_ids
        except ClientError as e:
            print(f"Error listing processed documents: {e}")
            return []

    def get_result(self, doc_id: str) -> Optional[dict]:
        key = f"processed_csv_json/{doc_id}.json"
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
            return json.loads(response['Body'].read().decode('utf-8'))
        except ClientError as e:
            print(f"Error reading result for {doc_id}: {e}")
            return None
