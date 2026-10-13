from pydantic import BaseModel, EmailStr
from typing import List


class SignupRequest(BaseModel):
    email: EmailStr
    password: str  # min 6 characters enforced in endpoint


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class BucketRequest(BaseModel):
    bucket_name: str


class TokenResponse(BaseModel):
    token: str
    db_name: str
    email: str


class MergeRequest(BaseModel):
    buckets: List[str]  # 2+ physical bucket names to merge

class UnmergeRequest(BaseModel):
    merged_name: str  # the "+"-joined string to unmerge

class UserProfile(BaseModel):
    user_id: str
    email: str
    db_name: str
    buckets: List[str] = []
    merged_buckets: List[str] = []
