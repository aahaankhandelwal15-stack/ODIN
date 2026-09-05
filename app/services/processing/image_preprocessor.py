"""
Image Preprocessor Utility for ODIN V1
Low-level image processing utilities used by preprocessing pipelines.
"""

import cv2
import numpy as np
from typing import Tuple, Optional, List, Dict
import logging

logger = logging.getLogger(__name__)


class ImagePreprocessor:
    """
    Utility class for low-level image processing operations.
    Provides reusable image processing functions for the preprocessing service.
    """

    @staticmethod
    def deskew_image(image: np.ndarray) -> np.ndarray:
        """
        Deskew an image by detecting text lines and calculating skew angle.

        Args:
            image: Grayscale input image

        Returns:
            Deskewed image
        """
        try:
            # Find all non-zero points (text pixels)
            coords = np.column_stack(np.where(image > 0))
            if len(coords) < 10:  # Not enough points
                return image

            # Calculate minimum area rectangle
            rect = cv2.minAreaRect(coords)
            angle = rect[-1]

            # Adjust angle
            if angle < -45:
                angle = -(90 + angle)
            else:
                angle = -angle

            # Rotate image to deskew
            (h, w) = image.shape[:2]
            center = (w // 2, h // 2)
            M = cv2.getRotationMatrix2D(center, angle, 1.0)
            rotated = cv2.warpAffine(image, M, (w, h),
                                   flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)

            return rotated
        except Exception as e:
            logger.warning(f"Deskewing failed: {e}")
            return image

    @staticmethod
    def remove_borders(image: np.ndarray, border_size: int = 10) -> np.ndarray:
        """
        Remove white borders from scanned document images.

        Args:
            image: Grayscale input image
            border_size: Size of border to check for removal

        Returns:
            Image with borders removed
        """
        try:
            # Find non-zero regions
            rows = np.where(np.any(image < 250, axis=1))[0]  # Non-white rows
            cols = np.where(np.any(image < 250, axis=0))[0]  # Non-white cols

            if len(rows) > 0 and len(cols) > 0:
                # Crop to content with some padding
                y_min, y_max = np.max([rows[0] - border_size, 0]), np.min([rows[-1] + border_size, image.shape[0]])
                x_min, x_max = np.max([cols[0] - border_size, 0]), np.min([cols[-1] + border_size, image.shape[1]])
                return image[y_min:y_max, x_min:x_max]
            else:
                return image
        except Exception as e:
            logger.warning(f"Border removal failed: {e}")
            return image

    @staticmethod
    def denoise_image(image: np.ndarray, method: str = "gaussian") -> np.ndarray:
        """
        Apply denoising to image.

        Args:
            image: Grayscale input image
            method: Denoising method ("gaussian", "median", "bilateral", "nl_means")

        Returns:
            Denoised image
        """
        try:
            if method == "gaussian":
                return cv2.GaussianBlur(image, (5, 5), 0)
            elif method == "median":
                return cv2.medianBlur(image, 5)
            elif method == "bilateral":
                return cv2.bilateralFilter(image, 9, 75, 75)
            elif method == "nl_means":
                return cv2.fastNlMeansDenoising(image, None, 10, 7, 21)
            else:
                return image
        except Exception as e:
            logger.warning(f"Denoising failed: {e}")
            return image

    @staticmethod
    def enhance_contrast(image: np.ndarray, method: str = "clahe") -> np.ndarray:
        """
        Enhance image contrast.

        Args:
            image: Grayscale input image
            method: Enhancement method ("clahe", "histogram_eq", "linear")

        Returns:
            Contrast-enhanced image
        """
        try:
            if method == "clahe":
                clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
                return clahe.apply(image)
            elif method == "histogram_eq":
                return cv2.equalizeHist(image)
            elif method == "linear":
                # Simple linear stretching
                return cv2.normalize(image, None, 0, 255, cv2.NORM_MINMAX)
            else:
                return image
        except Exception as e:
            logger.warning(f"Contrast enhancement failed: {e}")
            return image

    @staticmethod
    def binarize_image(image: np.ndarray, method: str = "adaptive") -> np.ndarray:
        """
        Convert grayscale image to binary (black and white).

        Args:
            image: Grayscale input image
            method: Binarization method ("adaptive", "otsu", "fixed")

        Returns:
            Binary image
        """
        try:
            if method == "adaptive":
                return cv2.adaptiveThreshold(
                    image, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                    cv2.THRESH_BINARY, 11, 2
                )
            elif method == "otsu":
                _, binary = cv2.threshold(image, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                return binary
            elif method == "fixed":
                _, binary = cv2.threshold(image, 127, 255, cv2.THRESH_BINARY)
                return binary
            else:
                return image
        except Exception as e:
            logger.warning(f"Binarization failed: {e}")
            return image

    @staticmethod
    def morphological_operation(image: np.ndarray, operation: str = "opening",
                              kernel_size: Tuple[int, int] = (3, 3),
                              iterations: int = 1) -> np.ndarray:
        """
        Apply morphological operations.

        Args:
            image: Binary input image
            operation: Morphological operation ("opening", "closing", "erosion", "dilation")
            kernel_size: Size of morphological kernel
            iterations: Number of iterations

        Returns:
            Processed image
        """
        try:
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, kernel_size)

            if operation == "opening":
                return cv2.morphologyEx(image, cv2.MORPH_OPEN, kernel, iterations=iterations)
            elif operation == "closing":
                return cv2.morphologyEx(image, cv2.MORPH_CLOSE, kernel, iterations=iterations)
            elif operation == "erosion":
                return cv2.erode(image, kernel, iterations=iterations)
            elif operation == "dilation":
                return cv2.dilate(image, kernel, iterations=iterations)
            else:
                return image
        except Exception as e:
            logger.warning(f"Morphological operation failed: {e}")
            return image

    @staticmethod
    def detect_lines(image: np.ndarray, min_length: int = 50,
                    max_gap: int = 10) -> List[Dict[str, int]]:
        """
        Detect lines in image using Hough line transform.

        Args:
            image: Binary input image (edges)
            min_length: Minimum line length to detect
            max_gap: Maximum gap between line segments to treat as single line

        Returns:
            List of detected lines with coordinates
        """
        try:
            lines = cv2.HoughLinesP(
                image, 1, np.pi / 180, threshold=50,
                minLineLength=min_length, maxLineGap=max_gap
            )

            if lines is not None:
                return [
                    {
                        "x1": int(line[0][0]), "y1": int(line[0][1]),
                        "x2": int(line[0][2]), "y2": int(line[0][3])
                    }
                    for line in lines
                ]
            else:
                return []
        except Exception as e:
            logger.warning(f"Line detection failed: {e}")
            return []

    @staticmethod
    def resize_image(image: np.ndarray, width: int = None, height: int = None) -> np.ndarray:
        """
        Resize image while maintaining aspect ratio.

        Args:
            image: Input image
            width: Target width (optional)
            height: Target height (optional)

        Returns:
            Resized image
        """
        try:
            if width is None and height is None:
                return image

            (h, w) = image.shape[:2]

            if width is None:
                ratio = height / h
                width = int(w * ratio)
            elif height is None:
                ratio = width / w
                height = int(h * ratio)

            return cv2.resize(image, (width, height), interpolation=cv2.INTER_AREA)
        except Exception as e:
            logger.warning(f"Image resize failed: {e}")
            return image