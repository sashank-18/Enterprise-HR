# Internal Benefits & SOP Assistant

An enterprise-grade, retrieval-augmented generation (RAG) assistant designed to help employees quickly find information regarding company benefits, Standard Operating Procedures (SOPs), and internal policies. The application leverages a robust role-based access control (RBAC) model, secure document ingestion, vector database integration, and local embedding models with external LLM inference.

---

## 🚀 Key Features

*   **Role-Based Access Control (RBAC):**
    *   **Employee:** Can view general policies, ask benefits/SOP questions, and view/delete their own chat history.
    *   **HR Manager:** Can upload/delete Employee and HR-level documents, view dashboard analytics, and ask questions.
    *   **Admin:** Complete permissions, including updating user roles, viewing all user chat histories, and uploading/deleting Admin-level documents.
*   **Security & Audit Logging:**
    *   **Double-Submit Cookie Pattern:** Complete CSRF token verification on all state-changing endpoints.
    *   **Secure Authentication:** JWT-based session tokens stored in `HTTPOnly`, `SameSite=Lax` cookies, combined with server-side session blacklisting and expiration checks.
    *   **Comprehensive Auditing:** Every critical action (login attempts, uploads, deletions, role updates, queries) is recorded in a MySQL-backed audit log.
    *   **Upload Validation:** Restricts files to PDF format, validates magic bytes signature (`%PDF`), limits size to 10 MB, and utilizes UUID-based naming to prevent directory traversal.
*   **Retrieval-Augmented Generation (RAG) Pipeline:**
    *   **Document Parsing:** PyMuPDF (`fitz`) with a `pypdf` fallback.
    *   **Text Chunking:** LangChain's `RecursiveCharacterTextSplitter` (chunk size 1000, overlap 200).
    *   **Embedding Generation:** Offline SentenceTransformer (`all-MiniLM-L6-v2`) generating 384-dimensional dense vectors.
    *   **Vector Database:** Pinecone vector search supporting metadata filtering for strict RBAC isolation.
    *   **Multi-LLM Support:** Groq API integration supporting **Llama 3 (8B)**, **DeepSeek-R1 (Llama 70B)**, and **Gemma 2 (9B)**.
    *   **Hallucination Prevention:** Strict instruction mapping and prompt filters that normalize responses to a pre-defined message if the question cannot be answered from the retrieved context.
*   **Analytics Dashboard:**
    *   **KPI Tracking:** Total document counts, total employees, total query counts, and most accessed policy types.
    *   **Visual Charts:** Query frequency trends (daily, weekly, monthly), document categorization distributions, and lists of the top asked questions.

---

## 🛠️ Technology Stack

| Component | Technology |
| :--- | :--- |
| **Backend Framework** | FastAPI (Python 3.10+) |
| **Relational Database** | MySQL (via SQLAlchemy & PyMySQL) |
| **Vector Search Engine** | Pinecone Vector Database |
| **Embeddings Model** | SentenceTransformer (`all-MiniLM-L6-v2` - Local) |
| **LLM Inference Provider** | Groq Cloud API |
| **Frontend UI** | Vanilla HTML5, Vanilla JavaScript, and Premium CSS3 |
| **PDF Processing** | PyMuPDF (`fitz`), `pypdf`, and LangChain Splitters |

---

## 📁 Repository Structure

```directory
├── backend/
│   ├── main.py              # Application entrypoint & FastAPI routes
│   ├── auth.py              # JWT token generation, CSRF verification, and RBAC helpers
│   ├── database.py          # SQLAlchemy engine, session creation, and database seeding
│   ├── models.py            # SQLAlchemy database schemas
│   ├── upload_service.py    # PDF validation, text extraction, and text chunking
│   ├── pinecone_service.py  # Local embedding generation & Pinecone vector operations
│   ├── groq_service.py      # LLM completion generation via Groq API
│   ├── rag.py               # Context assembly, RBAC vector filtering, and LLM orchestration
│   └── analytics.py         # Dashboard SQL query analytics generators
├── frontend/
│   ├── login.html           # Authentication portal (Login & Register views)
│   ├── dashboard.html       # Policy upload, document management, and admin console
│   ├── chatbot.html         # Context-aware conversation portal
│   └── analytics.html       # Analytics dashboard rendering KPIs and charts
├── documents/               # Secure non-executable storage for uploaded PDF files
├── requirements.txt         # Project python dependencies
└── .env                     # Local environment configurations (credentials, API keys)
```

