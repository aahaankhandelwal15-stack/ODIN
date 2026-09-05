from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.main import api_router
from app.core.config import get_settings
import logging

# Get settings
settings = get_settings()
print(f"[DEBUG] App module loaded. Settings APP_ENV: {settings.APP_ENV}, DATABASE_URL: {settings.DATABASE_URL}")

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="CMPDI/CIL AI Reporting Platform",
    description="Phase 1: Backend Foundation and Document Ingestion",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API router
app.include_router(api_router)

@app.on_event("startup")
async def startup_event():
    logger.info("Starting up CMPDI/CIL AI Reporting Platform")
    logger.info(f"Environment: {settings.APP_ENV}")
    logger.info(f"Storage backend: {settings.STORAGE_BACKEND}")

    # Create database tables if they don't exist
    logger.info("Creating database tables if they don't exist...")
    from app.core.database import Base, get_engine
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created/verified")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutting down CMPDI/CIL AI Reporting Platform")