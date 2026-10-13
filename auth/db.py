import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())

MONGO_URI = os.getenv("MONGO_URI")
AUTH_DB_NAME = "dredge_auth"

_client: AsyncIOMotorClient = None


def get_mongo_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(MONGO_URI)
    return _client


def get_auth_db():
    """Returns the shared auth database (dredge_auth)."""
    return get_mongo_client()[AUTH_DB_NAME]


def get_user_db(db_name: str):
    """Returns a user's personal database by name."""
    return get_mongo_client()[db_name]
