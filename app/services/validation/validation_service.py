"""
Main validation service that orchestrates the validation process.
"""

import logging
from typing import List, Dict, Any, Optional
from app.services.validation.schema_validator import SchemaValidator
from app.services.validation.table_validator import TableValidator
from app.services.validation.numeric_consistency_validator import NumericConsistencyValidator
from app.services.validation.quality_assessor import QualityAssessor
from app.services.validation.validation_persistence_service import ValidationPersistenceService
from app.models.extraction import DocumentTextExtraction
from app.models.structured_extraction import DocumentTableExtraction, DocumentChartAssociation
from app.core.config import get_settings

logger = logging.getLogger(__name__)


class ValidationService:
    """
    Main validation service that orchestrates the validation process.
    """

    def __init__(self):
        """Initialize the validation service."""
        self.schema_validator = SchemaValidator()
        self.table_validator = TableValidator()
        self.numeric_validator = NumericConsistencyValidator()
        self.quality_assessor = QualityAssessor()
        self.persistence_service = ValidationPersistenceService()
        self.settings = get_settings()
        logger.debug("ValidationService initialized")

    async def validate_document(self, document_id: str,
                              force_revalidation: bool = False) -> Dict[str, Any]:
        """
        Perform complete validation of a document.

        Args:
            document_id: ID of the document to validate
            force_revalidation: If True, re-validate even if already validated

        Returns:
            Dictionary containing validation results
        """
        logger.info(f"Starting validation for document {document_id}")

        # Check idempotency
        should_skip, existing_run_id = await self.persistence_service.should_skip_validation(
            document_id, force_revalidation
        )

        if should_skip and existing_run_id:
            logger.info(f"Skipping validation for document {document_id}: using existing run {existing_run_id}")
            # Return existing validation run
            existing_result = await self.persistence_service.get_validation_run(existing_run_id)
            if existing_result:
                return existing_result
            else:
                logger.warning(f"Existing validation run {existing_run_id} not found, proceeding with new validation")

        # Create new validation run
        validation_run_id = await self.persistence_service.create_validation_run(
            document_id=document_id,
            config_snapshot=self._get_config_snapshot(),
            input_hash=await self.persistence_service.compute_input_hash(document_id)
        )

        try:
            # Update status to validating
            await self.persistence_service.update_validation_run_status(
                validation_run_id=validation_run_id,
                status="validating"
            )

            # Gather extraction results from previous phases
            text_extractions, table_extractions, chart_associations = await self._gather_extraction_results(document_id)

            # Run all validators
            all_findings = []

            # Schema validation
            logger.debug("Running schema validation")
            for extraction in text_extractions:
                findings = self.schema_validator.validate_text_extraction(extraction)
                all_findings.extend(findings)

            for table in table_extractions:
                findings = self.schema_validator.validate_table_extraction(table)
                all_findings.extend(findings)

            for chart in chart_associations:
                findings = self.schema_validator.validate_chart_association(chart)
                all_findings.extend(findings)

            # Table structural validation
            logger.debug("Running table structural validation")
            for table in table_extractions:
                findings = self.table_validator.validate_table_structure(table)
                all_findings.extend(findings)

            # Numeric consistency validation
            logger.debug("Running numeric consistency validation")
            for table in table_extractions:
                findings = self.numeric_validator.validate_numeric_consistency(table)
                all_findings.extend(findings)

            # Persist all findings
            finding_ids = await self.persistence_service.add_validation_findings(
                validation_run_id=validation_run_id,
                findings=all_findings
            )

            # Assess quality
            logger.debug("Assessing quality")
            quality_result = self.quality_assessor.assess_quality(
                document_id=document_id,
                text_extractions=text_extractions,
                table_extractions=table_extractions,
                chart_associations=chart_associations,
                validation_findings=all_findings
            )

            # Determine final decision based on quality score and critical failures
            final_decision = self._determine_final_decision(
                quality_score=quality_result['overall_quality_score'],
                validation_findings=all_findings
            )

            # Update validation run with final results
            await self.persistence_service.update_validation_run_status(
                validation_run_id=validation_run_id,
                status="completed",
                overall_quality_score=quality_result['overall_quality_score'],
                final_decision=final_decision
            )

            # Prepare final result
            validation_result = await self.persistence_service.get_validation_run(validation_run_id)
            logger.info(f"Validation completed for document {document_id}. Score: {quality_result['overall_quality_score']}, Decision: {final_decision}")

            return validation_result

        except Exception as e:
            # Update status to failed on error
            await self.persistence_service.update_validation_run_status(
                validation_run_id=validation_run_id,
                status="failed"
            )
            logger.error(f"Validation failed for document {document_id}: {str(e)}")
            raise

    async def _gather_extraction_results(self, document_id: str) -> tuple[
        List[DocumentTextExtraction],
        List[DocumentTableExtraction],
        List[DocumentChartAssociation]
    ]:
        """
        Gather extraction results from previous phases.

        Args:
            document_id: ID of the document

        Returns:
            Tuple of (text_extractions, table_extractions, chart_associations)
        """
        async with get_async_session_local()() as session:
            # Get text extractions
            text_query = select(DocumentTextExtraction).where(
                DocumentTextExtraction.document_id == document_id
            ).order_by(DocumentTextExtraction.page_number, DocumentTextExtraction.extraction_method)
            text_result = await session.execute(text_query)
            text_extractions = text_result.scalars().all()

            # Get table extractions
            table_query = select(DocumentTableExtraction).where(
                DocumentTableExtraction.document_id == document_id
            ).order_by(DocumentTableExtraction.page_number, DocumentTableExtraction.table_index)
            table_result = await session.execute(table_query)
            table_extractions = table_result.scalars().all()

            # Get chart associations
            chart_query = select(DocumentChartAssociation).where(
                DocumentChartAssociation.document_id == document_id
            ).order_by(DocumentChartAssociation.page_number, DocumentChartAssociation.chart_index)
            chart_result = await session.execute(chart_query)
            chart_associations = chart_result.scalars().all()

            logger.debug(f"Gathered extraction results for document {document_id}: {len(text_extractions)} text, {len(table_extractions)} table, {len(chart_associations)} chart")

            return list(text_extractions), list(table_extractions), list(chart_associations)

    def _get_config_snapshot(self) -> Dict[str, Any]:
        """
        Get a snapshot of current configuration for persistence.

        Returns:
            Dictionary containing relevant configuration
        """
        return {
            'validation_auto_approve_threshold': getattr(self.settings, 'VALIDATION_AUTO_APPROVE_THRESHOLD', 85),
            'numeric_consistency_tolerance': 0.01,  # From NumericConsistencyValidator default
            'quality_assessor_weights': self.quality_assessor.weights.copy()
        }

    def _determine_final_decision(self, quality_score: float,
                                validation_findings: List[Dict[str, Any]]) -> str:
        """
        Determine final validation decision based on quality score and validation findings.

        Args:
            quality_score: Overall quality score (0-100)
            validation_findings: List of validation findings

        Returns:
            Final decision: "approved", "flagged", or "failed"
        """
        # Check for validation execution failures
        has_critical_errors = any(
            f.get('severity') == 'critical' and f.get('status') == 'error'
            for f in validation_findings
        )

        if has_critical_errors:
            return "failed"

        # Check quality threshold
        threshold = getattr(self.settings, 'VALIDATION_AUTO_APPROVE_THRESHOLD', 85)
        if quality_score >= threshold:
            # Check for any error-level findings that might prevent approval
            has_error_findings = any(
                f.get('severity') == 'error' and f.get('status') == 'failed'
                for f in validation_findings
            )

            if not has_error_findings:
                return "approved"

        # Either below threshold or has error findings
        return "flagged"