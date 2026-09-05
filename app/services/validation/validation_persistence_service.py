"""
Validation persistence service.
"""

import hashlib
import json
import uuid
from typing import List, Dict, Any, Optional, Union
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session_local
from app.models.document import Document
from app.models.validation import ValidationRun, ValidationFinding
from app.models.extraction import DocumentTextExtraction
from app.models.structured_extraction import DocumentTableExtraction, DocumentChartAssociation
from app.services.extraction.extraction_service import ExtractionService
from app.services.structured_extraction.structured_extraction_service import StructuredExtractionService
from app.services.analysis.analysis_service import get_analysis_results
from app.core.config import get_settings
import logging

logger = logging.getLogger(__name__)


def _ensure_uuid(id_value: Union[str, uuid.UUID]) -> Optional[uuid.UUID]:
    """Ensure the ID is a UUID object. Returns None if the string is not a valid UUID."""
    if isinstance(id_value, str):
        try:
            return uuid.UUID(id_value)
        except ValueError:
            return None
    return id_value


class ValidationPersistenceService:
    """
    Persists validation results using existing database patterns.
    """

    def __init__(self):
        """Initialize the validation persistence service."""
        logger.debug("ValidationPersistenceService initialized")

    async def create_validation_run(self, document_id: Union[str, uuid.UUID],
                                  config_snapshot: Optional[Dict[str, Any]] = None,
                                  input_hash: Optional[str] = None) -> str:
        """
        Create a new validation run record.

        Args:
            document_id: ID of the document being validated
            config_snapshot: Configuration used for this validation
            input_hash: Hash of input data for idempotency

        Returns:
            ID of the created validation run
        """
        # Ensure we're working with UUID objects for database operations
        document_uuid = _ensure_uuid(document_id)
        if document_uuid is None:
            raise ValueError(f"Document with ID {document_id} not found")

        async with get_async_session_local()() as session:
            # Verify document exists
            doc_query = select(Document).where(Document.id == document_uuid)
            doc_result = await session.execute(doc_query)
            document = doc_result.scalar_one_or_none()

            if not document:
                raise ValueError(f"Document with ID {document_id} not found")

            # Create validation run
            validation_run = ValidationRun(
                document_id=document_uuid,
                status="pending",
                config_snapshot=config_snapshot,
                input_hash=input_hash
            )

            session.add(validation_run)
            await session.commit()
            await session.refresh(validation_run)

            logger.info(f"Created validation run {validation_run.id} for document {document_id}")
            return str(validation_run.id)

    async def update_validation_run_status(self, validation_run_id: Union[str, uuid.UUID], status: str,
                                         overall_quality_score: Optional[float] = None,
                                         final_decision: Optional[str] = None) -> None:
        """
        Update the status of a validation run.

        Args:
            validation_run_id: ID of the validation run
            status: New status (pending, validating, completed, failed)
            overall_quality_score: Overall quality score (0-100)
            final_decision: Final decision (approved, flagged, failed)
        """
        # Ensure we'reworking with UUID objects for database operations
        run_uuid = _ensure_uuid(validation_run_id)
        if run_uuid is None:
            raise ValueError(f"Validation run with ID {validation_run_id} not found")

        async with get_async_session_local()() as session:
            query = select(ValidationRun).where(ValidationRun.id == run_uuid)
            result = await session.execute(query)
            validation_run = result.scalar_one_or_none()

            if not validation_run:
                raise ValueError(f"Validation run with ID {validation_run_id} not found")

            validation_run.status = status
            if overall_quality_score is not None:
                validation_run.overall_quality_score = overall_quality_score
            if final_decision is not None:
                validation_run.final_decision = final_decision
            if status == "completed" or status == "failed":
                from sqlalchemy.sql import func
                validation_run.completed_at = func.now()

            await session.commit()
            logger.debug(f"Updated validation run {validation_run_id} status to {status}")

    async def add_validation_findings(self, validation_run_id: Union[str, uuid.UUID],
                                    findings: List[Dict[str, Any]]) -> List[str]:
        """
        Add validation findings to a validation run.

        Args:
            validation_run_id: ID of the validation run
            findings: List of validation finding dictionaries

        Returns:
            List of IDs of the created findings
        """
        # Ensure we're working with UUID objects for database operations
        run_uuid = _ensure_uuid(validation_run_id)
        if run_uuid is None:
            raise ValueError(f"Validation run with ID {validation_run_id} not found")

        async with get_async_session_local()() as session:
            # Verify validation run exists
            query = select(ValidationRun).where(ValidationRun.id == run_uuid)
            result = await session.execute(query)
            validation_run = result.scalar_one_or_none()

            if not validation_run:
                raise ValueError(f"Validation run with ID {validation_run_id} not found")

            finding_ids = []
            for finding_data in findings:
                finding = ValidationFinding(
                    validation_run_id=run_uuid,
                    validator=finding_data.get('validator', 'unknown'),
                    check_name=finding_data.get('check_name', 'unknown_check'),
                    status=finding_data.get('status', 'unknown'),
                    severity=finding_data.get('severity', 'info'),
                    message=finding_data.get('message', ''),
                    page_number=finding_data.get('page_number'),
                    table_reference=finding_data.get('table_reference'),
                    details=finding_data.get('details')
                )

                session.add(finding)
                finding_ids.append(str(finding.id))

            await session.commit()
            logger.debug(f"Added {len(finding_ids)} validation findings to run {validation_run_id}")
            return finding_ids

    async def get_validation_run(self, validation_run_id: Union[str, uuid.UUID]) -> Optional[Dict[str, Any]]:
        """
        Get a validation run by ID.

        Args:
            validation_run_id: ID of the validation run

        Returns:
            Dictionary representation of the validation run or None if not found
        """
        # Ensure we're working with UUID objects for database operations
        run_uuid = _ensure_uuid(validation_run_id)
        if run_uuid is None:
            return None

        async with get_async_session_local()() as session:
            query = select(ValidationRun).where(ValidationRun.id == run_uuid)
            result = await session.execute(query)
            validation_run = result.scalar_one_or_none()

            if not validation_run:
                return None

            # Get associated findings
            findings_query = select(ValidationFinding).where(
                ValidationFinding.validation_run_id == run_uuid
            ).order_by(ValidationFinding.created_at)
            findings_result = await session.execute(findings_query)
            findings = findings_result.scalars().all()

            # Convert to dictionary
            return {
                'id': str(validation_run.id),
                'document_id': str(validation_run.document_id),
                'status': validation_run.status,
                'overall_quality_score': validation_run.overall_quality_score,
                'final_decision': validation_run.final_decision,
                'config_snapshot': validation_run.config_snapshot,
                'input_hash': validation_run.input_hash,
                'created_at': validation_run.created_at,
                'completed_at': validation_run.completed_at,
                'findings': [
                    {
                        'id': str(f.id),
                        'validator': f.validator,
                        'check_name': f.check_name,
                        'status': f.status,
                        'severity': f.severity,
                        'message': f.message,
                        'page_number': f.page_number,
                        'table_reference': str(f.table_reference) if f.table_reference else None,
                        'details': f.details,
                        'created_at': f.created_at
                    }
                    for f in findings
                ]
            }

    async def get_latest_validation_run(self, document_id: Union[str, uuid.UUID]) -> Optional[Dict[str, Any]]:
        """
        Get the latest validation run for a document.

        Args:
            document_id: ID of the document

        Returns:
            Dictionary representation of the latest validation run or None if not found
        """
        # Ensure we're working with UUID objects for database operations
        doc_uuid = _ensure_uuid(document_id)
        if doc_uuid is None:
            return None

        async with get_async_session_local()() as session:
            # Get latest validation run by created_at
            query = select(ValidationRun).where(
                ValidationRun.document_id == doc_uuid
            ).order_by(ValidationRun.created_at.desc()).limit(1)
            result = await session.execute(query)
            validation_run = result.scalar_one_or_none()

            if not validation_run:
                return None

            # Get associated findings
            findings_query = select(ValidationFinding).where(
                ValidationFinding.validation_run_id == validation_run.id
            ).order_by(ValidationFinding.created_at)
            findings_result = await session.execute(findings_query)
            findings = findings_result.scalars().all()

            # Convert to dictionary
            return {
                'id': str(validation_run.id),
                'document_id': str(validation_run.document_id),
                'status': validation_run.status,
                'overall_quality_score': validation_run.overall_quality_score,
                'final_decision': validation_run.final_decision,
                'config_snapshot': validation_run.config_snapshot,
                'input_hash': validation_run.input_hash,
                'created_at': validation_run.created_at,
                'completed_at': validation_run.completed_at,
                'findings': [
                    {
                        'id': str(f.id),
                        'validator': f.validator,
                        'check_name': f.check_name,
                        'status': f.status,
                        'severity': f.severity,
                        'message': f.message,
                        'page_number': f.page_number,
                        'table_reference': str(f.table_reference) if f.table_reference else None,
                        'details': f.details,
                        'created_at': f.created_at
                    }
                    for f in findings
                ]
            }

    async def compute_input_hash(self, document_id: Union[str, uuid.UUID]) -> str:
        """
        Compute a hash of the input data for idempotency detection.

        Args:
            document_id: ID of the document

        Returns:
            SHA-256 hash of the input data
        """
        # Ensure we're working with UUID objects for database operations
        doc_uuid = _ensure_uuid(document_id)
        if doc_uuid is None:
            # If we can't convert to UUID, we can't compute a meaningful hash
            # Return a hash based on the string itself
            return hashlib.sha256(document_id.encode()).hexdigest()

        hash_input = []

        async with get_async_session_local()() as session:
            # Get document basic info
            doc_query = select(Document).where(Document.id == doc_uuid)
            doc_result = await session.execute(doc_query)
            document = doc_result.scalar_one_or_none()

            if document:
                hash_input.append(f"doc_id:{document.id}")
                hash_input.append(f"checksum:{document.checksum_sha256}")
                hash_input.append(f"status:{document.status}")

            # Get text extractions
            text_query = select(DocumentTextExtraction).where(
                DocumentTextExtraction.document_id == doc_uuid
            ).order_by(DocumentTextExtraction.page_number, DocumentTextExtraction.extraction_method)
            text_result = await session.execute(text_query)
            text_extractions = text_result.scalars().all()

            for extraction in text_extractions:
                hash_input.append(f"text:{extraction.document_id}:{extraction.page_number}:{extraction.extraction_method}:{hashlib.sha256((extraction.raw_text or '').encode()).hexdigest()[:8]}")

            # Get table extractions
            table_query = select(DocumentTableExtraction).where(
                DocumentTableExtraction.document_id == doc_uuid
            ).order_by(DocumentTableExtraction.page_number, DocumentTableExtraction.table_index)
            table_result = await session.execute(table_query)
            table_extractions = table_result.scalars().all()

            for table in table_extractions:
                table_data_str = json.dumps(table.table_data, sort_keys=True) if table.table_data else ""
                hash_input.append(f"table:{table.document_id}:{table.page_number}:{table.table_index}:{table.extraction_method}:{hashlib.sha256(table_data_str.encode()).hexdigest()[:8]}")

            # Get chart associations
            chart_query = select(DocumentChartAssociation).where(
                DocumentChartAssociation.document_id == doc_uuid
            ).order_by(DocumentChartAssociation.page_number, DocumentChartAssociation.chart_index)
            chart_result = await session.execute(chart_query)
            chart_associations = chart_result.scalars().all()

            for chart in chart_associations:
                chart_meta_str = json.dumps(chart.chart_metadata, sort_keys=True) if chart.chart_metadata else ""
                hash_input.append(f"chart:{chart.document_id}:{chart.page_number}:{chart.chart_index}:{chart.association_method}:{hashlib.sha256(chart_meta_str.encode()).hexdigest()[:8]}")

        # Combine all inputs and hash
        combined_input = "|".join(sorted(hash_input))
        return hashlib.sha256(combined_input.encode()).hexdigest()

    async def should_skip_validation(self, document_id: Union[str, uuid.UUID],
                                   force_reextraction: bool = False) -> tuple[bool, Optional[str]]:
        """
        Check if validation should be skipped due to idempotency.

        Args:
            document_id: ID of the document
            force_reextraction: If True, skip idempotency check and force validation

        Returns:
            Tuple of (should_skip, existing_validation_run_id)
        """
        if force_reextraction:
            return False, None

        # Get latest validation run
        latest_run = await self.get_latest_validation_run(document_id)
        if not latest_run:
            return False, None  # No previous validation, so we should run

        # Compute current input hash
        current_hash = await self.compute_input_hash(document_id)

        # Compare with stored hash
        if latest_run.get('input_hash') == current_hash:
            logger.info(f"Validation skipped for document {document_id}: inputs unchanged")
            return True, latest_run['id']

        return False, None