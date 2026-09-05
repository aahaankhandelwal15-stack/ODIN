from fastapi import APIRouter, Depends, File, UploadFile, Form, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.services.ingestion_service import IngestionService
from app.services.document_repository import DocumentRepository
from app.services.analysis.analysis_service import analyze_document, get_analysis_results
from app.schemas.document import IngestionResult, DocumentResponse
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/upload", response_model=IngestionResult)
async def upload_document(
    file: UploadFile = File(...),
    source_type: str = Form("manual_upload"),
    source_identifier: str = Form(None),
    subsidiary: str = Form(None),
    document_timestamp: str = Form(None),  # ISO format string
    db: AsyncSession = Depends(get_db)
):
    """
    Upload and ingest a document.
    """
    try:
        # Parse document_timestamp if provided
        parsed_timestamp = None
        if document_timestamp:
            from datetime import datetime
            parsed_timestamp = datetime.fromisoformat(document_timestamp)

        # Initialize ingestion service
        ingestion_service = IngestionService()

        # Ingest the document
        result = await ingestion_service.ingest_document(
            file_data=file.file,
            original_filename=file.filename,
            content_type=file.content_type,
            source_type=source_type,
            source_identifier=source_identifier,
            subsidiary=subsidiary,
            document_timestamp=parsed_timestamp
        )

        return result

    except Exception as e:
        logger.error(f"Error uploading document: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to ingest document: {str(e)}"
        )


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Retrieve document metadata by document ID.
    """
    try:
        repository = DocumentRepository(db)
        document = await repository.get_by_id(document_id)

        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document with ID {document_id} not found"
            )

        return DocumentResponse.from_orm(document)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving document: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve document: {str(e)}"
        )


@router.post("/{document_id}/analyze")
async def analyze_document_endpoint(
    document_id: str,
    force: bool = False,
    db: AsyncSession = Depends(get_db)
):
    """
    Trigger analysis of a document to classify its pages.
    """
    try:
        # Initialize analysis service
        result = await analyze_document(document_id, force_reanalysis=force)
        return result

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error analyzing document: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to analyze document: {str(e)}"
        )


@router.get("/{document_id}/pages")
async def get_document_pages(
    document_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Retrieve page analysis results for a document.
    """
    try:
        # Get analysis results
        result = await get_analysis_results(document_id)
        return result

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error retrieving document pages: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve document pages: {str(e)}"
        )