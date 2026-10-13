import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv, find_dotenv

# Load root .env
load_dotenv(find_dotenv())

# Get URI from environment
MONGO_URI = os.getenv("MONGO_URI")

_client: AsyncIOMotorClient = None


def get_mongo_client():
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(MONGO_URI)
    return _client


def get_database(db_name: str = "test"):
    """Returns a database by name. Defaults to 'test' for backward compatibility."""
    client = get_mongo_client()
    return client[db_name]
