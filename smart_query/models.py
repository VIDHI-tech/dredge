"""Pydantic models for the smart query module."""

from pydantic import BaseModel, Field
from typing import Optional, Any


class AskRequest(BaseModel):
    text: str
    collection: str
    conversation_id: Optional[str] = None
    page: int = 1
    page_size: int = 50


class AskResponse(BaseModel):
    message_id: str
    conversation_id: str
    query_type: str  # "simple" | "analytical"
    # Populated immediately for simple queries
    mongo_query: Optional[list] = None
    results: Optional[list] = None
    total_count: Optional[int] = None
    explanation: Optional[str] = None
    # Populated for analytical queries (background job)
    job_id: Optional[str] = None
    status: str = "complete"  # "complete" | "processing" | "error"


class JobStatusResponse(BaseModel):
    status: str  # "processing" | "complete" | "error"
    message_id: Optional[str] = None
    conversation_id: Optional[str] = None
    analysis: Optional[str] = None
    table: Optional[dict] = None
    methodology: Optional[str] = None
    error: Optional[str] = None


class ConversationSummary(BaseModel):
    id: str
    title: str
    collection: str
    created_at: str
    updated_at: str
    message_count: int = 0


class ConversationListResponse(BaseModel):
    conversations: list[ConversationSummary]
    total: int


class MessageOut(BaseModel):
    id: str
    role: str  # "user" | "assistant"
    content: str
    query_type: Optional[str] = None
    mongo_query: Optional[Any] = None
    results: Optional[list] = None
    total_count: Optional[int] = None
    analysis: Optional[str] = None
    table: Optional[dict] = None
    methodology: Optional[str] = None
    job_id: Optional[str] = None
    status: str = "complete"
    created_at: str


class ConversationDetail(BaseModel):
    id: str
    title: str
    collection: str
    messages: list[MessageOut]


class RenameRequest(BaseModel):
    title: str
