"""
Preprocessing Service for ODIN V1
Implements CPU-based preprocessing pipelines for different document types.
"""

import cv2
import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum
from app.services.processing.content_router import ProcessingProfile
from app.services.analysis.page_classifier import ClassificationResult
import logging

logger = logging.getLogger(__name__)


class PreprocessingService:
    """
    Service for applying preprocessing pipelines to document images.

    Implements CPU-only operations using OpenCV for:
    - Text cleanup and enhancement
    - Table structure preservation
    - Visual feature extraction preparation
    - Image normalization
    """

    def __init__(self):
        # Initialize preprocessing kernels and parameters
        self._init_parameters()

    def _init_parameters(self):
        """Initialize preprocessing parameters for different profiles."""
        # Morphological operation kernels
        self.text_cleanup_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        self.table_lines_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        self.visual_enhance_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))

    def preprocess_page(self, image: np.ndarray, profile: ProcessingProfile,
                       classification_result: Optional[ClassificationResult] = None) -> np.ndarray:
        """
        Apply preprocessing pipeline based on processing profile.

        Args:
            image: Input image as numpy array (grayscale or BGR)
            profile: ProcessingProfile to apply
            classification_result: Optional classification result for additional context

        Returns:
            Preprocessed image as numpy array
        """
        if image is None or image.size == 0:
            logger.warning("Received empty image for preprocessing")
            return image

        # Convert to grayscale if needed
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image.copy()

        # Apply profile-specific preprocessing
        if profile == ProcessingProfile.NONE:
            return gray
        elif profile == ProcessingProfile.LIGHT:
            return self._light_preprocessing(gray)
        elif profile == ProcessingProfile.OCR_OPTIMIZED:
            return self._ocr_optimized_preprocessing(gray, classification_result)
        elif profile == ProcessingProfile.TABLE_PRESERVING:
            return self._table_preserving_preprocessing(gray, classification_result)
        elif profile == ProcessingProfile.VISUAL:
            return self._visual_preprocessing(gray, classification_result)
        else:
            logger.warning(f"Unknown processing profile: {profile}")
            return gray

    def _light_preprocessing(self, image: np.ndarray) -> np.ndarray:
        """
        Light preprocessing for text-heavy documents.
        - Basic denoising
        - Contrast enhancement
        """
        # Denoise
        denoised = cv2.fastNlMeansDenoising(image, None, 10, 7, 21)

        # Enhance contrast using CLAHE
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(denoised)

        return enhanced

    def _ocr_optimized_preprocessing(self, image: np.ndarray,
                                   classification_result: Optional[ClassificationResult] = None) -> np.ndarray:
        """
        OCR-optimized preprocessing for scanned documents.
        - Deskewing
        - Noise reduction
        - Binarization
        - Morphological cleanup
        """
        # Denoise
        denoised = cv2.fastNlMeansDenoising(image, None, 10, 7, 21)

        # Enhance contrast
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(denoised)

        # Adaptive thresholding for binarization
        binary = cv2.adaptiveThreshold(
            enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, 11, 2
        )

        # Morphological opening to remove small noise
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        cleaned = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)

        return cleaned

    def _table_preserving_preprocessing(self, image: np.ndarray,
                                      classification_result: Optional[ClassificationResult] = None) -> np.ndarray:
        """
        Table-preserving preprocessing for tabular documents.
        - Preserve table lines and structure
        - Enhance text within cells
        - Remove background noise
        """
        # Denoise while preserving edges
        denoised = cv2.bilateralFilter(image, 9, 75, 75)

        # Enhance contrast
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
        enhanced = clahe.apply(denoised)

        # Detect and enhance horizontal/vertical lines (table structure)
        # Horizontal lines
        horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 1))
        horizontal_lines = cv2.morphologyEx(enhanced, cv2.MORPH_OPEN, horizontal_kernel)

        # Vertical lines
        vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 25))
        vertical_lines = cv2.morphologyEx(enhanced, cv2.MORPH_OPEN, vertical_kernel)

        # Combine line structures
        table_structure = cv2.addWeighted(horizontal_lines, 0.5, vertical_lines, 0.5, 0.0)

        # Enhance text regions (subtract table structure to focus on text)
        text_enhanced = cv2.subtract(enhanced, table_structure)
        text_enhanced = cv2.normalize(text_enhanced, None, 0, 255, cv2.NORM_MINMAX)

        # Combine enhanced text with table structure
        result = cv2.addWeighted(enhanced, 0.7, text_enhanced, 0.3, 0)

        return result

    def _visual_preprocessing(self, image: np.ndarray,
                            classification_result: Optional[ClassificationResult] = None) -> np.ndarray:
        """
        Visual preprocessing for charts, graphs, maps, and diagrams.
        - Preserve visual details
        - Enhance edges and contours
        - Prepare for feature extraction
        """
        # Denoise while preserving edges
        denoised = cv2.bilateralFilter(image, 9, 75, 75)

        # Enhance contrast mildly to preserve visual details
        clahe = cv2.createCLAHE(clipLimit=1.5, tileGridSize=(8, 8))
        enhanced = clahe.apply(denoised)

        # Edge enhancement for visual feature extraction
        # Use unsharp masking
        gaussian = cv2.GaussianBlur(enhanced, (0, 0), 2.0)
        sharpened = cv2.addWeighted(enhanced, 1.5, gaussian, -0.5, 0)

        # Ensure valid pixel range
        result = np.clip(sharpened, 0, 255).astype(np.uint8)

        return result

    def extract_visual_regions(self, image: np.ndarray,
                             classification_result: ClassificationResult) -> List[Dict[str, Any]]:
        """
        Extract visual regions of interest from charts, graphs, maps, and diagrams.

        Args:
            image: Preprocessed image
            classification_result: Classification result for the page

        Returns:
            List of dictionaries containing region information
        """
        regions = []

        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image.copy()

        classification = classification_result.classification

        if classification == "chart_graph":
            regions.extend(self._extract_chart_regions(gray, classification_result))
        elif classification == "map_diagram":
            regions.extend(self._extract_map_diagram_regions(gray, classification_result))

        return regions

    def _extract_chart_regions(self, image: np.ndarray,
                             classification_result: ClassificationResult) -> List[Dict[str, Any]]:
        """Extract regions of interest from charts and graphs."""
        regions = []

        # Detect contours for potential chart elements
        edges = cv2.Canny(image, 50, 150, apertureSize=3)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # Filter contours by area and aspect ratio
        for contour in contours:
            area = cv2.contourArea(contour)
            if area > 100:  # Minimum area threshold
                x, y, w, h = cv2.boundingRect(contour)
                aspect_ratio = w / h if h > 0 else 0

                # Chart elements typically have reasonable aspect ratios
                if 0.2 < aspect_ratio < 5.0:
                    regions.append({
                        "type": "chart_element",
                        "bounding_box": {"x": x, "y": y, "width": w, "height": h},
                        "area": area,
                        "aspect_ratio": aspect_ratio,
                        "confidence": min(area / 1000.0, 1.0)  # Normalize confidence
                    })

        return regions

    def _extract_map_diagram_regions(self, image: np.ndarray,
                                   classification_result: ClassificationResult) -> List[Dict[str, Any]]:
        """Extract regions of interest from maps and diagrams."""
        regions = []

        # Use template matching or feature detection for common map/diagram elements
        # For now, use contour-based approach similar to charts but with different parameters

        edges = cv2.Canny(image, 30, 100, apertureSize=3)  # Lower thresholds for maps
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # Filter for larger, more complex shapes typical of maps/diagrams
        for contour in contours:
            area = cv2.contourArea(contour)
            if area > 500:  # Higher minimum area for map features
                x, y, w, h = cv2.boundingRect(contour)

                # Calculate extent (how much of bounding box is filled)
                extent = area / (w * h) if w * h > 0 else 0

                # Maps/diagrams often have complex, irregular shapes
                if extent > 0.3:  # Not just thin lines
                    regions.append({
                        "type": "map_feature",
                        "bounding_box": {"x": x, "y": y, "width": w, "height": h},
                        "area": area,
                        "extent": extent,
                        "confidence": min(area / 5000.0, 1.0)
                    })

        return regions