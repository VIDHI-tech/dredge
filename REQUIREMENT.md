 # Dredge — Frontend Requirements Document

> **Version**: 1.0  
> **Date**: 2026-03-03  
> **Backend Stack**: FastAPI (Python), MongoDB Atlas, Redis Cache, DigitalOcean Spaces  
> **Frontend Stack**: React + TypeScript + Vite  

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Authentication & User Model](#2-authentication--user-model)
3. [API Proxy Routing](#3-api-proxy-routing)
4. [Pages & Features](#4-pages--features)
   - [Auth Page](#41-auth-page)
   - [Dashboard](#42-dashboard)
   - [Ingestion](#43-ingestion-page)
   - [Graph Viewer (Sunburst + User Tree)](#44-graph-viewer)
   - [NLP Query](#45-nlp-query)
   - [Data Analyst](#46-data-analyst)
5. [API Reference](#5-api-reference)
   - [Auth Service](#51-auth-service-port-8005)
   - [PDF Processor](#52-pdf-processor-port-8000)
   - [CSV Importer](#53-csv-importer-port-8004)
   - [Image Processor](#54-image-processor-port-8003)
   - [Graph Service](#55-graph-service-port-8001)
   - [NLP Query Service](#56-nlp-query-service-port-8002)
   - [Data Analyst Service](#57-data-analyst-service-port-8006)
6. [Key Interaction Flows](#6-key-interaction-flows)
7. [Design Constraints & Notes](#7-design-constraints--notes)

---

## 1. Architecture Overview

Dredge is a **multi-service** platform with **7 independent backend services** and a unified React frontend.

```
┌─────────────────────────────────────────────────────────────┐
│                   React Frontend (Vite)                     │
│     /auth  /dashboard  /ingestion  /graph  /nlp  /analyst  │
└────────────────────────┬────────────────────────────────────┘
                         │  Vite Dev Proxy (/api/*)
    ┌────────────────────┼────────────────────────────┐
    │                    │                            │
    ▼                    ▼                            ▼
┌────────┐  ┌────────────────┐  ┌──────────────┐  ┌──────────┐
│  Auth  │  │ PDF Processor  │  │ CSV Importer │  │  Image   │
│ :8005  │  │     :8000      │  │    :8004     │  │ Proc :8003│
└────────┘  └────────────────┘  └──────────────┘  └──────────┘
    ┌────────────────┐  ┌───────────────┐  ┌──────────────────┐
    │ Graph Service   │  │  NLP Query   │  │  Data Analyst    │
    │     :8001       │  │    :8002     │  │     :8006        │
    └────────────────┘  └───────────────┘  └──────────────────┘
                         │
                    ┌────┴─────┐
                    │ MongoDB  │  (per-user databases)
                    │  Atlas   │
                    └──────────┘
```

### Key Principles

- **Each user gets their own MongoDB database** — `user_<short_id>`
- **Buckets = MongoDB Collections** — Creating a bucket in Dashboard creates a new collection in the user's DB
- **Active Bucket** — Setting a bucket as active means NLP querying and all ingestion targets go to that bucket/collection
- **JWT Auth** — All API requests (except signup/login) require `Authorization: Bearer <token>` header

---

## 2. Authentication & User Model

Authentication uses **JWT Bearer tokens**. The token payload contains:

| Field     | Type   | Description                        |
|-----------|--------|------------------------------------|
| `user_id` | string | MongoDB ObjectId of the user       |
| `email`   | string | User's email                       |
| `db_name` | string | User's unique database name        |

On signup, a unique database is created for the user: `user_<12-char-hex-id>`.

**Token Storage**: `localStorage.getItem('token')`  
**Header Format**: `Authorization: Bearer <token>`

---

## 3. API Proxy Routing

The Vite dev server proxies all `/api/*` requests to the appropriate backend service:

| Frontend Path     | Backend Target          | Rewrite Rule                |
|-------------------|-------------------------|-----------------------------|
| `/api/auth/*`     | `http://localhost:8005`  | Strip `/api/auth` prefix    |
| `/api/pdf/*`      | `http://localhost:8000`  | Strip `/api/pdf` prefix     |
| `/api/csv/*`      | `http://localhost:8004`  | Strip `/api/csv` prefix     |
| `/api/image/*`    | `http://localhost:8003`  | Strip `/api/image` prefix   |
| `/api/graph/*`    | `http://localhost:8001`  | Strip `/api/graph` prefix   |
| `/api/nlp/*`      | `http://localhost:8002`  | Strip `/api/nlp` prefix     |

> **Example**: Frontend calls `/api/pdf/upload` → Vite proxies to `http://localhost:8000/upload`

---

## 4. Pages & Features

### 4.1 Auth Page

**Route**: `/auth`  
**Purpose**: User signup and login

| Feature        | Description                                                  |
|----------------|--------------------------------------------------------------|
| Signup Form    | Email + Password (min 6 chars). Creates user + unique DB.    |
| Login Form     | Email + Password. Returns JWT token.                         |
| Token Storage  | On success, store `token`, `db_name`, `email` in localStorage |
| Redirect       | After auth → redirect to `/` (Dashboard)                     |

---

### 4.2 Dashboard

**Route**: `/` (index)  
**Purpose**: Bucket (collection) management

| Feature              | Description                                                                                       |
|----------------------|---------------------------------------------------------------------------------------------------|
| List Buckets         | Shows all collections (buckets) in the user's database                                            |
| Create Bucket        | Text input + "Create" button → creates a new MongoDB collection in the user's DB                  |
| Delete Bucket        | Trash icon per bucket → drops the collection and removes from user's bucket list                   |
| **Set Active Bucket**| **Clicking/selecting a bucket sets it as the "active" bucket** — all ingestion and NLP queries target this bucket |
| Refresh              | Re-fetch bucket list                                                                              |

> **IMPORTANT**: The active bucket concept is critical. When a bucket is active:
> - All file ingestion (PDF, CSV, Image) saves data to this collection
> - NLP queries run against this collection
> - The active bucket name should be visually highlighted and persisted (e.g., in context/state)

---

### 4.3 Ingestion Page

**Route**: `/ingestion`  
**Purpose**: Upload files (PDF, CSV, Images), process them, review output, edit, and save to MongoDB

#### Sub-tabs / Upload Targets

| Tab     | Accepted Files | Upload Endpoint         | Backend Port |
|---------|---------------|-------------------------|--------------|
| PDF     | `.pdf`        | `POST /api/pdf/upload`  | 8000         |
| CSV     | `.csv`        | `POST /api/csv/convert` | 8004         |
| Image   | `image/*`     | `POST /api/image/upload`| 8003         |

#### Ingestion Workflow (applies to ALL three processors)

```
Upload File(s)  →  Poll Status  →  View JSON Result  →  Edit (Table/JSON)  →  Verify & Save to MongoDB
      │                │                  │                     │                       │
  POST /upload    GET /status/{id}   GET /result/{id}    Client-side edit     POST /save-to-mongo/{id}
```

**Step-by-step**:

1. **Upload**: User selects files → `POST /upload` (or `/convert` for CSV) → returns `doc_id` + `status: "queued"`
2. **Processing**: Poll `GET /status/{doc_id}` every few seconds until status is `"done"`
3. **View Result**: Fetch `GET /result/{doc_id}` → returns the extracted JSON data
4. **Visualize as Table**: The JSON output **MUST be displayed in a tabular format** (not raw JSON only)
   - For all three processors (PDF, CSV, Image), the result is an array of objects
   - Render as a data table with columns derived from object keys
5. **Edit**: User can edit the data **before** saving:
   - **Table View editing**: Inline cell editing in the table
   - **JSON View editing**: Raw JSON editor (textarea or code editor)
   - User can toggle between Table View and JSON View
   - An **"Edit" button** enables edit mode
6. **Verify & Save**: 
   - User reviews the (possibly edited) data
   - Clicks **"Verify"** → data is confirmed
   - Clicks **"Save to MongoDB"** → `POST /save-to-mongo/{doc_id}?collection_name=<active_bucket>`
   - The `collection_name` query parameter should be the **currently active bucket**

#### Processed Documents List

- `GET /list-processed` shows previously processed documents
- Each doc can be re-viewed or re-saved

---

### 4.4 Graph Viewer

**Route**: `/graph`  
**Purpose**: Visualize MongoDB data as Sunburst Graph and User Tree, with drill-down

#### Two Visualization Modes (each should have its own dedicated section/tab):

##### A) Sunburst Graph

- **Build**: `POST /api/graph/api/graph` — builds a sunburst tree from all collections
- **Display**: D3.js interactive sunburst chart
- **Interaction Flow**:
  1. User sees the sunburst chart with segments representing fields/concepts
  2. **Click on a value/segment** → opens a **data table** showing documents matching that field/value
     - API call: `POST /api/graph/api/query-field` with `{ field, value }`
     - Response includes `rows`, `columns`, `total`
  3. **Click on a row in the table** → shows **full document detail** for that row
     - Displays all key-value pairs of the selected document
  4. **Back navigation**: User can go back from row detail → table → sunburst

##### B) User Tree Graph

- **Build**: `POST /api/graph/api/user-tree` — builds a user identity tree  
- **Display**: D3.js collapsible tree layout
- **Separate page/tab** from Sunburst — should be its own section

#### Supporting Features

| Feature         | API Call                          | Description                                |
|-----------------|-----------------------------------|--------------------------------------------|
| Schema Keys     | `GET /api/graph/api/schema`       | Lists all field keys for search/filter     |
| Schema Cache    | `GET /api/graph/api/schema-cache` | Full schema with types                     |
| Clear Cache     | `POST /api/graph/api/cache/clear` | Clears sunburst/usertree/schema/llm cache  |
| Fetch Document  | `GET /api/graph/api/document/{collection}/{doc_id}` | Full document data     |

---

### 4.5 NLP Query

**Route**: `/nlp`  
**Purpose**: Natural language querying of MongoDB data — chat-style interface

| Feature              | Description                                                                           |
|----------------------|---------------------------------------------------------------------------------------|
| Collection Selector  | User selects which collection (bucket) to query — **defaults to active bucket**       |
| Chat Interface       | User types natural language query, gets back results                                  |
| Query Conversion     | Backend converts NLP → MongoDB aggregation pipeline                                   |
| **Tabular Results**  | **Results MUST be displayed as a table** (not raw JSON)                                |
| Row Expansion        | Clicking a row expands to show full document detail                                   |
| Pagination           | Results are paginated (default page_size: 50)                                         |
| Generated Pipeline   | Optionally show the generated MongoDB pipeline to the user                            |

---


## 5. API Reference

> **Auth**: All endpoints except `/signup` and `/login` require `Authorization: Bearer <token>` header.

---

### 5.1 Auth Service (Port 8005)

**Proxy prefix**: `/api/auth`

#### `POST /signup`

Creates a new user and their dedicated database.

**Request Body**:
```json
{
  "email": "user@example.com",
  "password": "securepassword"
}
```

**Response** `200`:
```json
{
  "token": "eyJhbGciOiJIUzI1NiIs...",
  "db_name": "user_a1b2c3d4e5f6",
  "email": "user@example.com"
}
```

**Errors**:
| Code | Detail                          |
|------|---------------------------------|
| 400  | Password must be at least 6 characters |
| 409  | Email already registered        |

---

#### `POST /login`

Authenticates an existing user.

**Request Body**:
```json
{
  "email": "user@example.com",
  "password": "securepassword"
}
```

**Response** `200`:
```json
{
  "token": "eyJhbGciOiJIUzI1NiIs...",
  "db_name": "user_a1b2c3d4e5f6",
  "email": "user@example.com"
}
```

**Errors**:
| Code | Detail                     |
|------|----------------------------|
| 401  | Invalid email or password  |

---

#### `GET /me`

Returns the current user's profile.

**Headers**: `Authorization: Bearer <token>`

**Response** `200`:
```json
{
  "user_id": "665a1b2c3d4e5f6a7b8c9d0e",
  "email": "user@example.com",
  "db_name": "user_a1b2c3d4e5f6",
  "buckets": ["sales_data", "invoices", "customers"]
}
```

---

#### `POST /buckets`

Creates a new bucket (MongoDB collection) in the user's database.

**Headers**: `Authorization: Bearer <token>`

**Request Body**:
```json
{
  "bucket_name": "sales_data"
}
```

**Response** `200`:
```json
{
  "status": "success",
  "bucket_name": "sales_data",
  "db_name": "user_a1b2c3d4e5f6"
}
```

**Errors**:
| Code | Detail                                |
|------|---------------------------------------|
| 400  | Bucket name cannot be empty           |
| 400  | Invalid bucket name (starts with _ or system.) |
| 409  | Bucket 'X' already exists             |

---

#### `GET /buckets`

Lists all buckets (collections) in the user's database.

**Headers**: `Authorization: Bearer <token>`

**Response** `200`:
```json
{
  "buckets": ["sales_data", "invoices", "customers"],
  "db_name": "user_a1b2c3d4e5f6"
}
```

---

#### `DELETE /buckets/{bucket_name}`

Deletes a bucket and all its data.

**Headers**: `Authorization: Bearer <token>`

**Response** `200`:
```json
{
  "status": "success",
  "deleted": "sales_data"
}
```

**Errors**:
| Code | Detail                      |
|------|-----------------------------|
| 404  | Bucket 'X' not found        |

---

### 5.2 PDF Processor (Port 8000)

**Proxy prefix**: `/api/pdf`

#### `POST /upload`

Uploads one or more PDF files for processing.

**Headers**: `Authorization: Bearer <token>`  
**Content-Type**: `multipart/form-data`  
**Field**: `files` (multiple files allowed)

**Response** `200`:
```json
{
  "results": [
    {
      "doc_id": "550e8400-e29b-41d4-a716-446655440000",
      "status": "queued",
      "filename": "invoice.pdf"
    }
  ]
}
```

**Error entry in results array**:
```json
{
  "filename": "readme.txt",
  "status": "error",
  "detail": "Only PDF files are allowed."
}
```

---

#### `GET /status/{doc_id}`

Polls the processing status of a document.

**Headers**: `Authorization: Bearer <token>`

**Response** `200`:
```json
{
  "status": "processing",
  "phase": "extracting",
  "percent": 45
}
```

**Possible `status` values**: `"queued"`, `"processing"`, `"done"`, `"error"`, `"unknown"`

---

#### `GET /result/{doc_id}`

Fetches the processed JSON output.

**Headers**: `Authorization: Bearer <token>`

**Response** `200`: The extracted JSON data (array of objects or object)
```json
[
  {
    "invoice_number": "INV-001",
    "date": "2026-01-15",
    "total": 1500.00,
    "items": [...]
  }
]
```

**Errors**:
| Code | Detail           |
|------|------------------|
| 404  | Result not found |

---

#### `GET /list-processed`

Lists all previously processed documents.

**Headers**: `Authorization: Bearer <token>`

**Response** `200`:
```json
{
  "documents": [
    {
      "doc_id": "550e8400-...",
      "filename": "invoice.pdf",
      "processed_at": "2026-01-15T10:30:00Z"
    }
  ]
}
```

---

#### `POST /save-to-mongo/{doc_id}`

Saves processed data to MongoDB in the specified collection.

**Headers**: `Authorization: Bearer <token>`  
**Query Params**:
| Param            | Type   | Default  | Description                            |
|------------------|--------|----------|----------------------------------------|
| `collection_name`| string | `"test1"`| Target collection (should be active bucket) |

**Request Body**: The JSON data to save (array of objects or single object)
```json
[
  {
    "invoice_number": "INV-001",
    "date": "2026-01-15",
    "total": 1500.00
  }
]
```

**Response** `200`:
```json
{
  "status": "success",
  "inserted_ids": ["665a1b2c3d4e5f6a7b8c9d0e"]
}
```

> **Note**: Each document gets additional metadata: `doc_id`, `timestamp`, `source_type: "pdf_processor"`

---

### 5.3 CSV Importer (Port 8004)

**Proxy prefix**: `/api/csv`

#### `POST /convert`

Uploads one or more CSV files for processing.

**Headers**: `Authorization: Bearer <token>`  
**Content-Type**: `multipart/form-data`  
**Field**: `files` (multiple files allowed)

**Response** `200`:
```json
{
  "results": [
    {
      "doc_id": "550e8400-...",
      "status": "queued",
      "filename": "data.csv"
    }
  ]
}
```

---

#### `GET /status/{doc_id}`

Same interface as PDF Processor. See [PDF Status](#get-statusdoc_id).

---

#### `GET /result/{doc_id}`

Same interface as PDF Processor. Returns the CSV data converted to JSON (array of row objects).

---

#### `GET /list-processed`

Same interface as PDF Processor.

---

#### `POST /save-to-mongo/{doc_id}`

Same interface as PDF Processor. `source_type` is `"csv_importer"`.

---

### 5.4 Image Processor (Port 8003)

**Proxy prefix**: `/api/image`

#### `POST /upload`

Uploads one or more image files for processing.

**Headers**: `Authorization: Bearer <token>`  
**Content-Type**: `multipart/form-data`  
**Field**: `files` (multiple files allowed, must be `image/*` MIME type)

**Response** `200`:
```json
{
  "results": [
    {
      "doc_id": "550e8400-...",
      "status": "queued",
      "filename": "receipt.jpg"
    }
  ]
}
```

---

#### `GET /status/{doc_id}`, `GET /result/{doc_id}`, `GET /list-processed`, `POST /save-to-mongo/{doc_id}`

Same interface as PDF Processor. `source_type` is `"image_processor"`.

---

### 5.5 Graph Service (Port 8001)

**Proxy prefix**: `/api/graph`

> **Note**: This service has its own `/api/*` prefix internally, so frontend calls `api/graph/api/...`

---

#### `GET /api/databases`

Returns available databases (user's own DB).

**Headers**: `Authorization: Bearer <token>`

**Response** `200`:
```json
{
  "databases": ["user_a1b2c3d4e5f6"]
}
```

---

#### `GET /api/schema`

Returns field keys found across all collections.

**Headers**: `Authorization: Bearer <token>`

**Response** `200`:
```json
{
  "keys": ["name", "email", "phone", "address", "invoice_number", "total"]
}
```

---

#### `GET /api/schema-cache`

Returns the full schema with types for all collections.

**Headers**: `Authorization: Bearer <token>`

**Response** `200`:
```json
{
  "db": "user_a1b2c3d4e5f6",
  "collections": ["sales_data", "invoices"],
  "schema": {
    "sales_data": {
      "name": { "type": "string", "example": "John" },
      "total": { "type": "number", "example": 1500 }
    }
  }
}
```

---

#### `POST /api/graph`

Builds the sunburst tree visualization data.

**Headers**: `Authorization: Bearer <token>`

**Request Body**:
```json
{
  "target_db": "test",
  "use_llm": true,
  "force_refresh": false
}
```

> **Note**: `target_db` is overridden server-side to the user's `db_name` from the JWT token.

**Response** `200`:
```json
{
  "tree": {
    "name": "root",
    "children": [
      {
        "name": "Concept: Contact Info",
        "children": [
          {
            "name": "email",
            "children": [
              { "name": "john@example.com", "value": 3 }
            ]
          }
        ]
      }
    ]
  },
  "field_groups": [
    {
      "concept": "Contact Info",
      "fields": ["email", "contact_email", "user_email"]
    }
  ]
}
```

---

#### `POST /api/query-field`

Queries documents matching a specific field and optional value. Used when clicking on sunburst segments.

**Headers**: `Authorization: Bearer <token>`

**Request Body**:
```json
{
  "db": "test",
  "field": "email",
  "value": "john@example.com",
  "concept": "Contact Info"
}
```

**Response** `200`:
```json
{
  "rows": [
    {
      "_id": "665a1b2c...",
      "_collection": "invoices",
      "email": "john@example.com",
      "name": "John Doe",
      "total": 1500
    }
  ],
  "columns": ["_id", "_collection", "email", "name", "total"],
  "total": 15,
  "equivalent_fields": ["email", "contact_email", "user_email"]
}
```

---

#### `GET /api/document/{collection}/{doc_id}`

Fetches a single document's full data. Used when clicking a row in the query results table.

**Headers**: `Authorization: Bearer <token>`

**Response** `200`: Full document object
```json
{
  "_id": "665a1b2c...",
  "name": "John Doe",
  "email": "john@example.com",
  "phone": "+1234567890",
  "items": [{ "desc": "Widget", "qty": 5 }]
}
```

---

#### `POST /api/user-tree`

Builds the user identity tree visualization data.

**Headers**: `Authorization: Bearer <token>`

**Request Body**:
```json
{
  "target_db": "test",
  "use_llm": true,
  "force_refresh": false
}
```

**Response** `200`:
```json
{
  "tree": {
    "name": "Users",
    "children": [
      {
        "name": "john@example.com",
        "children": [
          { "name": "Invoice #001", "value": 1 },
          { "name": "Invoice #002", "value": 1 }
        ]
      }
    ]
  }
}
```

---

#### `POST /api/cache/clear`

Clears cache entries.

**Headers**: `Authorization: Bearer <token>`

**Request Body**:
```json
{
  "target": "all"
}
```

**Valid targets**: `"sunburst"`, `"usertree"`, `"schema"`, `"llm"`, `"all"`

**Response** `200`:
```json
{
  "status": "success",
  "target": "all",
  "keys_cleared": 12
}
```

---

### 5.6 NLP Query Service (Port 8002)

**Proxy prefix**: `/api/nlp`

#### `POST /convert`

Converts a natural language query to a MongoDB aggregation pipeline and optionally executes it.

**Headers**: `Authorization: Bearer <token>`

**Request Body**:
```json
{
  "text": "show me all invoices over $1000",
  "collection": "invoices",
  "db_name": "test",
  "execute": true,
  "page": 1,
  "page_size": 50
}
```

> **Note**: `db_name` is overridden server-side to the user's `db_name` from JWT token.

**Response** `200`:
```json
{
  "mongo_query": [
    { "$match": { "total": { "$gt": 1000 } } }
  ],
  "explanation": "Generated aggregation pipeline from schema context.",
  "results": [
    {
      "_id": "665a1b2c...",
      "invoice_number": "INV-001",
      "total": 1500.00,
      "date": "2026-01-15"
    }
  ],
  "total_count": 25,
  "page": 1,
  "page_size": 50
}
```

> **IMPORTANT**: The `results` array should be rendered as a **TABLE**, with:
> - Column headers derived from the keys of the result objects
> - Clicking a row expands/shows full document detail
> - Pagination controls based on `total_count`, `page`, `page_size`

---

#### `GET /schema/{collection_name}`

Returns the cached schema for a specific collection.

**Headers**: `Authorization: Bearer <token>`

**Response** `200`:
```json
{
  "collection": "invoices",
  "schema": {
    "invoice_number": { "type": "string", "example": "INV-001" },
    "total": { "type": "number", "example": 1500 }
  },
  "summary": "Fields: invoice_number (string), total (number), ..."
}
```

---

#### `POST /refresh-schema`

Force-refreshes the schema cache for a collection.

**Headers**: `Authorization: Bearer <token>`

**Request Body**:
```json
{
  "collection": "invoices",
  "db_name": "test"
}
```

**Response** `200`:
```json
{
  "status": "success",
  "field_count": 8
}
```

---

### 5.7 Data Analyst Service (Port 8006)

**Proxy prefix**: Needs to be added (currently not in vite proxy config — suggest `/api/analyst`)

#### `POST /analyze`

Sends an analysis prompt and returns a streaming response.

**Headers**: `Authorization: Bearer <token>`

**Request Body**:
```json
{
  "prompt": "What are the top 5 customers by revenue?",
  "collection": "sales_data"
}
```

**Response**: `text/plain` **streaming** (chunked transfer encoding)  
Each chunk is a text fragment that should be appended to the UI in real-time.

---

#### `GET /health`

Health check endpoint. No auth required.

**Response** `200`:
```json
{
  "status": "healthy"
}
```

---

## 6. Key Interaction Flows

### Flow 1: Ingestion → View → Edit → Save

```
┌──────────┐    ┌──────────────┐    ┌─────────────┐    ┌──────────────┐    ┌───────────┐
│  Upload   │───▶│ Poll Status  │───▶│ View Result │───▶│  Edit Data   │───▶│   Save    │
│  File(s)  │    │  (polling)   │    │  (Table)    │    │ Table / JSON │    │ to Mongo  │
└──────────┘    └──────────────┘    └─────────────┘    └──────────────┘    └───────────┘
                                          │
                                    JSON output is
                                    displayed as a
                                    TABLE for all 3
                                    processors
```

**Edit capabilities**:
- **Edit Button**: Toggles edit mode on the table/JSON view
- **Table View**: Inline cell editing — click a cell to edit its value
- **JSON View**: Full JSON editor — user can edit raw JSON
- **Toggle**: Switch between Table View ↔ JSON View while editing
- **Verify Button**: Confirms the edits look correct
- **Save to MongoDB Button**: Sends the (edited) data to `POST /save-to-mongo/{doc_id}?collection_name=<active_bucket>`

### Flow 2: Sunburst Drill-Down

```
┌───────────────┐    ┌─────────────────┐    ┌──────────────────┐
│   Sunburst    │───▶│  Data Table     │───▶│  Row Detail      │
│  Click Value  │    │  (field=value)  │    │  (full document) │
└───────────────┘    └─────────────────┘    └──────────────────┘
     ▲                      ▲                       │
     │                      └───── Back ────────────┘
     └──────────────── Back ────────────────────────┘
```

### Flow 3: NLP Query

```
┌────────────────┐    ┌───────────────┐    ┌──────────────────┐
│  Type Natural  │───▶│ Table Results │───▶│  Expanded Row    │
│  Language Query│    │ (paginated)   │    │  (full document) │
└────────────────┘    └───────────────┘    └──────────────────┘
```

---

## 7. Design Constraints & Notes

### Per-User Database Isolation
- Every user gets their own MongoDB database (`user_<id>`)
- Users can only see/query their own data
- The `db_name` is encoded in the JWT token and enforced server-side

### Active Bucket System
- The Dashboard allows creating, deleting, and selecting buckets
- An **"active bucket"** must be tracked in frontend state (React Context or similar)
- The active bucket determines:
  - Which `collection_name` is used in `save-to-mongo` calls
  - Which collection is pre-selected in NLP Query
  - Which collection is used for Data Analyst queries
- Active bucket should be **visually indicated** in the UI (highlighted, badge, etc.)

### Tabular Display Requirements
- **Ingestion results**: ALL processor outputs (PDF, CSV, Image) must render as tables
- **NLP query results**: Must render as tables with expandable rows
- **Sunburst drill-down**: Query results shown as tables
- Tables should handle nested objects gracefully (e.g., show `[Object]` or expand inline)

### Edit-Before-Save Feature
- Users must be able to **edit extracted data before saving** to MongoDB
- Two editing modes: **Table View** (inline cell editing) and **JSON View** (raw editor)
- An explicit **Edit** button to enter edit mode
- Changes are client-side only until **Save to MongoDB** is clicked

### Page Ownership
| Page            | Route       | Standalone Section |
|-----------------|-------------|-------------------|
| Sunburst Graph  | `/graph`    | Yes — its own tab/section within graph page |
| User Tree Graph | `/graph`    | Yes — its own tab/section within graph page |
| NLP Query       | `/nlp`      | Yes — standalone page |
| Ingestion       | `/ingestion`| Yes — with sub-tabs for PDF/CSV/Image |
| Dashboard       | `/`         | Yes — bucket management |

### Error Handling
- All API errors return `{ "detail": "error message" }` with appropriate HTTP status codes
- Frontend should display user-friendly error messages
- Network errors should show retry options

