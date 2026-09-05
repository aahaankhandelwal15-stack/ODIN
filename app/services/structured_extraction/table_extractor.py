"""
Table Extraction Module for ODIN V1 Phase 5

This module implements table extraction using OpenCV and OCR for both native PDF tables
and scanned/image-based tables. It preserves row/column structure and provides traceable
results.
"""

import cv2
import numpy as np
from typing import List, Tuple, Optional, Dict, Any
import logging
from dataclasses import dataclass, asdict
from datetime import datetime

logger = logging.getLogger(__name__)

# Try to import pytesseract and handle the case when it's not available
try:
    import pytesseract
    # Check if tesseract executable is available
    # This will raise an exception if tesseract is not installed or not in PATH
    _ = pytesseract.get_tesseract_version()
    TESSERACT_AVAILABLE = True
except Exception as e:
    TESSERACT_AVAILABLE = False
    logger.warning(f"Tesseract OCR is not available: {e}")


@dataclass
class TableCell:
    """Represents a single cell in a table."""
    text: str
    row_index: int
    column_index: int
    confidence: float = 1.0
    bounding_box: Optional[Dict[str, int]] = None  # x, y, width, height


@dataclass
class TableExtractionResult:
    """Represents the result of table extraction from a page."""
    document_id: str
    page_number: int
    table_index: int
    extraction_method: str
    rows: List[List[str]]  # 2D array of cell texts
    row_count: int
    column_count: int
    extraction_confidence: float
    structure_confidence: float
    source_artifact_reference: Optional[str] = None
    extraction_metadata: Optional[Dict[str, Any]] = None
    cell_metadata: Optional[List[List[Dict[str, Any]]]] = None  # Detailed cell info
    processed_at: str = None

    def __post_init__(self):
        if self.processed_at is None:
            self.processed_at = datetime.utcnow().isoformat() + "Z"


