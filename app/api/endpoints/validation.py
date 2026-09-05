"""
API endpoints for validation results.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app.core.database import get_db
from app.services.validation.validation_service import ValidationService
from app.schemas.validation import (
    ValidationRunResponse,
    ValidationFindingResponse,
    ValidationResult,
    ValidationSummary
)
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/{document_id}/validate", response_model=ValidationResult)
async def validate_document(
    document_id: str,
    force: bool = False,
    db: AsyncSession = Depends(get_db)
):
    """
    Validate a document's extraction results.
    """
    try:
        # Initialize validation service
        validation_service = ValidationService()
        result = await validation_service.validate_document(document_id, force_revalidation=force)
        return result

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error validating document: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to validate document: {str(e)}"
        )


@router.get("/{document_id}/validation", response_model=ValidationSummary)
async def get_document_validation(
    document_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Get latest validation results for a document.
    """
    try:
        # Initialize validation service
        validation_service = ValidationService()
        result = await validation_service.persistence_service.get_latest_validation_run(document_id)

        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No validation results found for document {document_id}"
            )

        # Convert to summary format
        summary = ValidationSummary(
            document_id=result["document_id"],
            status=result["status"],
            overall_quality_score=result["overall_quality_score"],
            final_decision=result["final_decision"],
            validation_run_id=result["id"],
            created_at=result["created_at"],
            completed_at=result["completed_at"],
            findings_count=len(result["findings"]),
            passed_count=sum(1 for f in result["findings"] if f["status"] == "passed"),
            failed_count=sum(1 for f in result["findings"] if f["status"] == "failed"),
            skipped_count=sum(1 for f in result["findings"] if f["status"] == "skipped"),
            error_count=sum(1 for f in result["findings"] if f["status"] == "error")
        )
        return summary

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error retrieving validation results: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve validation results: {str(e)}"
        )


@router.get("/{document_id}/validation/findings", response_model=List[ValidationFindingResponse])
async def get_document_validation_findings(
    document_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Get detailed validation findings for a document's latest validation run.
    """
    try:
        # Initialize validation service
        validation_service = ValidationService()
        result = await validation_service.persistence_service.get_latest_validation_run(document_id)

        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No validation results found for document {document_id}"
            )

        # Convert findings to response format
        findings = [
            ValidationFindingResponse(
                id=f["id"],
                validation_run_id=result["id"],
                validator=f["validator"],
                check_name=f["check_name"],
                status=f["status"],
                severity=f["severity"],
                message=f["message"],
                page_number=f["page_number"],
                table_reference=f["table_reference"],
                details=f["details"],
                created_at=f["created_at"]
            )
            for f in result["findings"]
        ]
        return findings

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error retrieving validation findings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve validation findings: {str(e)}"
        )


@router.get("/validation/{validation_run_id}", response_model=ValidationRunResponse)
async def get_validation_run(
    validation_run_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Get a specific validation run by ID.
    """
    try:
        # Initialize validation service
        validation_service = ValidationService()
        result = await validation_service.persistence_service.get_validation_run(validation_run_id)

        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Validation run with ID {validation_run_id} not found"
            )

        # Convert to response format
        response = ValidationRunResponse(
            id=result["id"],
            document_id=result["document_id"],
            status=result["status"],
            overall_quality_score=result["overall_quality_score"],
            final_decision=result["final_decision"],
            config_snapshot=result["config_snapshot"],
            input_hash=result["input_hash"],
            created_at=result["created_at"],
            completed_at=result["completed_at"]
        )
        return response

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error retrieving validation run: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve validation run: {str(e)}"
        )