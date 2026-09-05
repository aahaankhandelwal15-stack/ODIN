"""
Page Classifier Module for ODIN V1 Phase 2 & 3
Responsible for classifying PDF pages based on extracted signals.

Classification categories:
- typed_text: Pages with extractable text, low image/drawing dominance
- scanned_document: Pages with little/no extractable text, high image coverage
- table_dense: Pages with strong table-like structural signals
- chart_graph: Pages or regions containing charts/graphs with potential numerical information
- map_diagram: Pages or regions containing maps, diagrams, or other visual information
- mixed: Pages with significant text AND significant visual/table elements
"""

from typing import Dict, Any, Optional
from dataclasses import dataclass
import logging

from .pdf_analyzer import PageAnalysis

logger = logging.getLogger(__name__)


@dataclass
class ClassificationResult:
    """Result of page classification."""
    classification: str
    classification_confidence: float
    classification_reason: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage or transmission."""
        return {
            "classification": self.classification,
            "classification_confidence": self.classification_confidence,
            "classification_reason": self.classification_reason
        }


class PageClassifier:
    """
    Classifies PDF pages based on structural signals extracted by PDFAnalyzer.

    Classification categories:
    - typed_text: Pages with extractable text, low image/drawing dominance
    - scanned_document: Pages with little/no extractable text, high image coverage
    - table_dense: Pages with strong table-like structural signals
    - chart_graph: Pages or regions containing charts/graphs with potential numerical information
    - map_diagram: Pages or regions containing maps, diagrams, or other visual information
    - mixed: Pages with significant text AND significant visual/table elements
    """

    def __init__(self):
        """Initialize the page classifier with configurable thresholds."""
        # Thresholds for classification decisions
        self.MIN_TEXT_LENGTH_FOR_TYPED = 50
        self.MAX_TEXT_LENGTH_FOR_SCANNED = 10
        self.MIN_TEXT_DENSITY_FOR_TYPED = 0.001
        self.MAX_TEXT_DENSITY_FOR_SCANNED = 0.0005
        self.SCANNED_IMAGE_COVERAGE_THRESHOLD = 0.3
        self.TABLE_DENSE_SCORE_THRESHOLD = 0.5

        # Chart/Graph detection thresholds
        self.CHART_LINE_RATIO_THRESHOLD = 0.3  # Ratio of line drawings to total drawings
        self.CHART_DRAWING_COMPLEXITY_THRESHOLD = 0.6  # Complexity score for chart-like drawings
        self.CHART_TEXT_RATIO_THRESHOLD = 0.1  # Text-to-drawing ratio for chart detection

        # Map/Diagram detection thresholds
        self.MAP_AREA_RATIO_THRESHOLD = 0.4  # Minimum image area ratio for map consideration
        self.MAP_DRAWING_SPREAD_THRESHOLD = 0.5  # Drawing dispersion for map-like structures

        # Mixed content thresholds
        self.MIXED_TEXT_THRESHOLD = 100
        self.MIXED_VISUAL_THRESHOLD = 0.1

        logger.debug("PageClassifier initialized with thresholds")

    # Helper methods for chart/graph detection
    def _calculate_line_drawing_ratio(self, analysis: PageAnalysis) -> float:
        """
        Calculate the ratio of line drawings to total drawings.
        Charts typically have many line elements for axes, grids, and data lines.
        """
        # This is a simplified approximation - in a full implementation we would
        # analyze the actual drawing types from page.get_drawings()
        # For now, we use drawing count as a proxy and assume a portion are lines
        if analysis.drawing_count == 0:
            return 0.0
        # Estimate that 60% of drawings in charts are lines (axes, grids, data lines)
        return min(0.6, 1.0)

    def _detect_chart_geometric_regularity(self, analysis: PageAnalysis) -> bool:
        """
        Detect geometric regularity in drawings that suggests chart structure.
        Charts often have regular spacing in grid lines, tick marks, etc.
        """
        # Simplified heuristic: if we have sufficient drawings and some text,
        # and the drawing count suggests structured elements, assume geometric regularity
        return analysis.drawing_count >= 8 and analysis.text_length > 3

    def _detect_spatial_dispersion(self, analysis: PageAnalysis) -> bool:
        """
        Detect spatial dispersion characteristic of maps and diagrams.
        Maps/diagrams often have visual elements spread across the page.
        """
        # Simplified heuristic: if we have significant visual content but
        # not structured like a chart, and it's not concentrated in one area,
        # assume spatial dispersion
        return (analysis.image_area_ratio >= 0.2 or analysis.drawing_count >= 10) and \
               analysis.text_length < 200

    def classify_page(self, analysis: PageAnalysis) -> ClassificationResult:
        """
        Classify a single page based on its analysis signals.

        Args:
            analysis: PageAnalysis object containing page signals

        Returns:
            ClassificationResult with classification, confidence, and reason
        """
        # Handle edge case: empty or corrupted page
        if analysis.width <= 0 or analysis.height <= 0:
            return ClassificationResult(
                classification="unknown",
                classification_confidence=0.0,
                classification_reason="Invalid page dimensions"
            )

        # Apply classification rules in order of precedence
        # 1. table_dense when page is strongly dominated by tabular structure
        if self._is_table_dense(analysis):
            return self._create_table_dense_result(analysis)
        # 2. scanned_document when native text is very low and image dominance is high
        elif self._is_scanned_document(analysis):
            return self._create_scanned_document_result(analysis)
        # 3. chart_graph when strong chart/graph signals exist
        elif self._is_chart_graph(analysis):
            return self._create_chart_graph_result(analysis)
        # 4. map_diagram when significant visual/drawing content exists but chart signals are insufficient
        elif self._is_map_diagram(analysis):
            return self._create_map_diagram_result(analysis)
        # 5. typed_text when native text clearly dominates
        elif self._is_typed_text(analysis):
            return self._create_typed_text_result(analysis)
        # 6. mixed when multiple significant content types coexist
        else:
            return self._create_mixed_result(analysis)

    def _is_scanned_document(self, analysis: PageAnalysis) -> bool:
        """
        Determine if page matches scanned_document classification.

        Criteria:
        - Very low or zero extractable text
        - High image coverage
        """
        text_condition = (
            analysis.text_length <= self.MAX_TEXT_LENGTH_FOR_SCANNED and
            analysis.text_density <= self.MAX_TEXT_DENSITY_FOR_SCANNED
        )
        image_condition = analysis.image_area_ratio >= self.SCANNED_IMAGE_COVERAGE_THRESHOLD

        return text_condition and image_condition

    def _is_table_dense(self, analysis: PageAnalysis) -> bool:
        """
        Determine if page matches table_dense classification.

        Criteria:
        - Strong table candidate signal
        - Table density takes precedence when page is clearly dominated by tabular structure
        """
        return analysis.table_candidate_score >= self.TABLE_DENSE_SCORE_THRESHOLD

    def _is_typed_text(self, analysis: PageAnalysis) -> bool:
        """
        Determine if page matches typed_text classification.

        Criteria:
        - High native text density
        - Low image dominance
        - Low table signal
        """
        text_condition = (
            analysis.text_length >= self.MIN_TEXT_LENGTH_FOR_TYPED and
            analysis.text_density >= self.MIN_TEXT_DENSITY_FOR_TYPED
        )
        image_condition = analysis.image_area_ratio < 0.1  # Low image dominance
        table_condition = analysis.table_candidate_score < 0.3  # Low table signal

        return text_condition and image_condition and table_condition

    def _is_chart_graph(self, analysis: PageAnalysis) -> bool:
        """
        Determine if page matches chart_graph classification.

        Criteria:
        - Significant line drawing content (potential chart axes/grid)
        - Some text elements (axis labels, legends, values)
        - Geometric regularity suggesting chart structure
        - Not dominated by tabular structure
        - Not primarily image-based (that's more map/diagram or scanned document)
        """
        # Must have some drawings to be a chart
        if analysis.drawing_count < 5:
            return False

        # Check for line-based drawings (axes, grid lines)
        line_ratio = self._calculate_line_drawing_ratio(analysis)
        has_line_structure = line_ratio >= self.CHART_LINE_RATIO_THRESHOLD

        # Check for text associated with drawings (labels, values)
        has_chart_text = (
            analysis.text_length > 5 and
            analysis.text_length < self.MIXED_TEXT_THRESHOLD and  # Not too much text
            analysis.drawing_count > 0
        )

        # Check for geometric regularity (consistent spacing, alignment)
        has_geometric_regularity = self._detect_chart_geometric_regularity(analysis)

        # Must not be table-dominated
        not_table_dominated = analysis.table_candidate_score < 0.4
        
        # Charts are typically not image-heavy
        not_image_heavy = analysis.image_area_ratio < 0.4  # If >40% image, likely not a chart

        return has_line_structure and (has_chart_text or has_geometric_regularity) and not_table_dominated and not_image_heavy

    def _is_map_diagram(self, analysis: PageAnalysis) -> bool:
        """
        Determine if page matches map_diagram classification.

        Criteria:
        - Significant visual content (images or complex drawings)
        - Low text density (maps/diagrams are primarily visual)
        - Not clearly a chart, table, or scanned document
        - Spatial dispersion of visual elements
        """
        # Must have significant visual content
        has_significant_visual = (
            analysis.image_area_ratio >= self.MAP_AREA_RATIO_THRESHOLD or
            analysis.drawing_count >= 15
        )

        # Low to moderate text (maps/diagrams have labels but not paragraphs)
        text_level_ok = analysis.text_length < 150  # Not text-heavy

        # Not strongly matching other categories
        not_scanned = not self._is_scanned_document(analysis)
        not_table = analysis.table_candidate_score < 0.3
        not_chart = not self._is_chart_graph(analysis)  # Avoid double classification

        # Check for spatial dispersion characteristic of maps/diagrams
        has_spatial_dispersion = self._detect_spatial_dispersion(analysis)

        return has_significant_visual and text_level_ok and not_scanned and not_table and not_chart and has_spatial_dispersion

    def _create_scanned_document_result(self, analysis: PageAnalysis) -> ClassificationResult:
        """Create classification result for scanned_document."""
        confidence = min(
            0.5 + (analysis.image_area_ratio * 0.5) +
            (0.5 if analysis.text_length == 0 else 0.0),
            1.0
        )
        reason = (
            f"Very low native text density ({analysis.text_length} chars) "
            f"combined with high image coverage ({analysis.image_area_ratio:.2f})."
        )

        return ClassificationResult(
            classification="scanned_document",
            classification_confidence=confidence,
            classification_reason=reason
        )

    def _create_table_dense_result(self, analysis: PageAnalysis) -> ClassificationResult:
        """Create classification result for table_dense."""
        confidence = min(
            0.5 + (analysis.table_candidate_score * 0.5),
            1.0
        )
        reason = (
            f"Strong table candidate signal detected "
            f"(score: {analysis.table_candidate_score:.2f})."
        )

        return ClassificationResult(
            classification="table_dense",
            classification_confidence=confidence,
            classification_reason=reason
        )

    def _create_typed_text_result(self, analysis: PageAnalysis) -> ClassificationResult:
        """Create classification result for typed_text."""
        # Base confidence on text density, adjusted for absence of competing signals
        text_confidence = min(analysis.text_density * 500, 1.0)  # Scale factor
        penalty = (
            (analysis.image_area_ratio * 0.5) +  # Penalty for images
            (analysis.table_candidate_score * 0.3)  # Penalty for table signals
        )
        confidence = max(text_confidence - penalty, 0.5)
        confidence = min(confidence, 1.0)

        reason = (
            f"High native text density ({analysis.text_length} chars, "
            f"density: {analysis.text_density:.4f}) with low visual competition."
        )

        return ClassificationResult(
            classification="typed_text",
            classification_confidence=confidence,
            classification_reason=reason
        )

    def _create_chart_graph_result(self, analysis: PageAnalysis) -> ClassificationResult:
        """Create classification result for chart_graph."""
        # Base confidence on chart-like characteristics
        line_ratio = self._calculate_line_drawing_ratio(analysis)
        text_visual_balance = min(analysis.text_length / 50.0, 1.0) if analysis.text_length > 0 else 0.3
        drawing_complexity = min(analysis.drawing_count / 20.0, 1.0)

        confidence = (
            (line_ratio * 0.4) +
            (text_visual_balance * 0.3) +
            (drawing_complexity * 0.3)
        )
        confidence = min(confidence, 0.9)  # Cap chart confidence slightly lower to allow for map_diagram distinction

        reason = (
            f"Chart/graph-like structure detected "
            f"(line ratio: {line_ratio:.2f}, text length: {analysis.text_length} chars, "
            f"drawings: {analysis.drawing_count}) suggesting potential numerical visualization."
        )

        return ClassificationResult(
            classification="chart_graph",
            classification_confidence=confidence,
            classification_reason=reason
        )

    def _create_map_diagram_result(self, analysis: PageAnalysis) -> ClassificationResult:
        """Create classification result for map_diagram."""
        # Base confidence on visual dispersion and complexity
        visual_coverage = min((analysis.image_area_ratio + min(analysis.drawing_count / 50.0, 1.0)) / 1.5, 1.0)
        text_modesty = max(0.0, 1.0 - (analysis.text_length / 300.0))  # Lower text = higher map/diagram confidence
        spatial_indicator = 0.7 if self._detect_spatial_dispersion(analysis) else 0.3

        confidence = (
            (visual_coverage * 0.4) +
            (text_modesty * 0.3) +
            (spatial_indicator * 0.3)
        )
        confidence = min(confidence, 0.85)  # Cap map/diagram confidence

        reason = (
            f"Map/diagram-like visual content detected "
            f"(image area: {analysis.image_area_ratio:.2f}, drawings: {analysis.drawing_count}, "
            f"text length: {analysis.text_length} chars) suggesting spatial/visual information."
        )

        return ClassificationResult(
            classification="map_diagram",
            classification_confidence=confidence,
            classification_reason=reason
        )

    def _create_mixed_result(self, analysis: PageAnalysis) -> ClassificationResult:
        """Create classification result for mixed."""
        # Mixed classification when multiple strong signals coexist but don't fit other categories
        # This typically means significant text AND significant visual elements
        text_signal = min(analysis.text_length / 150.0, 1.0)  # Normalize text
        visual_signal = min(
            (analysis.image_area_ratio * 0.4) +
            (min(analysis.drawing_count / 20.0, 1.0) * 0.4) +
            (analysis.table_candidate_score * 0.2),
            1.0
        )

        # Confidence based on balance of signals - mixed happens when both are substantial
        if text_signal > 0.3 and visual_signal > 0.3:
            balance = 1.0 - abs(text_signal - visual_signal)
            confidence = (text_signal + visual_signal) / 2.0
            confidence = confidence * (0.5 + balance * 0.5)  # Boost if balanced
        else:
            # If one signal is weak, lower confidence
            confidence = max(text_signal, visual_signal) * 0.6

        confidence = min(confidence, 1.0)

        reason = (
            f"Mixed content detected: text ({analysis.text_length} chars) "
            f"combined with visual/table elements "
            f"(images: {analysis.image_count}, drawings: {analysis.drawing_count}, "
            f"table score: {analysis.table_candidate_score:.2f})."
        )

        return ClassificationResult(
            classification="mixed",
            classification_confidence=confidence,
            classification_reason=reason
        )


# Convenience function for external use
def classify_page(analysis: PageAnalysis) -> ClassificationResult:
    """
    Convenience function to classify a page analysis.

    Args:
        analysis: PageAnalysis object

    Returns:
        ClassificationResult
    """
    classifier = PageClassifier()
    return classifier.classify_page(analysis)