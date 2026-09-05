"""
API endpoints for structured table and chart extraction results.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app.core.database import get_db
from app.services.structured_extraction.structured_extraction_service import extract_structured_content, get_structured_extraction_results
from app.schemas.structured_extraction import (
    TableExtractionResponse,
    ChartAssociationResponse,
    StructuredExtractionResult,
    StructuredExtractionSummary
)
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/{document_id}/structured-extract", response_model=StructuredExtractionResult)
async def extract_document_structured_content(
    document_id: str,
    force: bool = False,
    db: AsyncSession = Depends(get_db)
):
    """
    Extract structured content (tables and chart associations) from a document.
    """
    try:
        # Initialize structured extraction service
        result = await extract_structured_content(document_id, force_reextraction=force)
        return result

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error extracting structured content from document: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to extract structured content from document: {str(e)}"
        )


@router.get("/{document_id}/structured-content", response_model=StructuredExtractionSummary)
async def get_document_structured_content(
    document_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Retrieve structured extraction results for a document.
    """
    try:
        # Get structured extraction results
        result = await get_structured_extraction_results(document_id)
        return result

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error retrieving structured extraction results: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve structured extraction results: {str(e)}"
        )


@router.get("/{document_id}/tables", response_model=List[TableExtractionResponse])
async def get_document_tables(
    document_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Retrieve table extraction results for a document.
    """
    try:
        # Get structured extraction results
        result = await get_structured_extraction_results(document_id)
        return result["tables"]

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error retrieving table results: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve table results: {str(e)}"
        )


@router.get("/{document_id}/charts", response_model=List[ChartAssociationResponse])
async def get_document_charts(
    document_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Retrieve chart association results for a document.
    """
    try:
        # Get structured extraction results
        result = await get_structured_extraction_results(document_id)
        return result["charts"]

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error retrieving chart results: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve chart results: {str(e)}"
        )