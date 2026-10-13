import json
from dotenv import load_dotenv, find_dotenv

# Load root .env
load_dotenv(find_dotenv())
import boto3
import os
from botocore.exceptions import ClientError
from typing import List, Optional
import json

class DigitalOceanSpaces:
    def __init__(self):
        self.region = os.getenv("DO_SPACES_REGION", "nyc3")
        self.endpoint_url = os.getenv("DO_SPACES_ENDPOINT", f"https://{self.region}.digitaloceanspaces.com")
        self.key_id = os.getenv("DO_SPACES_KEY")
        self.secret_key = os.getenv("DO_SPACES_SECRET")
        self.bucket = os.getenv("DO_SPACES_BUCKET")
        
        if self.bucket and self.bucket in self.endpoint_url:
            print(f"DEBUG: Detected bucket in endpoint. Fixing...")
            self.endpoint_url = self.endpoint_url.replace(f"{self.bucket}.", "")
            
        self.session = boto3.session.Session()
        self.client = self.session.client('s3',
                                          region_name=self.region,
                                          endpoint_url=self.endpoint_url,
                                          aws_access_key_id=self.key_id,
                                          aws_secret_access_key=self.secret_key)
        
        print(f"DEBUG: Storage Configured with Endpoint='{self.endpoint_url}', Bucket='{self.bucket}'")

    def upload_chunk(self, doc_id: str, index: int, text: str) -> str:
        """Uploads a text chunk to Spaces."""
        key = f"raw_chunks/{doc_id}/{index}.txt"
        try:
            self.client.put_object(Bucket=self.bucket, Key=key, Body=text.encode('utf-8'), ContentType='text/plain', ACL='private')
            return key
        except ClientError as e:
            print(f"Error uploading chunk {index} for {doc_id}: {e}")
            raise

    def list_chunks(self, doc_id: str) -> List[dict]:
        """Lists and downloads all chunks for a document. (Legacy: loads all in RAM)"""
        return list(self.yield_chunks(doc_id))

    def yield_chunks(self, doc_id: str):
        """Yields chunks one by one to save RAM."""
        prefix = f"raw_chunks/{doc_id}/"
        try:
            paginator = self.client.get_paginator('list_objects_v2')
            
            # 1. Get all keys first to sort them
            all_keys = []
            for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
                 if 'Contents' in page:
                    for obj in page['Contents']:
                        all_keys.append(obj['Key'])
            
            # 2. Sort by index
            # Key format: raw_chunks/{doc_id}/{index}.txt
            def get_index(key):
                try:
                    return int(key.split('/')[-1].replace('.txt', ''))
                except ValueError:
                    return 999999
            
            all_keys.sort(key=get_index)
            
            # 3. Yield content one by one
            for key in all_keys:
                try:
                    index = get_index(key)
                    response = self.client.get_object(Bucket=self.bucket, Key=key)
                    text = response['Body'].read().decode('utf-8')
                    yield {'index': index, 'text': text}
                except ClientError as e:
                    print(f"Error yielding chunk {key}: {e}")
                    
        except ClientError as e:
            print(f"Error listing chunks for {doc_id}: {e}")

    def save_result(self, doc_id: str, data: dict) -> str:
        """Saves the final processed JSON to Spaces."""
        key = f"processed_json/{doc_id}.json"
        try:
            json_str = json.dumps(data, indent=2)
            self.client.put_object(Bucket=self.bucket, Key=key, Body=json_str.encode('utf-8'), ContentType='application/json', ACL='private')
            return key
        except ClientError as e:
            print(f"Error saving result for {doc_id}: {e}")
            raise

    def is_processed(self, doc_id: str) -> bool:
        """Checks if a document has already been processed."""
        key = f"processed_json/{doc_id}.json"
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError:
            return False

    def get_result(self, doc_id: str) -> Optional[dict]:
        """Retrieves the final processed JSON result from Spaces."""
        key = f"processed_json/{doc_id}.json"
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
            return json.loads(response['Body'].read().decode('utf-8'))
        except ClientError as e:
            print(f"Error reading result for {doc_id}: {e}")
            return None

    def delete_chunks(self, doc_id: str):
        """Deletes all chunks for a document to free up space."""
        prefix = f"raw_chunks/{doc_id}/"
        try:
            # List objects to verify existence and get keys
            paginator = self.client.get_paginator('list_objects_v2')
            objects_to_delete = []
            
            for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
                if 'Contents' in page:
                    for obj in page['Contents']:
                        objects_to_delete.append({'Key': obj['Key']})
            
            if objects_to_delete:
                print(f"DEBUG: Deleting {len(objects_to_delete)} chunks for {doc_id}...")
                # Delete in batches of 1000 (S3 limit)
                for i in range(0, len(objects_to_delete), 1000):
                    batch = objects_to_delete[i:i+1000]
                    self.client.delete_objects(Bucket=self.bucket, Delete={'Objects': batch})
                print(f"DEBUG: Cleanup complete for {doc_id}.")
            else:
                print(f"DEBUG: No chunks found to delete for {doc_id}.")
                
        except ClientError as e:
            print(f"Error deleting chunks for {doc_id}: {e}")

    def save_processed_chunk(self, doc_id: str, index: int, data: dict) -> str:
        """Saves a processed JSON chunk to Spaces."""
        key = f"processed_chunks/{doc_id}/{index}.json"
        try:
            json_str = json.dumps(data)
            self.client.put_object(Bucket=self.bucket, Key=key, Body=json_str.encode('utf-8'), ContentType='application/json', ACL='private')
            return key
        except ClientError as e:
            print(f"Error saving processed chunk {index} for {doc_id}: {e}")
            raise

    def save_schema(self, doc_id: str, schema: dict) -> str:
        """Saves the inferred schema to Spaces."""
        key = f"schemas/{doc_id}.json"
        try:
            json_str = json.dumps(schema, indent=2)
            self.client.put_object(Bucket=self.bucket, Key=key, Body=json_str.encode('utf-8'), ContentType='application/json', ACL='private')
            return key
        except ClientError as e:
            print(f"Error saving schema for {doc_id}: {e}")
            raise

    def get_schema(self, doc_id: str) -> Optional[dict]:
        """Retrieves the schema for a document."""
        key = f"schemas/{doc_id}.json"
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
            return json.loads(response['Body'].read().decode('utf-8'))
        except ClientError as e:
            print(f"Error reading schema for {doc_id}: {e}")
            return None

    def upload_pdf(self, doc_id: str, file_content: bytes) -> str:
        """Uploads the raw PDF to Spaces (bytes — legacy)."""
        key = f"raw_pdfs/{doc_id}.pdf"
        try:
            self.client.put_object(Bucket=self.bucket, Key=key, Body=file_content, ContentType='application/pdf', ACL='private')
            return key
        except ClientError as e:
            print(f"Error uploading PDF for {doc_id}: {e}")
            raise

    def upload_pdf_file(self, doc_id: str, file_path: str) -> str:
        """Streams a PDF file to Spaces without loading it into RAM."""
        key = f"raw_pdfs/{doc_id}.pdf"
        try:
            with open(file_path, "rb") as f:
                self.client.upload_fileobj(f, self.bucket, key,
                    ExtraArgs={'ContentType': 'application/pdf', 'ACL': 'private'})
            print(f"DEBUG: Streamed PDF upload for {doc_id}")
            return key
        except ClientError as e:
            print(f"Error uploading PDF for {doc_id}: {e}")
            raise

    def download_pdf(self, doc_id: str) -> bytes:
        """Downloads the raw PDF from Spaces (bytes — legacy)."""
        key = f"raw_pdfs/{doc_id}.pdf"
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
            return response['Body'].read()
        except ClientError as e:
            print(f"Error downloading PDF for {doc_id}: {e}")
            raise

    def download_pdf_to_file(self, doc_id: str, dest_path: str):
        """Streams the PDF from Spaces directly to a file on disk."""
        key = f"raw_pdfs/{doc_id}.pdf"
        try:
            self.client.download_file(self.bucket, key, dest_path)
            print(f"DEBUG: Streamed PDF download to {dest_path}")
        except ClientError as e:
            print(f"Error downloading PDF for {doc_id}: {e}")
            raise

    def stream_assembly_json(self, doc_id: str, schema: dict) -> str:
        """
        Streams all processed chunks into a single final JSON file on Spaces.
        Format: { "doc_id": "...", "schema": ..., "data": [ ...merged data... ] }
        """
        final_key = f"processed_json/{doc_id}.json"
        chunk_prefix = f"processed_chunks/{doc_id}/"

        # 1. Get all processed chunk keys
        try:
            paginator = self.client.get_paginator('list_objects_v2')
            all_keys = []
            for page in paginator.paginate(Bucket=self.bucket, Prefix=chunk_prefix):
                if 'Contents' in page:
                    for obj in page['Contents']:
                        all_keys.append(obj['Key'])
            
            # Sort keys by index
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

        # 2. Define Generator for Multipart Upload (Simulated via BytesIO if Multipart not supported easily, 
        #    but standard boto3 put_object expects bytes. 
        #    For true streaming upload, we need smart buffering. 
        #    SIMPLIFIED STRATEGY: 
        #    Start with Header -> Download Chunk 1 -> Yield -> Download Chunk 2 -> Yield -> Footer
        #    This keeps only 1 chunk in RAM at a time.
        
        # We will construct a generator that yields bytes
        def json_stream_generator():
            # HEADER
            header = {
                "doc_id": doc_id,
                "schema": schema,
                "processed_at": 0, # Placeholder
                "data": [] # We will inject contents here specially involves text manipulation
            }
            # We want to output: {"doc_id": "...", "data": [ <chunk1_content>, <chunk2_content> ]}
            # So we create the start
            yield f'{{"doc_id": "{doc_id}", "schema": {json.dumps(schema)}, "data": ['.encode('utf-8')
            
            first = True
            for key in all_keys:
                try:
                    obj = self.client.get_object(Bucket=self.bucket, Key=key)
                    content = obj['Body'].read().decode('utf-8')
                    
                    # Strip outer brackets to flatten array-of-arrays into a single flat array.
                    # Each chunk is stored as a JSON array like [{...}, {...}].
                    # We unwrap it so the final output is data: [obj1, obj2, ...] not data: [[obj1, obj2], ...]
                    inner = content.strip()
                    if inner.startswith('[') and inner.endswith(']'):
                        inner = inner[1:-1].strip()
                    
                    # Skip empty chunks (e.g. "[]" becomes "")
                    if inner:
                        if not first:
                            yield b","
                        first = False
                        yield inner.encode('utf-8')
                    
                except Exception as e:
                    print(f"Error reading chunk {key} during assembly: {e}")
            
            # FOOTER
            yield b"]}"

        # 3. Upload using the generator
        # boto3 client.put_object supports body as a file-like object. 
        # We need a wrapper class to treat the generator as a file.
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
            print(f"DEBUG: Starting streaming assembly for {doc_id}...")
            # We use upload_fileobj which handles multipart uploads automatically for large streams
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

    def delete_processed_chunks(self, doc_id: str):
        """Deletes all intermediate processed chunks for a document."""
        prefix = f"processed_chunks/{doc_id}/"
        try:
            paginator = self.client.get_paginator('list_objects_v2')
            objects_to_delete = []
            
            for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
                if 'Contents' in page:
                    for obj in page['Contents']:
                        objects_to_delete.append({'Key': obj['Key']})
            
            if objects_to_delete:
                print(f"DEBUG: Deleting {len(objects_to_delete)} intermediate chunks for {doc_id}...")
                for i in range(0, len(objects_to_delete), 1000):
                    batch = objects_to_delete[i:i+1000]
                    self.client.delete_objects(Bucket=self.bucket, Delete={'Objects': batch})
                print(f"DEBUG: Processed chunks cleanup complete for {doc_id}.")
                
        except ClientError as e:
            print(f"Error deleting processed chunks for {doc_id}: {e}")

    def delete_source_pdf(self, doc_id: str):
        """Deletes the original raw PDF from Spaces."""
        key = f"raw_pdfs/{doc_id}.pdf"
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
            print(f"DEBUG: Deleted source PDF {key}")
        except ClientError as e:
            print(f"Error deleting source PDF for {doc_id}: {e}")

    def delete_schema(self, doc_id: str):
        """Deletes the schema JSON from Spaces."""
        key = f"schemas/{doc_id}.json"
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
            print(f"DEBUG: Deleted schema {key}")
        except ClientError as e:
            print(f"Error deleting schema for {doc_id}: {e}")

    def delete_result(self, doc_id: str):
        """Deletes the final processed JSON from Spaces."""
        key = f"processed_json/{doc_id}.json"
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
            print(f"DEBUG: Deleted result JSON {key}")
        except ClientError as e:
            print(f"Error deleting result JSON for {doc_id}: {e}")

    def list_processed_documents(self) -> List[str]:
        """Lists all document IDs that have been fully processed."""
        try:
            doc_ids = []
            paginator = self.client.get_paginator('list_objects_v2')
            for page in paginator.paginate(Bucket=self.bucket, Prefix='processed_json/'):
                if 'Contents' in page:
                    for obj in page['Contents']:
                        # Key is like "processed_json/{doc_id}.json"
                        doc_id = obj['Key'].split('/')[-1].replace('.json', '')
                        if doc_id:
                            doc_ids.append(doc_id)
            return doc_ids
        except ClientError as e:
            print(f"Error listing processed documents: {e}")
            return []

    def list_unprocessed_documents(self) -> List[str]:
        """
        Lists all document IDs in raw_chunks that do not have a corresponding file in processed_json.
        Note: This lists TOP-LEVEL folders in raw_chunks/.
        """
        try:
            # List folders in raw_chunks/
            doc_ids = set()
            paginator = self.client.get_paginator('list_objects_v2')
            for page in paginator.paginate(Bucket=self.bucket, Prefix='raw_chunks/', Delimiter='/'):
                if 'CommonPrefixes' in page:
                    for prefix in page['CommonPrefixes']:
                        # Prefix is like "raw_chunks/{doc_id}/"
                        doc_id = prefix['Prefix'].split('/')[1]
                        doc_ids.add(doc_id)
            
            unprocessed = []
            for doc_id in doc_ids:
                if not self.is_processed(doc_id):
                    unprocessed.append(doc_id)
            
            return unprocessed
        except ClientError as e:
            print(f"Error listing documents: {e}")
            return []
