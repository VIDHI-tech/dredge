"""
MongoDB-backed conversation and message persistence.
Stores chat history in dredge_system database, scoped per user.
"""

import time
from datetime import datetime
from typing import Optional
from bson import ObjectId
from .utils import get_system_db

CONVERSATIONS_COL = "conversations"
MESSAGES_COL = "messages"


class ChatStore:
    def __init__(self):
        self.db = get_system_db()
        self._indexes_created = False

    async def _ensure_indexes(self):
        if self._indexes_created:
            return
        convos = self.db[CONVERSATIONS_COL]
        msgs = self.db[MESSAGES_COL]
        await convos.create_index([("user_id", 1), ("updated_at", -1)])
        await msgs.create_index([("conversation_id", 1), ("created_at", 1)])
        self._indexes_created = True

    # ---- Conversations ----

    async def create_conversation(
        self, user_id: str, db_name: str, collection: str, title: str = "New Chat"
    ) -> str:
        await self._ensure_indexes()
        now = datetime.utcnow().isoformat()
        doc = {
            "user_id": user_id,
            "db_name": db_name,
            "collection": collection,
            "title": title,
            "created_at": now,
            "updated_at": now,
        }
        result = await self.db[CONVERSATIONS_COL].insert_one(doc)
        return str(result.inserted_id)

    async def list_conversations(
        self, user_id: str, db_name: str,
        skip: int = 0, limit: int = 50
    ) -> tuple[list[dict], int]:
        await self._ensure_indexes()
        col = self.db[CONVERSATIONS_COL]
        query = {"user_id": user_id, "db_name": db_name}
        total = await col.count_documents(query)

        cursor = col.find(query).sort("updated_at", -1).skip(skip).limit(limit)
        convos = []
        async for doc in cursor:
            msg_count = await self.db[MESSAGES_COL].count_documents(
                {"conversation_id": str(doc["_id"])}
            )
            convos.append({
                "id": str(doc["_id"]),
                "title": doc.get("title", "New Chat"),
                "collection": doc.get("collection", ""),
                "created_at": doc.get("created_at", ""),
                "updated_at": doc.get("updated_at", ""),
                "message_count": msg_count,
            })
        return convos, total

    async def get_conversation(self, conversation_id: str, user_id: str) -> Optional[dict]:
        doc = await self.db[CONVERSATIONS_COL].find_one({
            "_id": ObjectId(conversation_id),
            "user_id": user_id,
        })
        if not doc:
            return None
        return {
            "id": str(doc["_id"]),
            "title": doc.get("title", "New Chat"),
            "collection": doc.get("collection", ""),
            "db_name": doc.get("db_name", ""),
            "created_at": doc.get("created_at", ""),
            "updated_at": doc.get("updated_at", ""),
        }

    async def rename_conversation(self, conversation_id: str, user_id: str, title: str):
        await self.db[CONVERSATIONS_COL].update_one(
            {"_id": ObjectId(conversation_id), "user_id": user_id},
            {"$set": {"title": title, "updated_at": datetime.utcnow().isoformat()}},
        )

    async def delete_conversation(self, conversation_id: str, user_id: str):
        await self.db[CONVERSATIONS_COL].delete_one(
            {"_id": ObjectId(conversation_id), "user_id": user_id}
        )
        await self.db[MESSAGES_COL].delete_many(
            {"conversation_id": conversation_id}
        )

    async def touch_conversation(self, conversation_id: str):
        await self.db[CONVERSATIONS_COL].update_one(
            {"_id": ObjectId(conversation_id)},
            {"$set": {"updated_at": datetime.utcnow().isoformat()}},
        )

    # ---- Messages ----

    async def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        query_type: Optional[str] = None,
        mongo_query=None,
        results=None,
        total_count: Optional[int] = None,
        analysis: Optional[str] = None,
        table: Optional[dict] = None,
        methodology: Optional[str] = None,
        job_id: Optional[str] = None,
        status: str = "complete",
    ) -> str:
        await self._ensure_indexes()
        doc = {
            "conversation_id": conversation_id,
            "role": role,
            "content": content,
            "query_type": query_type,
            "mongo_query": mongo_query,
            "results": results,
            "total_count": total_count,
            "analysis": analysis,
            "table": table,
            "methodology": methodology,
            "job_id": job_id,
            "status": status,
            "created_at": datetime.utcnow().isoformat(),
        }
        result = await self.db[MESSAGES_COL].insert_one(doc)
        await self.touch_conversation(conversation_id)
        return str(result.inserted_id)

    async def update_message(self, message_id: str, updates: dict):
        await self.db[MESSAGES_COL].update_one(
            {"_id": ObjectId(message_id)},
            {"$set": updates},
        )

    async def get_messages(
        self, conversation_id: str, limit: int = 200
    ) -> list[dict]:
        cursor = (
            self.db[MESSAGES_COL]
            .find({"conversation_id": conversation_id})
            .sort("created_at", 1)
            .limit(limit)
        )
        messages = []
        async for doc in cursor:
            messages.append({
                "id": str(doc["_id"]),
                "role": doc["role"],
                "content": doc.get("content", ""),
                "query_type": doc.get("query_type"),
                "mongo_query": doc.get("mongo_query"),
                "results": doc.get("results"),
                "total_count": doc.get("total_count"),
                "analysis": doc.get("analysis"),
                "table": doc.get("table"),
                "methodology": doc.get("methodology"),
                "job_id": doc.get("job_id"),
                "status": doc.get("status", "complete"),
                "created_at": doc.get("created_at", ""),
            })
        return messages

    async def get_recent_context(
        self, conversation_id: str, n: int = 10
    ) -> list[dict]:
        """Get last N messages for LLM context in follow-up queries."""
        cursor = (
            self.db[MESSAGES_COL]
            .find(
                {"conversation_id": conversation_id},
                {"role": 1, "content": 1, "analysis": 1, "query_type": 1},
            )
            .sort("created_at", -1)
            .limit(n)
        )
        msgs = []
        async for doc in cursor:
            msgs.append({"role": doc["role"], "content": doc.get("content", "")})
            if doc.get("analysis"):
                msgs[-1]["content"] += f"\n\n[Analysis]: {doc['analysis']}"
        msgs.reverse()
        return msgs
