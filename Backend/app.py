import sys
import os
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Add the current folder and project root to sys.path to support running the script directly
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database import init_db_and_seed

# Import routers
from backend.routers.auth import router as auth_router
from backend.routers.documents import router as documents_router
from backend.routers.chat import router as chat_router
from backend.routers.tickets import router as tickets_router
from backend.routers.analytics import router as analytics_router
from backend.routers.users import router as users_router
from backend.routers.pages import router as pages_router

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Main")

app = FastAPI(
    title="Internal Benefits & SOP Assistant",
    description="Enterprise HR Retrieval-Augmented Generation (RAG) assistant.",
    version="1.0.0"
)

# CORS configuration - strict settings to prevent external site leaks
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8000", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS", "PUT"],
    allow_headers=["X-CSRF-Token", "Content-Type", "Authorization"]
)

# Startup DB initialization
@app.on_event("startup")
def startup_event():
    logger.info("Initializing database schema...")
    init_db_and_seed()

# Include routers
app.include_router(auth_router)
app.include_router(documents_router)
app.include_router(chat_router)
app.include_router(tickets_router)
app.include_router(analytics_router)
app.include_router(users_router)
app.include_router(pages_router) # Serve HTML pages at the end as fallback routes

if __name__ == "__main__":
    import uvicorn
    # Dynamically determine the import path based on CWD
    # This prevents multiprocessing reload (spawn) crashes on Windows
    cwd = os.getcwd()
    if os.path.basename(cwd) == "backend":
        app_string = "app:app"
    else:
        app_string = "backend.app:app"
        
    uvicorn.run(app_string, host="127.0.0.1", port=8000, reload=True)
