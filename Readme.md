# Run locally without Docker

This setup runs the same gateway and four workers as `docker-compose.prod.yml`. It uses local MongoDB, Redis, and disk backed S3 storage, the installed Ollama vision model, and the Groq key from `.env` for text processing. The existing `.env` contains an obsolete MongoDB address and a Spaces bucket that does not exist; `scripts/local-env.sh` overrides those values without changing your credentials file.

On this Mac, MongoDB, Redis, Python 3.11, Node.js, and Ollama are installed. Start the backing services if needed:

```sh
brew services start mongodb-community@8.0
brew services start redis
ollama serve
ollama pull qwen2.5vl:7b
```

Run `ollama serve` in its own terminal only if it is not already running. From the repository root, install the app dependencies:

```sh
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r auth/requirements.txt -r pdf_processor/requirements.txt -r image_processor/requirements.txt -r csv_importer/requirements.txt -r mongo_graph/requirements.txt -r nlp_to_mongo/requirements.txt
npm ci
cd frontend && npm ci && cd ..
```

The root `requirements.txt` is UTF-16 encoded, so use the service requirement files above. The Docker images use Python 3.11. Keep `.env` private; the Groq key in it must be valid.

Start the whole stack from the repository root:

```sh
bash scripts/start-local.sh
```

Open [http://127.0.0.1:5173/](http://127.0.0.1:5173/). To open the app from another computer on the same Wi-Fi, use `http://<Mac-LAN-IP>:5173/` (find the Mac's LAN IP with `ifconfig`). The gateway health endpoint is [http://127.0.0.1:8001/health](http://127.0.0.1:8001/health). Port 8000 is occupied by another process on this machine, so this project uses 8001. Vite forwards `/api` requests to the gateway.

The startup command runs the frontend, gateway, PDF worker, image worker, CSV worker, unified processor, and local S3 server. Logs are in `.local/logs/`. Press Ctrl-C in its terminal to stop them. MongoDB and Redis run as Homebrew services. Uploaded objects persist under `.local/s3/`; MongoDB and Redis use their normal local data directories.
