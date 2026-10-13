# Auth Service

JWT-based authentication with per-user MongoDB database isolation.

## Components

| File | Role |
|------|------|
| `main.py` | FastAPI endpoints for signup, login, profile, bucket CRUD (mounted at `/auth` via gateway) |
| `auth_utils.py` | Password hashing, JWT creation/verification, `get_current_user` dependency |
| `db.py` | MongoDB connection helpers |
| `models.py` | Pydantic request/response models |

## Running (Standalone)

```bash
python -m uvicorn auth.main:app --host 0.0.0.0 --port 8005 --reload
```

> **Note:** In production, this is mounted at `/auth` via `gateway.py`.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/signup` | Create account → returns JWT + user database |
| POST | `/login` | Authenticate → returns JWT |
| GET | `/me` | Get user profile |
| POST | `/buckets` | Create a collection (bucket) |
| GET | `/buckets` | List user's collections |
| DELETE | `/buckets/{name}` | Delete a collection |
