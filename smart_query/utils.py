"""Shared utilities for smart_query module."""

import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
_client = None

SYSTEM_DB = "dredge_system"


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(MONGO_URI)
    return _client


def get_database(db_name: str):
    return get_client()[db_name]


def get_system_db():
    return get_client()[SYSTEM_DB]
