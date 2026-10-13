#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
source scripts/local-env.sh

if [[ ! -x .venv/bin/python || ! -d node_modules/s3rver || ! -x frontend/node_modules/.bin/vite ]]; then
  echo "Install the Python and npm dependencies in Readme.md first." >&2
  exit 1
fi

for port in 5001 8001 5173; do
  if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "Port $port is already in use. Stop the existing app before starting another copy." >&2
    exit 1
  fi
done

.venv/bin/python - <<'PY'
import os
from pymongo import MongoClient
import redis
MongoClient(os.environ['MONGO_URI'], serverSelectionTimeoutMS=2000).admin.command('ping')
redis.Redis(host=os.environ['REDIS_HOST'], port=int(os.environ['REDIS_PORT'])).ping()
PY

if ! ollama list | grep -q '^qwen2.5vl:7b '; then
  echo "Install and start Ollama, then run: ollama pull qwen2.5vl:7b" >&2
  exit 1
fi

mkdir -p .local/logs
pids=()
cleanup() {
  trap - EXIT INT TERM
  for pid in "${pids[@]}"; do kill "$pid" 2>/dev/null || true; done
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

node scripts/local-s3.cjs >.local/logs/s3.log 2>&1 & pids+=("$!")
for _ in {1..20}; do
  if .venv/bin/python - <<'PY' >/dev/null 2>&1
import boto3
boto3.client('s3', endpoint_url='http://127.0.0.1:5001', region_name='us-east-1',
             aws_access_key_id='S3RVER', aws_secret_access_key='S3RVER').head_bucket(Bucket='dredge-local')
PY
  then break; fi
  sleep 1
done
.venv/bin/python - <<'PY'
import boto3
boto3.client('s3', endpoint_url='http://127.0.0.1:5001', region_name='us-east-1',
             aws_access_key_id='S3RVER', aws_secret_access_key='S3RVER').head_bucket(Bucket='dredge-local')
PY

.venv/bin/python -m uvicorn gateway:gateway --host 127.0.0.1 --port 8001 >.local/logs/gateway.log 2>&1 & pids+=("$!")
for module in pdf_processor.worker_pipeline image_processor.worker_pipeline csv_importer.worker_pipeline unified_processor; do
  .venv/bin/python -m "$module" >".local/logs/$module.log" 2>&1 & pids+=("$!")
done
(cd frontend && exec ./node_modules/.bin/vite --host 0.0.0.0) >.local/logs/frontend.log 2>&1 & pids+=("$!")

echo "Dredge is starting at http://127.0.0.1:5173/"
echo "Logs: .local/logs/  |  Stop: Ctrl-C"
while :; do
  for pid in "${pids[@]}"; do
    if ! kill -0 "$pid" 2>/dev/null; then
      echo "A local service exited; check .local/logs/." >&2
      exit 1
    fi
  done
  sleep 2
done
