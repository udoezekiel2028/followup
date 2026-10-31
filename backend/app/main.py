import os
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.database import init_db
from app.services.scheduler import AutomationEngine
from app.routers import (
    auth, accounts, dashboard, email_management, 
    settings as settings_router, automation, logs, pubsub
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize Database Tables
    init_db()
    # Startup: Start Background Scheduler Worker
    AutomationEngine.start()
    yield
    # Shutdown: Stop scheduler gracefully
    AutomationEngine.shutdown()

app = FastAPI(
    title=settings.APP_NAME,
    description="SmartFollow AI - Gmail AI Cold Email Follow-Up Automation Platform",
    version="1.0.0",
    lifespan=lifespan
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.FRONTEND_URL,
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "*"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API Routers
app.include_router(auth.router)
app.include_router(accounts.router)
app.include_router(dashboard.router)
app.include_router(email_management.router)
app.include_router(settings_router.router)
app.include_router(automation.router)
app.include_router(logs.router)
app.include_router(pubsub.router)

@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "app_name": settings.APP_NAME,
        "environment": settings.APP_ENV,
        "scheduler_running": AutomationEngine.scheduler.running
    }

# Check for production frontend build directory
possible_dist_dirs = [
    Path(__file__).resolve().parent.parent.parent / "frontend" / "dist",
    Path("/app/frontend/dist"),
    Path("./frontend/dist")
]

dist_dir = None
for d in possible_dist_dirs:
    if d.exists() and (d / "index.html").exists():
        dist_dir = d
        break

if dist_dir:
    assets_dir = dist_dir / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(request: Request, full_path: str):
        if full_path.startswith("api"):
            return None
        file_path = dist_dir / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(dist_dir / "index.html")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)
