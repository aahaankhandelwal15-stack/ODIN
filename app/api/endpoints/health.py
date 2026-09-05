from fastapi import APIRouter
from app.core.config import get_settings
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("")
async def health_check():
    """
    Health check endpoint to confirm the backend is operational.
    """
    settings = get_settings()
    logger.info("Health check requested")
    return {
        "status": "healthy",
        "environment": settings.APP_ENV,
        "storage_backend": settings.STORAGE_BACKEND
    }