class TableExtractor:
    """
    Extracts tables from document images using computer vision and OCR.

    Supports both native PDF tables (where table structure is visible in lines)
    and scanned/image-based tables (where we detect grid structures and apply OCR).
    """

    def __init__(self, language: str = 'eng'):
        """
        Initialize the table extractor.

        Args:
            language: Language code for OCR (default: 'eng' for English)
        """
        self.language = language
        self.tesseract_available = TESSERACT_AVAILABLE

        # Initialize preprocessing parameters
        self._init_preprocessing_params()

        logger.debug("TableExtractor initialized")

    def _init_preprocessing_params(self):
        """Initialize preprocessing parameters for table detection."""
        # Kernels for line detection
        self.horizontal_kernel_ratio = 0.025  # 2.5% of image width
        self.vertical_kernel_ratio = 0.025   # 2.5% of image height

        # Morphological operation parameters
        self.line_min_width = 20  # Minimum line length in pixels
        self.line_max_gap = 5     # Maximum gap to connect line segments

        # Contour filtering parameters
        self.min_cell_area = 100  # Minimum area for a cell contour
        self.max_cell_aspect_ratio = 10  # Maximum width/height ratio for cells
        self.min_cell_extent = 0.1   # Minimum fill ratio (area/bounding box area)

    def extract_tables_from_image(self, image: np.ndarray,
                                source_reference: str = None) -> List[TableExtractionResult]:
        """
        Extract tables from a preprocessed image.

        Args:
            image: Preprocessed image (grayscale numpy array)
            source_reference: Reference to the source artifact (for traceability)

        Returns:
            List of TableExtractionResult objects (one per table found)
        """
        if image is None or image.size == 0:
            logger.warning("Received empty image for table extraction")
            return []

        logger.debug(f"Starting table extraction from image of shape {image.shape}")

        # Detect table structures in the image
        table_structures = self._detect_table_structures(image)

        if not table_structures:
            logger.debug("No table structures detected in image")
            return []

        logger.info(f"Detected {len(table_structures)} potential table structures")

        # Extract data from each table structure
        table_results = []
        for i, table_structure in enumerate(table_structures):
            try:
                table_result = self._extract_table_data(
                    image,
                    table_structure,
                    table_index=i,
                    source_reference=source_reference
                )
                if table_result:
                    table_results.append(table_result)
            except Exception as e:
                logger.error(f"Failed to extract data from table {i}: {e}")
                # Continue with other tables even if one fails

        return table_results

    def _detect_table_structures(self, image: np.ndarray) -> List[Dict[str, Any]]:
        """
        Detect table structures (grid patterns) in an image.

        Args:
            image: Preprocessed image (grayscale numpy array)

        Returns:
            List of dictionaries describing detected table structures
        """
        try:
            # Ensure we're working with grayscale
            if len(image.shape) == 3:
                gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            else:
                gray = image.copy()

            # Apply adaptive thresholding to get binary image
            binary = cv2.adaptiveThreshold(
                gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                cv2.THRESH_BINARY_INV, 15, 2
            )

            # Detect horizontal and vertical lines
            horizontal_lines = self._detect_horizontal_lines(binary)
            vertical_lines = self._detect_vertical_lines(binary)

            if not horizontal_lines and not vertical_lines:
                logger.debug("No lines detected for table structure")
                return []

            # Find intersections to identify table cells
            intersections = self._find_line_intersections(horizontal_lines, vertical_lines)

            if len(intersections) < 4:  # Need at least 2x2 grid for a table
                logger.debug(f"Insufficient intersections found: {len(intersections)}")
                return []

            # Group intersections into table structures
            table_structures = self._group_intersections_into_tables(
                intersections, horizontal_lines, vertical_lines, gray.shape
            )

            return table_structures

        except Exception as e:
            logger.error(f"Table structure detection failed: {e}")
            return []

    def _detect_horizontal_lines(self, binary_image: np.ndarray) -> List[Dict[str, int]]:
        """Detect horizontal lines in a binary image."""
        height, width = binary_image.shape
        horizontal_kernel_size = max(10, int(width * self.horizontal_kernel_ratio))
        horizontal_kernel = cv2.getStructuringElement(
            cv2.MORPH_RECT, (horizontal_kernel_size, 1)
        )

        # Detect horizontal lines
        horizontal_lines = cv2.morphologyEx(
            binary_image, cv2.MORPH_OPEN, horizontal_kernel, iterations=1
        )

        # Use HoughLinesP to get line segments
        lines = cv2.HoughLinesP(
            horizontal_lines, 1, np.pi/180, threshold=30,
            minLineLength=self.line_min_width, maxLineGap=self.line_max_gap
        )

        if lines is None:
            return []

        result = []
        for line in lines:
            x1, y1, x2, y2 = line[0]
            # Ensure it's roughly horizontal (more horizontal than vertical)
            if abs(x2 - x1) > abs(y2 - y1):
                result.append({
                    'x1': min(x1, x2), 'y1': y1,  # y1 == y2 for horizontal
                    'x2': max(x1, x2), 'y2': y2,
                    'length': abs(x2 - x1)
                })

        return result

    def _detect_vertical_lines(self, binary_image: np.ndarray) -> List[Dict[str, int]]:
        """Detect vertical lines in a binary image."""
        height, width = binary_image.shape
        vertical_kernel_size = max(10, int(height * self.vertical_kernel_ratio))
        vertical_kernel = cv2.getStructuringElement(
            cv2.MORPH_RECT, (1, vertical_kernel_size)
        )

        # Detect vertical lines
        vertical_lines = cv2.morphologyEx(
            binary_image, cv2.MORPH_OPEN, vertical_kernel, iterations=1
        )

        # Use HoughLinesP to get line segments
        lines = cv2.HoughLinesP(
            vertical_lines, 1, np.pi/180, threshold=30,
            minLineLength=self.line_min_width, maxLineGap=self.line_max_gap
        )

        if lines is None:
            return []

        result = []
        for line in lines:
            x1, y1, x2, y2 = line[0]
            # Ensure it's roughly vertical (more vertical than horizontal)
            if abs(y2 - y1) > abs(x2 - x1):
                result.append({
                    'x1': x1, 'y1': min(y1, y2),  # x1 == x2 for vertical
                    'x2': x2, 'y2': max(y1, y2),
                    'length': abs(y2 - y1)
                })

        return result

    def _find_line_intersections(self, horizontal_lines: List[Dict],
                               vertical_lines: List[Dict]) -> List[Dict[str, int]]:
        """Find intersection points between horizontal and vertical lines."""
        intersections = []

        for h_line in horizontal_lines:
            for v_line in vertical_lines:
                # Check if lines intersect
                if (h_line['x1'] <= v_line['x1'] <= h_line['x2'] and
                    v_line['y1'] <= h_line['y1'] <= v_line['y2']):
                    intersections.append({
                        'x': v_line['x1'],
                        'y': h_line['y1']
                    })

        return intersections

    def _group_intersections_into_tables(self, intersections: List[Dict],
                                       horizontal_lines: List[Dict],
                                       vertical_lines: List[Dict],
                                       image_shape: Tuple[int, int]) -> List[Dict[str, Any]]:
        """
        Group intersection points into distinct table structures.

        This is a simplified implementation that assumes we're looking for
        rectangular grids of intersections.
        """
        if len(intersections) < 4:
            return []

        # For now, we'll implement a simple approach:
        # Find the bounding box of all intersections and treat it as one table
        # In a more sophisticated implementation, we'd cluster intersections

        xs = [point['x'] for point in intersections]
        ys = [point['y'] for point in intersections]

        if not xs or not ys:
            return []

        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)

        # Count unique x and y coordinates to estimate grid size
        unique_xs = sorted(list(set(xs)))
        unique_ys = sorted(list(set(ys)))

        # Only consider it a table if we have a reasonable grid
        if len(unique_xs) < 2 or len(unique_ys) < 2:
            return []

        # Calculate estimated rows and columns
        estimated_cols = len(unique_xs) - 1
        estimated_rows = len(unique_ys) - 1

        # Reasonable table size constraints
        if estimated_rows < 1 or estimated_cols < 1:
            return []
        if estimated_rows > 50 or estimated_cols > 50:  # Unreasonably large
            return []

        return [{
            'bounding_box': {
                'x1': min_x, 'y1': min_y,
                'x2': max_x, 'y2': max_y
            },
            'estimated_rows': estimated_rows,
            'estimated_cols': estimated_cols,
            'intersections': intersections,
            'unique_x_coords': unique_xs,
            'unique_y_coords': unique_ys
        }]

    def _extract_table_data(self, image: np.ndarray, table_structure: Dict,
                          table_index: int, source_reference: str = None) -> Optional[TableExtractionResult]:
        """
        Extract cell data from a detected table structure.

        Args:
            image: Preprocessed image (grayscale numpy array)
            table_structure: Dictionary describing the table structure
            table_index: Index of this table on the page
            source_reference: Reference to source artifact

        Returns:
            TableExtractionResult or None if extraction failed
        """
        try:
            # Extract the table region from the image
            bbox = table_structure['bounding_box']
            table_image = image[
                bbox['y1']:bbox['y2'],
                bbox['x1']:bbox['x2']
            ].copy()

            if table_image.size == 0:
                logger.warning("Extracted table region is empty")
                return None

            logger.debug(f"Extracting data from table region of shape {table_image.shape}")

            # Get the grid coordinates
            y_coords = table_structure['unique_y_coords']
            x_coords = table_structure['unique_x_coords']

            # Adjust coordinates to be relative to the table image
            rel_y_coords = [y - bbox['y1'] for y in y_coords]
            rel_x_coords = [x - bbox['x1'] for x in x_coords]

            # Extract text from each cell using OCR
            rows = []
            cell_metadata = []

            for row_idx in range(len(rel_y_coords) - 1):
                row_data = []
                row_metadata = []

                y1 = rel_y_coords[row_idx]
                y2 = rel_y_coords[row_idx + 1]

                for col_idx in range(len(rel_x_coords) - 1):
                    x1 = rel_x_coords[col_idx]
                    x2 = rel_x_coords[col_idx + 1]

                    # Extract cell region
                    if y2 > y1 and x2 > x1:
                        cell_image = table_image[y1:y2, x1:x2]
                        cell_text, cell_confidence = self._extract_cell_text(cell_image)

                        row_data.append(cell_text)
                        row_metadata.append({
                            'confidence': cell_confidence,
                            'bounding_box': {
                                'x': bbox['x1'] + x1,
                                'y': bbox['y1'] + y1,
                                'width': x2 - x1,
                                'height': y2 - y1
                            },
                            'extraction_method': 'tesseract_ocr' if self.tesseract_available else 'none'
                        })
                    else:
                        row_data.append('')  # Empty cell
                        row_metadata.append({
                            'confidence': 0.0,
                            'bounding_box': None,
                            'extraction_method': 'none'
                        })

                rows.append(row_data)
                cell_metadata.append(row_metadata)

            # Calculate confidence metrics
            if self.tesseract_available and rows:
                # Average confidence across all non-empty cells
                confidences = []
                for row_meta in cell_metadata:
                    for cell_meta in row_meta:
                        if cell_meta['confidence'] > 0:
                            confidences.append(cell_meta['confidence'])
                extraction_confidence = sum(confidences) / len(confidences) if confidences else 0.0
            else:
                extraction_confidence = 0.5 if self.tesseract_available else 0.0

            # Structure confidence based on how well we detected the grid
            structure_confidence = min(
                len(table_structure['unique_x_coords']) * len(table_structure['unique_y_coords']) / 100.0,
                1.0
            )

            # Create result
            result = TableExtractionResult(
                document_id="",  # Will be filled by service
                page_number=0,   # Will be filled by service
                table_index=table_index,
                extraction_method="opencv_plus_ocr" if self.tesseract_available else "opencv_only",
                rows=rows,
                row_count=len(rows),
                column_count=len(rows[0]) if rows else 0,
                extraction_confidence=extraction_confidence,
                structure_confidence=structure_confidence,
                source_artifact_reference=source_reference,
                extraction_metadata={
                    'detection_method': 'line_intersection',
                    'horizontal_lines_detected': len(
                        self._detect_horizontal_lines(
                            cv2.adaptiveThreshold(
                                cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape)==3 else image,
                                255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 15, 2
                            )
                        )
                    ),
                    'vertical_lines_detected': len(
                        self._detect_vertical_lines(
                            cv2.adaptiveThreshold(
                                cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape)==3 else image,
                                255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 15, 2
                            )
                        )
                    ),
                    'intersections_found': len(table_structure['intersections'])
                },
                cell_metadata=cell_metadata
            )

            logger.info(f"Successfully extracted table with {result.row_count} rows and {result.column_count} columns")
            return result

        except Exception as e:
            logger.error(f"Table data extraction failed: {e}")
            return None

    def _extract_cell_text(self, cell_image: np.ndarray) -> Tuple[str, float]:
        """
        Extract text from a single cell image using OCR.

        Args:
            cell_image: Image of the cell (grayscale numpy array)

        Returns:
            Tuple of (extracted_text, confidence_score)
        """
        if not self.tesseract_available or cell_image.size == 0:
            return "", 0.0

        try:
            # Preprocess cell image for better OCR
            # Apply slight dilation to connect components
            kernel = np.ones((2, 2), np.uint8)
            processed = cv2.dilate(cell_image, kernel, iterations=1)

            # Configure Tesseract for single line/text block
            custom_config = r'--oem 3 --psm 6 -c tessedit_char_whitelist=0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz.,%-+/() '

            # Get OCR result with confidence
            data = pytesseract.image_to_data(
                processed,
                language=self.language,
                config=custom_config,
                output_type=pytesseract.Output.DICT
            )

            # Extract text and calculate average confidence
            text_parts = data['text']
            confidences = [int(conf) for conf in data['conf'] if int(conf) > 0]

            # Filter out empty text parts
            non_empty_parts = [text for text in text_parts if text.strip()]
            full_text = ' '.join(non_empty_parts).strip()

            # Calculate average confidence
            avg_confidence = sum(confidences) / len(confidences) / 100.0 if confidences else 0.0

            return full_text, avg_confidence

        except Exception as e:
            logger.warning(f"Cell OCR extraction failed: {e}")
            return "", 0.0