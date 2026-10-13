# Dredge Frontend

A unified React + Vite frontend application that consolidates all Dredge backend services into one cohesive interface.

## Tech Stack
- **React 18** with TypeScript
- **Vite** build tool + dev server with multi-service proxy
- **Axios** with JWT interceptors
- **React Router** for SPA navigation
- **Framer Motion** for animations
- **Lucide React** for icons

## Getting Started

```bash
# Install dependencies
npm install

# Start the dev server (proxies all backend APIs)
npm run dev
```

The app will be available at **http://localhost:5173**.

## API Proxy Configuration

The Vite dev server proxies requests to backend services:

| Frontend Path | Backend Target      | Port |
|---------------|---------------------|------|
| `/api/auth`   | Auth Service        | 8005 |
| `/api/pdf`    | PDF Processor       | 8000 |
| `/api/graph`  | Mongo Graph         | 8001 |
| `/api/nlp`    | NLP to Mongo        | 8002 |
| `/api/image`  | Image Processor     | 8003 |
| `/api/csv`    | CSV Importer        | 8004 |

> **Note:** All backend services must be running for full functionality. Use `start_all.bat` from the project root to start everything at once.

## Pages

| Page            | Route        | Description                                      |
|-----------------|--------------|--------------------------------------------------|
| Auth            | `/auth`      | Login / Signup with JWT authentication            |
| Dashboard       | `/`          | Manage data buckets (collections)                 |
| Ingestion       | `/ingestion` | Upload PDFs, images, CSVs with progress tracking  |
| Graph Viewer    | `/graph`     | Explore schemas and entity relationships          |
| NLP Query       | `/nlp`       | Chat interface for natural language data queries  |

## Project Structure

```
frontend/
├── src/
│   ├── api/          # Axios client with auth interceptors
│   ├── components/   # Layout, sidebar, shared components
│   ├── context/      # AuthContext provider
│   ├── pages/        # Route-level page components
│   └── index.css     # Global design system
├── vite.config.ts    # Proxy configuration
└── package.json
```

## Building for Production

```bash
npm run build
```

Output will be in `dist/`. For production, configure a reverse proxy (e.g., Nginx) to route `/api/*` paths to the appropriate backend services.
