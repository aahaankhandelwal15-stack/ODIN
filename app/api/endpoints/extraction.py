"""
API endpoints for text extraction results.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app.core.database import get_db
from app.services.extraction.extraction_service import extract_text_from_document, get_extraction_results
from app.schemas.extraction import ExtractionResponse, ExtractionResult, ExtractionSummary
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/{document_id}/extract", response_model=ExtractionResult)
async def extract_document_text(
    document_id: str,
    force: bool = False,
    db: AsyncSession = Depends(get_db)
):
    """
    Extract text from a document.
    """
    try:
        # Initialize extraction service
        result = await extract_text_from_document(document_id, force_reextraction=force)
        return result

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error extracting text from document: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to extract text from document: {str(e)}"
        )


@router.get("/{document_id}/extractions", response_model=ExtractionResult)
async def get_document_extractions(
    document_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Retrieve text extraction results for a document.
    """
    try:
        # Get extraction results
        result = await get_extraction_results(document_id)
        return result

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error retrieving extraction results: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve extraction results: {str(e)}"
        )


@router.get("/{document_id}/extraction/summary", response_model=ExtractionSummary)
async def get_document_extraction_summary(
    document_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Retrieve a summary of text extraction results for a document.
    """
    try:
        # Get extraction results
        result = await get_extraction_results(document_id)

        # Calculate summary statistics
        total_characters = 0
        total_words = 0
        extraction_methods = {}

        for extraction in result["extractions"]:
            normalized_text = extraction["normalized_text"] or ""
            total_characters += len(normalized_text)
            total_words += len(normalized_text.split()) if normalized_text else 0

            method = extraction["extraction_method"]
            extraction_methods[method] = extraction_methods.get(method, 0) + 1

        summary = ExtractionSummary(
            document_id=document_id,
            status=result["status"],
            page_count=result["page_count"],
            total_characters=total_characters,
            total_words=total_words,
            extraction_methods=extraction_methods
        )

        return summary

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error retrieving extraction summary: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve extraction summary: {str(e)}"
        )