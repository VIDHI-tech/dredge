import os
import time
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

# Model to use

# Model to use
MODEL_ID = os.getenv("TEXT_MODEL_ID", "qwen/qwen3-32b")

class ModelEngine:
    def __init__(self, model_path=None):
        # We ignore model_path as we use Groq API
        # Using the key provided by user
        self.api_key = os.getenv("GROQ_API_KEY")
        self.client = Groq(api_key=self.api_key)
        print(f"Initialized Model Engine with model: {MODEL_ID}")

    def _generate(self, messages, json_mode=False, max_retries=3):
        """
        Helper to call Groq API with retries and exponential backoff.
        """
        for attempt in range(max_retries):
            try:
                params = {
                    "model": MODEL_ID,
                    "messages": messages,
                    "temperature": 0.1,  
                    "max_tokens": 8192,
                }
                if json_mode:
                    params["response_format"] = {"type": "json_object"}
                
                completion = self.client.chat.completions.create(**params)
                return completion.choices[0].message.content
            except Exception as e:
                wait_time = 2 ** (attempt + 1)  # 2s, 4s, 8s
                print(f"Groq API Error (attempt {attempt+1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    print(f"  Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    print(f"  All {max_retries} attempts failed.")
                    return "{}"

    def infer_schema(self, text_chunk):
        messages = [
            {
                "role": "system",
                "content": """You are a data architect. Analyze the text and generate a JSON schema.
CRITICAL INSTRUCTION:
- If you see a TABLE, LIST, or REPEATED DATA (e.g., list of contributors), you MUST define it as an 'array' of objects.
- For CONTRIBUTIONS, ensure you capture ALL columns: Name, Address, City, State, Zip, Employer, Date, Amount.
- IMPORTANT: A 'Name' or 'Contributor' field can be EITHER a person's name (e.g. "John Smith") OR an organization/agency name (e.g. "ABC Corp", "State Teachers Union"). Use a single string field for the name; do NOT split into first/last if the source data has one combined name column.
- Output ONLY the JSON schema."""
            },
            {
                "role": "user",
                "content": f"Document Text:\n{text_chunk}\n\nGenerate JSON Schema:"
            }
        ]
        return self._generate(messages, json_mode=True)

    def extract_data(self, text_chunk, schema_str):
        messages = [
            {
                "role": "system", 
                "content": f"""You are a meticulous data entry clerk.
Your Goal: Extract EVERY SINGLE PIECE of data from the text that fits the schema.
- Do not summarize.
- Do not omit ANY items. Count every row in the source table and ensure your output array has the same count.
- If the schema contains an ARRAY (e.g. for contributors), you MUST extract EVERY SINGLE ROW from the document tables into that array.
- IMPORTANT: A name/contributor field may contain EITHER a person's name (e.g. "John Smith") OR an organization/agency/company name (e.g. "ABC Corp", "State Teachers Union"). Extract the name EXACTLY as it appears in the document. Do NOT skip entries just because the name looks like an organization instead of a person.
- Output valid JSON only matching the schema provided.
- If a field is not found, use null or empty string.

Schema:
{schema_str}"""
            },
            {
                "role": "user",
                "content": f"Document Text:\n{text_chunk}\n\nExtract data as JSON:"
            }
        ]
        return self._generate(messages, json_mode=True)
