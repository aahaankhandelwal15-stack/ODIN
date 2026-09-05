"""
PDF Analyzer Module for ODIN V1 Phase 2
Responsible for extracting structural signals from PDF pages.
"""

import fitz  # PyMuPDF
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class PageAnalysis:
    """Data class representing analyzed page signals."""
    page_number: int
    width: float
    height: float
    text_length: int
    text_density: float
    image_count: int
    image_area_ratio: float
    drawing_count: int
    table_candidate_score: float
    has_extractable_text: bool

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage or transmission."""
        return {
            "page_number": self.page_number,
            "width": self.width,
            "height": self.height,
            "text_length": self.text_length,
            "text_density": self.text_density,
            "image_count": self.image_count,
            "image_area_ratio": self.image_area_ratio,
            "drawing_count": self.drawing_count,
            "table_candidate_score": self.table_candidate_score,
            "has_extractable_text": self.has_extractable_text
        }


class PDFAnalyzer:
    """
    Analyzes PDF documents to extract structural signals for page classification.

    This component focuses solely on signal extraction and does not perform
    classification. It provides measurable signals that classifiers can use.
    """

    def __init__(self):
        """Initialize the PDF analyzer."""
        pass

    def analyze_pdf(self, pdf_bytes: bytes) -> List[PageAnalysis]:
        """
        Analyze a PDF document and extract signals for each page.

        Args:
            pdf_bytes: Raw PDF file bytes

        Returns:
            List of PageAnalysis objects, one per page

        Raises:
            Exception: If PDF cannot be opened or processed
        """
        try:
            # Open PDF from bytes
            pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")
            page_count = pdf_document.page_count

            logger.info(f"Analyzing PDF with {page_count} pages")

            analyses = []

            for page_num in range(page_count):
                page = pdf_document[page_num]
                analysis = self._analyze_page(page, page_num + 1)  # Page numbers are 1-indexed
                analyses.append(analysis)

            pdf_document.close()
            logger.info(f"Completed analysis of {len(analyses)} pages")

            return analyses

        except Exception as e:
            logger.error(f"Failed to analyze PDF: {e}")
            raise

    def _analyze_page(self, page: fitz.Page, page_number: int) -> PageAnalysis:
        """
        Analyze a single PDF page and extract signals.

        Args:
            page: PyMuPDF Page object
            page_number: 1-indexed page number

        Returns:
            PageAnalysis object with extracted signals
        """
        # Get page dimensions
        rect = page.rect
        width = rect.width
        height = rect.height

        # Extract text
        text_dict = page.get_text("dict")
        extracted_text = page.get_text()
        text_length = len(extracted_text.strip())
        has_extractable_text = text_length > 0

        # Calculate text density (text length per unit area)
        page_area = width * height
        text_density = text_length / page_area if page_area > 0 else 0.0

        # Analyze images
        image_list = page.get_images()
        image_count = len(image_list)

        # Calculate image area ratio
        total_image_area = 0.0
        for img in image_list:
            # Get image bounding box
            img_info = page.get_image_bbox(img)
            if img_info:
                img_rect = fitz.Rect(img_info)
                total_image_area += img_rect.width * img_rect.height

        image_area_ratio = total_image_area / page_area if page_area > 0 else 0.0

        # Analyze drawings/vector graphics
        drawings = page.get_drawings()
        drawing_count = len(drawings)

        # Calculate table candidate score
        table_candidate_score = self._calculate_table_candidate_score(
            page, drawings, text_dict, width, height
        )

        return PageAnalysis(
            page_number=page_number,
            width=width,
            height=height,
            text_length=text_length,
            text_density=text_density,
            image_count=image_count,
            image_area_ratio=image_area_ratio,
            drawing_count=drawing_count,
            table_candidate_score=table_candidate_score,
            has_extractable_text=has_extractable_text
        )

    def _calculate_table_candidate_score(
        self,
        page: fitz.Page,
        drawings: List[Dict],
        text_dict: Dict,
        width: float,
        height: float
    ) -> float:
        """
        Calculate a heuristic table candidate score based on drawing and text patterns.

        This score indicates the likelihood that a page contains table-like structure.
        It's based on:
        - Density of line-like drawings (potential table borders/grid)
        - Regularity of drawing patterns
        - Text alignment patterns

        Returns:
            Score between 0.0 and 1.0
        """
        score = 0.0

        if not drawings:
            return score

        # Analyze drawing characteristics
        line_count = 0
        rect_count = 0

        for drawing in drawings:
            items = drawing.get("items", [])
            for item in items:
                if item[0] == "l":  # Line
                    line_count += 1
                elif item[0] == "re":  # Rectangle
                    rect_count += 1

        # Score based on line density (normalized by page area)
        page_area = width * height
        line_density = line_count / page_area if page_area > 0 else 0
        # Normalize line density score (empirical threshold: 0.01 lines per unit area)
        line_score = min(line_density / 0.01, 1.0) * 0.4

        # Score based on rectangle density (table cells often appear as rectangles)
        rect_density = rect_count / page_area if page_area > 0 else 0
        rect_score = min(rect_density / 0.005, 1.0) * 0.3  # Lower threshold for rectangles

        # Check for grid-like patterns (equal spacing indicators)
        grid_score = self._detect_grid_pattern(drawings, width, height) * 0.3

        score = line_score + rect_score + grid_score

        return min(score, 1.0)  # Cap at 1.0

    def _detect_grid_pattern(
        self,
        drawings: List[Dict],
        width: float,
        height: float
    ) -> float:
        """
        Detect grid-like patterns in drawings that might indicate table structure.

        Returns:
            Score between 0.0 and 1.0 indicating likelihood of grid pattern
        """
        if len(drawings) < 4:  # Need at least a few drawings to form a grid
            return 0.0

        # Collect all line endpoints
        points = []
        for drawing in drawings:
            items = drawing.get("items", [])
            for item in items:
                if item[0] == "l":  # Line
                    # Line format: ["l", (x0, y0), (x1, y1), ...]
                    points.append(item[1])  # Start point
                    points.append(item[2])  # End point

        if len(points) < 4:
            return 0.0

        # Simple heuristic: check for alignment of points
        # Count how many points share similar x or y coordinates (within tolerance)
        tolerance = max(width, height) * 0.02  # 2% tolerance

        x_coords = [p[0] for p in points]
        y_coords = [p[1] for p in points]

        # Count clustered coordinates
        x_clusters = self._count_coordinate_clusters(x_coords, tolerance)
        y_clusters = self._count_coordinate_clusters(y_coords, tolerance)

        # Grid pattern indicated by multiple strong clusters in both dimensions
        grid_indication = min(x_clusters, y_clusters) / 5.0  # Normalize

        return min(grid_indication, 1.0)

    def _count_coordinate_clusters(
        self,
        coords: List[float],
        tolerance: float
    ) -> int:
        """
        Count clusters of coordinates within a given tolerance.

        Returns:
            Number of distinct clusters
        """
        if not coords:
            return 0

        sorted_coords = sorted(coords)
        clusters = 1
        current_cluster_start = sorted_coords[0]

        for coord in sorted_coords[1:]:
            if coord - current_cluster_start > tolerance:
                clusters += 1
                current_cluster_start = coord

        return clusters


# Convenience function for external use
def analyze_pdf_bytes(pdf_bytes: bytes) -> List[PageAnalysis]:
    """
    Convenience function to analyze PDF bytes.

    Args:
        pdf_bytes: Raw PDF file bytes

    Returns:
        List of PageAnalysis objects
    """
    analyzer = PDFAnalyzer()
    return analyzer.analyze_pdf(pdf_bytes)