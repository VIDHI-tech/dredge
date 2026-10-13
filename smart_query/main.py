"""
Smart Query FastAPI service.
Provides chat-based querying with conversation persistence
and background job processing for analysis.
"""

import asyncio
import uuid
import traceback
from fastapi import FastAPI, HTTPException, Depends

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from auth.auth_utils import get_current_user
from .models import (
    AskRequest, AskResponse, JobStatusResponse,
    ConversationListResponse, ConversationSummary,
    ConversationDetail, MessageOut, RenameRequest,
)
from .chat_store import ChatStore
from .job_manager import QueryJobManager
from .analyst import AnalystAgent, generate_title
from .tools import ToolExecutor

from nlp_to_mongo.schema_manager import SchemaManager
from cache_utils import RedisCache

app = FastAPI(title="Smart Query")

# Module-level singletons
chat_store = ChatStore()
job_manager = QueryJobManager()
cache = RedisCache()
nlp_schema_manager = SchemaManager(cache=cache)

# Track running background tasks to prevent GC
_background_tasks: set[asyncio.Task] = set()


def _get_user_id(current_user: dict) -> str:
    return current_user.get("user_id", current_user.get("email", "unknown"))


# ---- Ask endpoint ----

@app.post("/ask", response_model=AskResponse)
async def ask(request: AskRequest, current_user: dict = Depends(get_current_user)):
    user_id = _get_user_id(current_user)
    db_name = current_user["db_name"]

    # Create or use existing conversation
    conversation_id = request.conversation_id
    if not conversation_id:
        conversation_id = await chat_store.create_conversation(
            user_id=user_id,
            db_name=db_name,
            collection=request.collection,
            title="New Chat",
        )

    # Save user message
    await chat_store.add_message(
        conversation_id=conversation_id,
        role="user",
        content=request.text,
    )

    return await _handle_analytical(request, conversation_id, db_name, user_id)


async def _handle_analytical(
    request: AskRequest, conversation_id: str,
    db_name: str, user_id: str
) -> AskResponse:
    """Handle analytical queries via background agent job."""
    job_id = str(uuid.uuid4())

    # Create placeholder assistant message
    message_id = await chat_store.add_message(
        conversation_id=conversation_id,
        role="assistant",
        content="",
        query_type="analytical",
        job_id=job_id,
        status="processing",
    )

    # Create job in Redis
    job_manager.create_job(
        job_id=job_id,
        conversation_id=conversation_id,
        message_id=message_id,
        user_id=user_id,
        db_name=db_name,
    )

    # Launch background task
    task = asyncio.create_task(
        _run_analysis(
            job_id=job_id,
            message_id=message_id,
            conversation_id=conversation_id,
            user_query=request.text,
            collection=request.collection,
            db_name=db_name,
            user_id=user_id,
        )
    )
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    # Generate title in background
    asyncio.create_task(_maybe_generate_title(conversation_id, request.text, user_id))

    return AskResponse(
        message_id=message_id,
        conversation_id=conversation_id,
        query_type="analytical",
        job_id=job_id,
        status="processing",
    )


async def _run_analysis(
    job_id: str, message_id: str, conversation_id: str,
    user_query: str, collection: str, db_name: str, user_id: str
):
    """Background task that runs the analyst agent."""
    try:
        # Get schema for context
        schema = await nlp_schema_manager.get_schema(collection, db_name=db_name)
        schema_summary = nlp_schema_manager.get_schema_summary(schema)

        # Check identity index
        tool_exec = ToolExecutor(db_name)
        identity_available = await tool_exec.check_identity_index_available()

        # Get conversation context
        context = await chat_store.get_recent_context(conversation_id)

        # Run agent
        agent = AnalystAgent(db_name=db_name, collection=collection)
        result = await agent.analyze(
            user_query=user_query,
            schema_summary=schema_summary,
            conversation_context=context,
            identity_index_available=identity_available,
        )

        # Update message with results
        await chat_store.update_message(message_id, {
            "analysis": result.get("analysis", ""),
            "table": result.get("table"),
            "methodology": result.get("methodology", ""),
            "status": "complete",
        })

        # Update job
        job_manager.complete_job(job_id, result)

    except Exception as e:
        traceback.print_exc()
        error_msg = str(e)
        await chat_store.update_message(message_id, {
            "content": f"Analysis failed: {error_msg}",
            "status": "error",
        })
        job_manager.fail_job(job_id, error_msg)


async def _maybe_generate_title(conversation_id: str, query: str, user_id: str):
    """Generate a title for new conversations (only if still 'New Chat')."""
    try:
        convo = await chat_store.get_conversation(conversation_id, user_id)
        if convo and convo.get("title") == "New Chat":
            title = await generate_title(query)
            await chat_store.rename_conversation(conversation_id, user_id, title)
    except Exception:
        pass


# ---- Job status endpoint ----

@app.get("/job/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str, current_user: dict = Depends(get_current_user)):
    user_id = _get_user_id(current_user)
    status_data = job_manager.get_status(job_id)

    if not status_data:
        raise HTTPException(status_code=404, detail="Job not found")

    # Verify ownership
    if status_data.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Not your job")

    status = status_data.get("status", "processing")

    if status == "complete":
        result = job_manager.get_result(job_id)
        return JobStatusResponse(
            status="complete",
            message_id=status_data.get("message_id"),
            conversation_id=status_data.get("conversation_id"),
            analysis=result.get("analysis") if result else None,
            table=result.get("table") if result else None,
            methodology=result.get("methodology") if result else None,
        )
    elif status == "error":
        return JobStatusResponse(
            status="error",
            message_id=status_data.get("message_id"),
            conversation_id=status_data.get("conversation_id"),
            error=status_data.get("error", "Unknown error"),
        )
    else:
        return JobStatusResponse(
            status="processing",
            message_id=status_data.get("message_id"),
            conversation_id=status_data.get("conversation_id"),
        )


# ---- Conversation CRUD ----

@app.get("/conversations", response_model=ConversationListResponse)
async def list_conversations(
    skip: int = 0, limit: int = 50,
    current_user: dict = Depends(get_current_user)
):
    user_id = _get_user_id(current_user)
    db_name = current_user["db_name"]
    convos, total = await chat_store.list_conversations(user_id, db_name, skip, limit)
    return ConversationListResponse(
        conversations=[ConversationSummary(**c) for c in convos],
        total=total,
    )


@app.get("/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: str,
    current_user: dict = Depends(get_current_user)
):
    user_id = _get_user_id(current_user)
    convo = await chat_store.get_conversation(conversation_id, user_id)
    if not convo:
        raise HTTPException(status_code=404, detail="Conversation not found")

    messages = await chat_store.get_messages(conversation_id)
    return ConversationDetail(
        id=convo["id"],
        title=convo["title"],
        collection=convo["collection"],
        messages=[MessageOut(**m) for m in messages],
    )


@app.patch("/conversations/{conversation_id}")
async def rename_conversation(
    conversation_id: str, body: RenameRequest,
    current_user: dict = Depends(get_current_user)
):
    user_id = _get_user_id(current_user)
    await chat_store.rename_conversation(conversation_id, user_id, body.title)
    return {"status": "ok"}


@app.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    current_user: dict = Depends(get_current_user)
):
    user_id = _get_user_id(current_user)
    await chat_store.delete_conversation(conversation_id, user_id)
    return {"status": "ok"}
