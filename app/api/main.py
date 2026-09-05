from fastapi import APIRouter
from app.api.endpoints import health, documents, extraction, structured_extraction, validation

api_router = APIRouter()
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(documents.router, prefix="/documents", tags=["documents"])
api_router.include_router(extraction.router, prefix="/documents", tags=["extraction"])
api_router.include_router(structured_extraction.router, prefix="/documents", tags=["structured_extraction"])
api_router.include_router(validation.router, prefix="/documents", tags=["validation"])