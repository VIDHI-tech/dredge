import os
import time
import requests
from groq import Groq
from dotenv import load_dotenv

from pathlib import Path
# Load .env from the same directory
env_path = Path(__file__).parent / '.env'
load_dotenv(dotenv_path=env_path)

# Model to use (Vision capable)
MODEL_ID = os.getenv("IMAGE_MODEL_ID", "meta-llama/llama-4-scout-17b-16e-instruct")
MODEL_PROVIDER = os.getenv("IMAGE_MODEL_PROVIDER", "groq")

class ModelEngine:
    def __init__(self):
        self.api_key = os.getenv("GROQ_API_KEY")
        self.client = Groq(api_key=self.api_key) if MODEL_PROVIDER == "groq" else None
        print(f"Initialized Model Engine with {MODEL_PROVIDER} model: {MODEL_ID}")

    def _generate_local(self, messages, json_mode):
        ollama_messages = []
        for message in messages:
            parts = message["content"]
            if isinstance(parts, str):
                ollama_messages.append({"role": message["role"], "content": parts})
                continue
            text = "\n".join(part["text"] for part in parts if part["type"] == "text")
            images = [part["image_url"]["url"].split(",", 1)[1]
                      for part in parts if part["type"] == "image_url"]
            ollama_messages.append({"role": message["role"], "content": text, "images": images})
        payload = {"model": MODEL_ID, "messages": ollama_messages, "stream": False}
        if json_mode:
            payload["format"] = "json"
        response = requests.post(
            os.getenv("OLLAMA_URL", "http://127.0.0.1:11434") + "/api/chat",
            json=payload,
            timeout=300,
        )
        response.raise_for_status()
        return response.json()["message"]["content"]

    def _generate(self, messages, json_mode=False, max_retries=3):
        """
        Helper to call Groq API with retries and exponential backoff.
        """
        for attempt in range(max_retries):
            try:
                if MODEL_PROVIDER == "ollama":
                    return self._generate_local(messages, json_mode)
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

    def infer_schema(self, image_data):
        """
        image_data: dict with 'mime_type' and 'base64_data'
        """
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text", 
                        "text": """You are a data architect. Analyze this image and generate a JSON schema.
CRITICAL INSTRUCTION:
- If you see a TABLE, LIST, or REPEATED DATA (e.g., list of items, rows), you MUST define it as an 'array' of objects.
- Ensure you capture ALL visible columns or fields.
- Output ONLY the JSON schema."""
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{image_data['mime_type']};base64,{image_data['base64_data']}"
                        }
                    }
                ]
            }
        ]
        return self._generate(messages, json_mode=True)

    def extract_data(self, image_data, schema_str):
        """
        image_data: dict with 'mime_type' and 'base64_data'
        """
        messages = [
            {
                "role": "user", 
                "content": [
                    {
                        "type": "text",
                        "text": f"""You are a meticulous data entry clerk.
Your Goal: Extract EVERY SINGLE PIECE of data from the image that fits the schema.
- Do not summarize.
- Extraction must be EXACT.
- Output valid JSON only matching the schema provided.
- If a field is not found, use null or empty string.

Schema:
{schema_str}"""
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{image_data['mime_type']};base64,{image_data['base64_data']}"
                        }
                    }
                ]
            }
        ]
        return self._generate(messages, json_mode=True)
