# Dredge — Windows Local Setup Without Docker

## 1. Install required software

Install:

1. Git
2. Node.js 22 or newer
3. Python 3.11 x64
4. MongoDB Community Server
5. Redis for Windows or Memurai Developer Edition

Confirm the command-line tools:

```powershell
git --version
node --version
npm --version
py -3.11 --version
```

MongoDB must listen on `127.0.0.1:27017`, and Redis must listen on
`127.0.0.1:6379`.

## 2. Download the project

```powershell
git clone <your-repository-url>
cd dredge
```

Alternatively, copy the complete project directory to the other computer.

## 3. Generate a new Groq key

1. Open the Groq API console.
2. Revoke any key that has been publicly shared.
3. Generate a new API key.
4. Do not share or commit the new key.

## 4. Create `.env`

Create `dredge\.env` with the following content:

```env
GROQ_API_KEY=gsk_your_actual_new_groq_key

MONGO_URI=mongodb://127.0.0.1:27017

REDIS_HOST=127.0.0.1
REDIS_PORT=6379
REDIS_PASSWORD=

DO_SPACES_REGION=us-east-1
DO_SPACES_ENDPOINT=http://127.0.0.1:5001
DO_SPACES_BUCKET=dredge-local
DO_SPACES_KEY=S3RVER
DO_SPACES_SECRET=S3RVER

TEXT_MODEL_ID=qwen/qwen3.8-27b
IMAGE_MODEL_PROVIDER=groq
IMAGE_MODEL_ID=meta-llama/llama-4-scout-17b-16e-instruct

JWT_SECRET=replace-with-a-random-string-at-least-32-characters
```

Replace only `GROQ_API_KEY` and `JWT_SECRET`. Keep the `S3RVER` values
unchanged because they belong to the local S3 emulator.

## 5. Create the Python environment

Run from the project root:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
```

## 6. Install Python dependencies

```powershell
.venv\Scripts\python.exe -m pip install `
  -r auth\requirements.txt `
  -r pdf_processor\requirements.txt `
  -r image_processor\requirements.txt `
  -r csv_importer\requirements.txt `
  -r mongo_graph\requirements.txt `
  -r nlp_to_mongo\requirements.txt
```

Do not use the root `requirements.txt`.

## 7. Install Node.js dependencies

```powershell
npm ci
cd frontend
npm ci
cd ..
```

## 8. Start MongoDB

If MongoDB is installed as a Windows service:

```powershell
Start-Service MongoDB
```

Verify it:

```powershell
Get-NetTCPConnection -State Listen -LocalPort 27017
```

You can also start MongoDB from the Windows Services application.

## 9. Start Redis

Start Redis or Memurai using its Windows service or executable.

Verify it:

```powershell
Get-NetTCPConnection -State Listen -LocalPort 6379
```

## 10. Start local S3 storage

Open PowerShell in the project root:

```powershell
node scripts\local-s3.cjs
```

Expected address: `http://127.0.0.1:5001`.

Keep this terminal open.

## 11. Start the API gateway

Open another PowerShell terminal:

```powershell
cd <path-to-dredge>
.venv\Scripts\python.exe -m uvicorn gateway:gateway --host 127.0.0.1 --port 8001
```

Test it by opening `http://127.0.0.1:8001/health`.

Expected response:

```json
{
  "status": "ok",
  "service": "dredge-gateway"
}
```

## 12. Start the PDF worker

Open another PowerShell terminal:

```powershell
cd <path-to-dredge>
.venv\Scripts\python.exe -m pdf_processor.worker_pipeline
```

## 13. Start the image worker

Open another PowerShell terminal:

```powershell
cd <path-to-dredge>
.venv\Scripts\python.exe -m image_processor.worker_pipeline
```

## 14. Start the CSV worker

Open another PowerShell terminal:

```powershell
cd <path-to-dredge>
.venv\Scripts\python.exe -m csv_importer.worker_pipeline
```

## 15. Start the unified processor

Open another PowerShell terminal:

```powershell
cd <path-to-dredge>
.venv\Scripts\python.exe -m unified_processor
```

## 16. Start the frontend

Open another PowerShell terminal:

```powershell
cd <path-to-dredge>\frontend
npm run dev -- --host 0.0.0.0 --port 5173
```

Open `http://127.0.0.1:5173`.

## 17. Verify all services

| Service | Address |
|---|---|
| Frontend | `http://127.0.0.1:5173` |
| API gateway | `http://127.0.0.1:8001` |
| MongoDB | `127.0.0.1:27017` |
| Redis | `127.0.0.1:6379` |
| Local S3 | `http://127.0.0.1:5001` |

Check the ports:

```powershell
Get-NetTCPConnection -State Listen |
  Where-Object LocalPort -in 5173,8001,27017,6379,5001 |
  Select-Object LocalAddress,LocalPort,OwningProcess
```

## 18. Stop the application

Press `Ctrl+C` in every application terminal:

- Frontend
- Gateway
- Local S3
- PDF worker
- Image worker
- CSV worker
- Unified processor

MongoDB and Redis can remain running as Windows services. To stop MongoDB:

```powershell
Stop-Service MongoDB
```

Stop Redis or Memurai using its corresponding Windows service name.

