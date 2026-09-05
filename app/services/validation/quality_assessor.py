"""
Quality assessment for extraction results.
"""

import logging
from typing import List, Dict, Any, Optional
from app.models.extraction import DocumentTextExtraction
from app.models.structured_extraction import DocumentTableExtraction, DocumentChartAssociation

logger = logging.getLogger(__name__)


class QualityAssessor:
    """
    Assesses extraction quality using deterministic signals from existing pipeline outputs.
    Produces explainable quality scores from 0-100.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the quality assessor.

        Args:
            config: Configuration dictionary for scoring weights and thresholds
        """
        # Default weights for quality score components
        self.weights = {
            'ocr_confidence': 0.30,      # From Phase 4 OCR confidence
            'validation_pass_rate': 0.40, # From validation checks passed/failed
            'structure_quality': 0.20,    # From table structure validation
            'completeness': 0.10          # From extraction completeness
        }

        # Override with provided config
        if config:
            if 'weights' in config:
                self.weights.update(config['weights'])

        logger.debug(f"QualityAssessor initialized with weights: {self.weights}")

    def assess_quality(self, document_id: str, text_extractions: List[DocumentTextExtraction],
                      table_extractions: List[DocumentTableExtraction],
                      chart_associations: List[DocumentChartAssociation],
                      validation_findings: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Assess the quality of extraction results.

        Args:
            document_id: ID of the document being assessed
            text_extractions: List of text extraction results
            table_extractions: List of table extraction results
            chart_associations: List of chart association results
            validation_findings: List of validation findings from all validators

        Returns:
            Dictionary containing quality score and breakdown
        """
        # Calculate individual component scores
        ocr_score = self._assess_ocr_confidence(text_extractions)
        validation_score = self._assess_validation_pass_rate(validation_findings)
        structure_score = self._assess_structure_quality(table_extractions)
        completeness_score = self._assess_completeness(text_extractions, table_extractions, chart_associations)

        # Calculate weighted final score
        final_score = (
            self.weights['ocr_confidence'] * ocr_score +
            self.weights['validation_pass_rate'] * validation_score +
            self.weights['structure_quality'] * structure_score +
            self.weights['completeness'] * completeness_score
        )

        # Ensure score is within bounds
        final_score = max(0.0, min(100.0, final_score))

        # Create detailed breakdown
        breakdown = {
            'ocr_confidence': {
                'score': round(ocr_score, 2),
                'weight': self.weights['ocr_confidence'],
                'weighted_contribution': round(self.weights['ocr_confidence'] * ocr_score, 2),
                'description': 'OCR confidence from Phase 4 extraction (0-30 points)',
                'available': len(text_extractions) > 0
            },
            'validation_pass_rate': {
                'score': round(validation_score, 2),
                'weight': self.weights['validation_pass_rate'],
                'weighted_contribution': round(self.weights['validation_pass_rate'] * validation_score, 2),
                'description': 'Percentage of validation checks passed (0-40 points)',
                'available': len(validation_findings) > 0
            },
            'structure_quality': {
                'score': round(structure_score, 2),
                'weight': self.weights['structure_quality'],
                'weighted_contribution': round(self.weights['structure_quality'] * structure_score, 2),
                'description': 'Table structure quality from validation (0-20 points)',
                'available': len(table_extractions) > 0
            },
            'completeness': {
                'score': round(completeness_score, 2),
                'weight': self.weights['completeness'],
                'weighted_contribution': round(self.weights['completeness'] * completeness_score, 2),
                'description': 'Extraction completeness ratio (0-10 points)',
                'available': len(text_extractions) > 0 or len(table_extractions) > 0
            }
        }

        logger.debug(f"Quality assessment completed for document {document_id}: {final_score:.2f}")

        return {
            'document_id': document_id,
            'overall_quality_score': round(final_score, 2),
            'component_scores': breakdown,
            'scoring_method': 'weighted_deterministic',
            'weights_used': self.weights.copy()
        }

    def _assess_ocr_confidence(self, text_extractions: List[DocumentTextExtraction]) -> float:
        """
        Assess OCR confidence component (0-100 scale).

        Only considers genuine OCR confidence from Phase 4.
        Native text extraction is not assigned fake confidence.

        Returns:
            Score from 0-100
        """
        if not text_extractions:
            # No text extractions - this could mean no text content or extraction not attempted
            # Return neutral score since we don't know if OCR was applicable
            return 50.0

        confidences = []
        has_ocr_extractions = False

        for extraction in text_extractions:
            # Only consider confidence if it's from OCR extraction
            if extraction.extraction_method and 'ocr' in extraction.extraction_method.lower():
                has_ocr_extractions = True
                if extraction.confidence is not None:
                    # Confidence is expected to be 0-1 scale, convert to 0-100
                    confidences.append(float(extraction.confidence) * 100.0)

        if not has_ocr_extractions:
            # No OCR extractions found - all text came from native PDF extraction
            # Native text gets neutral score since no confidence fabrication
            return 50.0

        if not confidences:
            # OCR extractions exist but no confidence values
            return 50.0

        # Calculate average OCR confidence
        avg_confidence = sum(confidences) / len(confidences)
        return max(0.0, min(100.0, avg_confidence))

    def _assess_validation_pass_rate(self, validation_findings: List[Dict[str, Any]]) -> float:
        """
        Assess validation pass rate component (0-100 scale).

        Returns:
            Score from 0-100 representing percentage of checks passed
        """
        if not validation_findings:
            # No validation findings - neutral score
            return round(50.0, 2)

        # Count checks by status
        passed_checks = sum(1 for f in validation_findings if f.get('status') == 'passed')
        failed_checks = sum(1 for f in validation_findings if f.get('status') == 'failed')
        error_checks = sum(1 for f in validation_findings if f.get('status') == 'error')
        skipped_checks = sum(1 for f in validation_findings if f.get('status') == 'skipped')

        total_checks = passed_checks + failed_checks + error_checks + skipped_checks

        if total_checks == 0:
            return round(50.0, 2)

        # Calculate pass rate (only count non-skipped checks for pass/fail ratio)
        applicable_checks = passed_checks + failed_checks + error_checks
        if applicable_checks == 0:
            # All checks were skipped
            return round(50.0, 2)

        pass_rate = (passed_checks / applicable_checks) * 100.0
        return round(max(0.0, min(100.0, pass_rate)), 2)

    def _assess_structure_quality(self, table_extractions: List[DocumentTableExtraction]) -> float:
        """
        Assess table structure quality component (0-100 scale).

        Based on the absence of structural errors in validation.

        Returns:
            Score from 0-100
        """
        if not table_extractions:
            # No tables to assess structure
            return 50.0

        # For now, we'll return a neutral score since structure quality
        # would ideally come from table validator findings
        # In a full implementation, we'd analyze the table validator findings
        # specifically for structure-related issues
        return 75.0  # Slightly positive since tables were extracted successfully

    def _assess_completeness(self, text_extractions: List[DocumentTextExtraction],
                           table_extractions: List[DocumentTableExtraction],
                           chart_associations: List[DocumentChartAssociation]) -> float:
        """
        Assess extraction completeness component (0-100 scale).

        Based on ratio of expected vs actual extraction results.
        Since we don't have expectations, we use a heuristic based on
        whether we got any results vs none.

        Returns:
            Score from 0-100
        """
        total_extractions = len(text_extractions) + len(table_extractions) + len(chart_associations)

        if total_extractions == 0:
            # No extractions at all
            return 0.0
        elif total_extractions < 3:  # Very few extractions
            return 30.0
        else:  # Moderate to good number of extractions (3+)
            return 90.0