---

## ⚙️ Configuration Setup

Create a `.env` file in the root directory and define the following variables:

```ini
# Relational Database Config
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_mysql_password
DB_NAME=hr_assistant

# Vector Database Config
PINECONE_API_KEY=your_pinecone_api_key
PINECONE_INDEX_NAME=hr-policies

# LLM Provider API Config
GROQ_API_KEY=your_groq_api_key

# Security Configuration
JWT_SECRET_KEY=generate_a_random_hex_string
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
```

---

## 🚀 Getting Started

### Prerequisites
*   Python 3.10 or higher
*   MySQL Server running locally or remotely
*   A Pinecone index configured with **384 dimensions** (metric: `cosine`)
*   Groq API Key (available on Groq Console)

### Installation Steps

1.  **Clone the repository and navigate to the project directory:**
    ```bash
    cd HR-project
    ```

2.  **Create and activate a virtual environment:**
    ```bash
    python -m venv venv
    
    # On Windows:
    venv\Scripts\activate
    
    # On macOS/Linux:
    source venv/bin/activate
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Database Initialization:**
    *   Make sure your MySQL server is running.
    *   FastAPI will automatically create the `hr_assistant` database and its tables, and seed roles/users on startup.

5.  **Run the application:**
    ```bash
    python backend/main.py
    ```
    Alternatively, using Uvicorn directly:
    ```bash
    uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
    ```

6.  **Access the application:**
    *   Open your browser and navigate to: [http://127.0.0.1:8000](http://127.0.0.1:8000)

---

## 👤 Seed Credentials

On initial startup, the database is pre-seeded with three default users corresponding to the system roles:

| Username | Email | Password | Role | Permissions |
| :--- | :--- | :--- | :--- | :--- |
| **admin** | `admin@company.com` | `admin123` | **Admin** | Full system administration, role updates, document upload/deletion, view all audit logs and chat histories. |
| **hr_manager** | `hr@company.com` | `hr_manager123` | **HR Manager** | Upload and delete documents (except Admin level), view analytics dashboard, ask questions. |
| **employee** | `employee@company.com` | `employee123` | **Employee** | Query general policies and benefits, view chat history. |

---

## 🛡️ RAG Pipeline & Security Overview

### Ingestion Flow
1.  **PDF Submission:** Admin/HR uploads a file.
2.  **File Sanitation:** Server checks size, validates extension, verifies magic bytes, and moves it under a randomly generated UUID name.
3.  **Chunking:** The document is split into 1000-character overlapping chunks.
4.  **Embedding:** Local `SentenceTransformer` converts the text chunks into 384-dimensional float arrays.
5.  **Upsert:** Vectors are sent to Pinecone with associated metadata containing the document's ID, name, department, type, and RBAC `access_level`.

### Retrieval Flow
1.  **Query Submission:** The user asks a question via the chat interface.
2.  **RBAC Filtering:** The system checks the user's role and constructs a metadata query filter (e.g. Employee can only search `access_level: "Employee"` chunks).
3.  **Vector Match:** Pinecone runs cosine similarity searches on the filtered subset.
4.  **LLM Assembly:** If matches exist, the server constructs a context block containing the document passages and forwards it along with strict boundary instructions to the Groq LLM API.
5.  **Answer & Citations:** The LLM's response is structured and returned with list citations (sources) or a normalized fallback message if no data exists.
