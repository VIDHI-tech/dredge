#!/usr/bin/env bash
# Source this file before starting the API or workers on this machine.
export MONGO_URI=mongodb://127.0.0.1:27017
export REDIS_HOST=127.0.0.1
export REDIS_PORT=6379
export REDIS_PASSWORD=
export DO_SPACES_REGION=us-east-1
export DO_SPACES_ENDPOINT=http://127.0.0.1:5001
export DO_SPACES_BUCKET=dredge-local
export DO_SPACES_KEY=S3RVER
export DO_SPACES_SECRET=S3RVER
export TEXT_MODEL_ID=qwen/qwen3.8-27b
export IMAGE_MODEL_PROVIDER=ollama
export IMAGE_MODEL_ID=qwen2.5vl:7b
