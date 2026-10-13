from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import uuid

from .models import SignupRequest, LoginRequest, BucketRequest, MergeRequest, UnmergeRequest, TokenResponse, UserProfile
from .auth_utils import hash_password, verify_password, create_token, get_current_user
from .db import get_auth_db, get_user_db, get_mongo_client


app = FastAPI(title="Dredge Auth Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    client = get_mongo_client()
    try:
        await client.admin.command("ping")
        print("Auth Service: MongoDB connected.")
    except Exception as e:
        print(f"Auth Service: MongoDB connection error: {e}")

    auth_db = get_auth_db()
    await auth_db.users.create_index("email", unique=True)


# ──────────────────────────────────── Signup ────────────────────────────────────

@app.post("/signup", response_model=TokenResponse)
async def signup(request: SignupRequest):
    if len(request.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    auth_db = get_auth_db()

    # Check if email already exists
    existing = await auth_db.users.find_one({"email": request.email})
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    # Generate a unique database name for this user
    short_id = uuid.uuid4().hex[:12]
    db_name = f"user_{short_id}"

    # Create user document
    user_doc = {
        "email": request.email,
        "password_hash": hash_password(request.password),
        "db_name": db_name,
        "buckets": [],
        "merged_buckets": [],
    }
    result = await auth_db.users.insert_one(user_doc)
    user_id = str(result.inserted_id)

    # Create the user's database by inserting a metadata doc (MongoDB creates DBs lazily)
    user_db = get_user_db(db_name)
    await user_db["_meta"].insert_one({
        "owner_email": request.email,
        "created_by": "dredge_auth",
    })

    token = create_token(user_id, request.email, db_name)
    return TokenResponse(token=token, db_name=db_name, email=request.email)


# ──────────────────────────────────── Login ─────────────────────────────────────

@app.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest):
    auth_db = get_auth_db()
    user = await auth_db.users.find_one({"email": request.email})
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not verify_password(request.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    user_id = str(user["_id"])
    token = create_token(user_id, user["email"], user["db_name"])
    return TokenResponse(token=token, db_name=user["db_name"], email=user["email"])


# ──────────────────────────────────── Profile ───────────────────────────────────

@app.get("/me", response_model=UserProfile)
async def get_profile(current_user: dict = Depends(get_current_user)):
    auth_db = get_auth_db()
    user = await auth_db.users.find_one({"email": current_user["email"]})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return UserProfile(
        user_id=str(user["_id"]),
        email=user["email"],
        db_name=user["db_name"],
        buckets=user.get("buckets", []),
        merged_buckets=user.get("merged_buckets", []),
    )


# ──────────────────────────────── Bucket (Collection) CRUD ──────────────────────

@app.post("/buckets")
async def create_bucket(request: BucketRequest, current_user: dict = Depends(get_current_user)):
    bucket_name = request.bucket_name.strip()
    if not bucket_name:
        raise HTTPException(status_code=400, detail="Bucket name cannot be empty")

    # Disallow system collection names
    if bucket_name.startswith("_") or bucket_name.startswith("system."):
        raise HTTPException(status_code=400, detail="Invalid bucket name")

    db_name = current_user["db_name"]
    auth_db = get_auth_db()

    # Check if bucket already exists for this user
    user = await auth_db.users.find_one({"email": current_user["email"]})
    if bucket_name in user.get("buckets", []):
        raise HTTPException(status_code=409, detail=f"Bucket '{bucket_name}' already exists")

    # Create collection in user's database
    user_db = get_user_db(db_name)
    await user_db.create_collection(bucket_name)

    # Update user's bucket list
    await auth_db.users.update_one(
        {"email": current_user["email"]},
        {"$push": {"buckets": bucket_name}},
    )

    return {"status": "success", "bucket_name": bucket_name, "db_name": db_name}


@app.get("/buckets")
async def list_buckets(current_user: dict = Depends(get_current_user)):
    db_name = current_user["db_name"]
    user_db = get_user_db(db_name)
    auth_db = get_auth_db()
    collections = await user_db.list_collection_names()
    # Filter out internal collections (same prefixes ignored by graph builders)
    buckets = [c for c in collections if not c.startswith("_") and not c.startswith("system.") and not c.startswith("mg_")]
    # Document counts per bucket
    counts: dict = {}
    for b in buckets:
        counts[b] = await user_db[b].count_documents({})
    # Merged bucket names (virtual, no physical collection)
    user = await auth_db.users.find_one({"email": current_user["email"]})
    merged_buckets = user.get("merged_buckets", []) if user else []
    return {"buckets": buckets, "merged_buckets": merged_buckets, "counts": counts, "db_name": db_name}


@app.post("/buckets/merge")
async def merge_buckets(request: MergeRequest, current_user: dict = Depends(get_current_user)):
    if len(request.buckets) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 buckets to merge")
    auth_db = get_auth_db()
    user = await auth_db.users.find_one({"email": current_user["email"]})
    existing = user.get("buckets", [])
    for b in request.buckets:
        if b not in existing:
            raise HTTPException(status_code=404, detail=f"Bucket '{b}' not found")
    merged_name = "+".join(request.buckets)
    if merged_name in user.get("merged_buckets", []):
        raise HTTPException(status_code=409, detail=f"Merged bucket '{merged_name}' already exists")
    await auth_db.users.update_one(
        {"email": current_user["email"]},
        {"$push": {"merged_buckets": merged_name}},
    )
    return {"status": "success", "merged_name": merged_name}


@app.post("/buckets/unmerge")
async def unmerge_buckets(request: UnmergeRequest, current_user: dict = Depends(get_current_user)):
    auth_db = get_auth_db()
    user = await auth_db.users.find_one({"email": current_user["email"]})
    if request.merged_name not in user.get("merged_buckets", []):
        raise HTTPException(status_code=404, detail=f"Merged bucket '{request.merged_name}' not found")
    await auth_db.users.update_one(
        {"email": current_user["email"]},
        {"$pull": {"merged_buckets": request.merged_name}},
    )
    return {"status": "success", "unmerged": request.merged_name}


@app.delete("/buckets/{bucket_name}")
async def delete_bucket(bucket_name: str, current_user: dict = Depends(get_current_user)):
    db_name = current_user["db_name"]
    auth_db = get_auth_db()

    # Check ownership
    user = await auth_db.users.find_one({"email": current_user["email"]})
    if bucket_name not in user.get("buckets", []):
        raise HTTPException(status_code=404, detail=f"Bucket '{bucket_name}' not found")

    # Drop the collection
    user_db = get_user_db(db_name)
    await user_db.drop_collection(bucket_name)

    # Remove from user's bucket list
    await auth_db.users.update_one(
        {"email": current_user["email"]},
        {"$pull": {"buckets": bucket_name}},
    )

    return {"status": "success", "deleted": bucket_name}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("auth.main:app", host="0.0.0.0", port=8005, reload=True)
