"""
Content Routing Service for ODIN V1
Routes documents to appropriate processing pipelines based on page classifications.
"""

from typing import Dict, List, Optional
from enum import Enum
from app.services.analysis.page_classifier import ClassificationResult


class ProcessingProfile(Enum):
    """Processing profiles for different document types."""
    NONE = "none"                    # No additional processing
    LIGHT = "light"                  # Basic text cleanup only
    OCR_OPTIMIZED = "ocr_optimized"  # Optimized for OCR text extraction
    TABLE_PRESERVING = "table_preserving"  # Preserve table structures
    VISUAL = "visual"                # Visual feature extraction for charts/maps


class ContentRouter:
    """
    Routes document pages to appropriate processing profiles based on classification.

    Routes classifications to processing profiles as follows:
    - typed_text -> LIGHT
    - scanned_document -> OCR_OPTIMIZED
    - table_dense -> TABLE_PRESERVING
    - chart_graph -> VISUAL (with chart-specific routing)
    - map_diagram -> VISUAL (with map/diagram-specific routing)
    - mixed -> VISUAL (balanced processing)
    """

    def __init__(self):
        # Mapping from classification to processing profile
        self.classification_to_profile = {
            "typed_text": ProcessingProfile.LIGHT,
            "scanned_document": ProcessingProfile.OCR_OPTIMIZED,
            "table_dense": ProcessingProfile.TABLE_PRESERVING,
            "chart_graph": ProcessingProfile.VISUAL,
            "map_diagram": ProcessingProfile.VISUAL,
            "mixed": ProcessingProfile.VISUAL,
        }

    def get_processing_profile(self, classification: str) -> ProcessingProfile:
        """
        Get the appropriate processing profile for a page classification.

        Args:
            classification: Page classification string

        Returns:
            ProcessingProfile enum value
        """
        return self.classification_to_profile.get(
            classification.lower(),
            ProcessingProfile.NONE  # Default to no processing for unknown classifications
        )

    def route_document_pages(self, page_classifications: List[Dict]) -> Dict[str, List[int]]:
        """
        Route document pages to processing profiles.

        Args:
            page_classifications: List of dicts with 'page_number' and 'classification' keys

        Returns:
            Dictionary mapping processing profiles to lists of page numbers
        """
        routing = {
            profile: [] for profile in ProcessingProfile
        }

        for page_info in page_classifications:
            page_number = page_info.get('page_number')
            classification = page_info.get('classification', '').lower()

            if page_number is not None:
                profile = self.get_processing_profile(classification)
                routing[profile].append(page_number)

        # Remove empty profiles
        return {k: v for k, v in routing.items() if v}

    def get_chart_resolution_route(self, classification_result: ClassificationResult,
                                 analysis_signal_dict: Optional[Dict] = None) -> str:
        """
        Determine chart resolution routing for chart_graph classifications.

        Based on characteristics, route to either:
        - TABLE_BACKED_CHART: If chart appears to be data-driven and could be backed by extracted table
        - VISUAL_NUMERIC_EXTRACTION: If chart requires pure visual analysis

        Args:
            classification_result: ClassificationResult for a chart_graph page
            analysis_signal_dict: Optional dictionary of raw analysis signals for detailed routing

        Returns:
            String indicating the chart resolution route
        """
        # Initialize scoring
        table_backed_score = 0.0
        visual_score = 0.0

        # Factors favoring TABLE_BACKED_CHART:
        reason = classification_result.classification_reason.lower()

        # Text-based indicators
        if "grid" in reason or "axis" in reason or "scale" in reason:
            table_backed_score += 0.3
        if "structured" in reason or "regular" in reason or "uniform" in reason:
            table_backed_score += 0.2
        if "numeric" in reason or "data" in reason or "value" in reason:
            table_backed_score += 0.2

        # Signal-based indicators (if available)
        if analysis_signal_dict:
            # High drawing count with geometric regularity suggests chart structure
            drawing_count = analysis_signal_dict.get('drawing_count', 0)
            if drawing_count >= 10:
                table_backed_score += 0.2

            # Low image area ratio suggests not primarily photographic
            image_area_ratio = analysis_signal_dict.get('image_area_ratio', 1.0)
            if image_area_ratio < 0.3:
                table_backed_score += 0.2

            # Moderate text length suggests axis labels/data values
            text_length = analysis_signal_dict.get('text_length', 0)
            if 10 < text_length < 200:  # Reasonable for axis labels
                table_backed_score += 0.1

        # Factors favoring VISUAL_NUMERIC_EXTRACTION:
        # Complex shapes, curves, color gradients, complex patterns
        if "complex" in reason or "irregular" in reason or "organic" in reason:
            visual_score += 0.3
        if "shaded" in reason or "gradient" in reason or "color" in reason:
            visual_score += 0.2
        if "symbol" in reason or "icon" in reason or "picture" in reason:
            visual_score += 0.2

        # Default fallback based on classification confidence
        if classification_result.classification_confidence > 0.8:
            # High confidence in chart_graph classification - lean toward table-backed
            if table_backed_score == 0 and visual_score == 0:
                table_backed_score = 0.5

        # Make decision
        if table_backed_score >= visual_score:
            return "TABLE_BACKED_CHART"
        else:
            return "VISUAL_NUMERIC_EXTRACTION"

    def get_visual_processing_hints(self, classification_result: ClassificationResult) -> Dict[str, any]:
        """
        Get processing hints for visual content based on classification result.

        Args:
            classification_result: ClassificationResult object

        Returns:
            Dictionary of processing hints
        """
        hints = {
            "confidence": classification_result.classification_confidence,
            "reason": classification_result.classification_reason
        }

        classification = classification_result.classification

        if classification == "chart_graph":
            hints.update({
                "chart_type": self.get_chart_resolution_route(classification_result),
                "extract_numeric_data": True,
                "preserve_aspect_ratio": True
            })
        elif classification == "map_diagram":
            hints.update({
                "content_type": "spatial_visual",
                "extract_features": True,
                "preserve_colors": True,
                "detect_regions": True
            })
        elif classification == "table_dense":
            hints.update({
                "preserve_structure": True,
                "extract_grid": True,
                "ocr_friendly": True
            })

        return hints