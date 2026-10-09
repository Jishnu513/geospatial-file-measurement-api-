import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.api.routes_files import router as files_router
from app.services.database import init_db

# Uptime tracker
START_TIME = time.time()
STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize SQLite database schema
    init_db()
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    description=settings.PROJECT_DESCRIPTION,
    version=settings.PROJECT_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Enable CORS for frontend clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API Routers
app.include_router(files_router)

# Mount static files directory
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/dashboard", tags=["Dashboard"])
def get_dashboard():
    """
    Serves the interactive GIS Web Dashboard and visualizer.
    """
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return JSONResponse(
        status_code=404,
        content={"detail": "Dashboard frontend index.html not found."}
    )


@app.get("/api/health", tags=["Health"])
def health_check():
    """
    Health check and runtime diagnostics endpoint.
    """
    uptime = round(time.time() - START_TIME, 2)
    return {
        "status": "HEALTHY",
        "service": settings.PROJECT_NAME,
        "version": settings.PROJECT_VERSION,
        "uptime_seconds": uptime,
        "storage": {
            "upload_dir": str(settings.UPLOAD_DIR),
            "max_upload_size_mb": settings.MAX_UPLOAD_SIZE_BYTES // (1024 * 1024),
        }
    }


@app.get("/", tags=["Root"])
def root():
    return {
        "message": "Geospatial File Measurement API is running.",
        "dashboard": "/dashboard",
        "documentation": "/docs",
        "health": "/api/health",
        "endpoints": {
            "upload": "POST /api/files/",
            "list": "GET /api/files/",
            "samples": "GET /api/files/samples/",
            "info": "GET /api/files/{id}/",
            "measurements": "GET /api/files/{id}/measurements/",
            "features": "GET /api/files/{id}/features/",
            "delete": "DELETE /api/files/{id}/"
        }
    }

