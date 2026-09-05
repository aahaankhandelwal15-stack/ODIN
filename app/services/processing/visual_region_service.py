"""
Visual Region Service for ODIN V1
Service for extracting and processing visual regions from charts, graphs, maps, and diagrams.
"""

import cv2
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
import logging
from app.services.analysis.page_classifier import ClassificationResult
from app.services.processing.image_preprocessor import ImagePreprocessor

logger = logging.getLogger(__name__)


class VisualRegionService:
    """
    Service for extracting visual regions of interest from document images.
    Specialized for charts, graphs, maps, and diagrams.
    """

    def __init__(self):
        self.image_preprocessor = ImagePreprocessor()

    def extract_visual_regions(self, image: np.ndarray,
                             classification_result: ClassificationResult) -> List[Dict[str, Any]]:
        """
        Extract visual regions based on page classification.

        Args:
            image: Preprocessed image (grayscale numpy array)
            classification_result: Classification result for the page

        Returns:
            List of visual region dictionaries
        """
        regions = []

        classification = classification_result.classification.lower()

        if classification == "chart_graph":
            regions = self._extract_chart_regions(image, classification_result)
        elif classification == "map_diagram":
            regions = self._extract_map_diagram_regions(image, classification_result)
        elif classification == "table_dense":
            # Tables can have visual structure worth preserving
            regions = self._extract_table_regions(image, classification_result)
        # For other classifications, return empty list (no special visual regions)

        return regions

    def _extract_chart_regions(self, image: np.ndarray,
                             classification_result: ClassificationResult) -> List[Dict[str, Any]]:
        """
        Extract regions of interest from charts and graphs.
        Focuses on axes, data points, legends, and grid lines.
        """
        regions = []

        try:
            # Enhance edges for better detection
            edges = cv2.Canny(image, 30, 100, apertureSize=3)

            # Detect lines (axes, grid lines)
            lines = self.image_preprocessor.detect_lines(
                edges, min_length=20, max_gap=5
            )

            # Detect contours (data points, bars, pie slices, etc.)
            contours, hierarchy = cv2.findContours(
                edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )

            # Process detected lines as potential axes/grid
            if lines:
                horizontal_lines = []
                vertical_lines = []

                for line in lines:
                    dx = abs(line["x2"] - line["x1"])
                    dy = abs(line["y2"] - line["y1"])
                    if dx > dy * 2:  # More horizontal than vertical
                        horizontal_lines.append(line)
                    elif dy > dx * 2:  # More vertical than horizontal
                        vertical_lines.append(line)

                if horizontal_lines:
                    regions.append({
                        "type": "horizontal_grid_lines",
                        "lines": horizontal_lines,
                        "purpose": "axis_reference_or_grid",
                        "confidence": 0.8
                    })

                if vertical_lines:
                    regions.append({
                        "type": "vertical_grid_lines",
                        "lines": vertical_lines,
                        "purpose": "axis_reference_or_grid",
                        "confidence": 0.8
                    })

            # Process contours as potential data elements
            significant_contours = []
            for contour in contours:
                area = cv2.contourArea(contour)
                if area > 20:  # Filter out tiny noise
                    x, y, w, h = cv2.boundingRect(contour)
                    aspect_ratio = w / h if h > 0 else 0
                    extent = area / (w * h) if w * h > 0 else 0

                    # Filter for reasonable chart elements
                    if 0.1 < aspect_ratio < 10 and extent > 0.3:
                        significant_contours.append({
                            "contour": contour,
                            "area": area,
                            "bounding_box": {"x": x, "y": y, "width": w, "height": h},
                            "aspect_ratio": aspect_ratio,
                            "extent": extent
                        })

            if significant_contours:
                regions.append({
                    "type": "chart_data_elements",
                    "contours": significant_contours,
                    "purpose": "data_points_bars_pie_slices",
                    "count": len(significant_contours),
                    "confidence": 0.7
                })

            # Look for potential legend areas (typically in corners with color variety)
            # For grayscale, we'll look for areas with varied texture
            legend_regions = self._detect_legend_areas(image)
            if legend_regions:
                regions.extend(legend_regions)

        except Exception as e:
            logger.error(f"Chart region extraction failed: {e}")

        return regions

    def _extract_map_diagram_regions(self, image: np.ndarray,
                                   classification_result: ClassificationResult) -> List[Dict[str, Any]]:
        """
        Extract regions of interest from maps and diagrams.
        Focuses on geographic features, symbols, labels, and spatial relationships.
        """
        regions = []

        try:
            # Apply different processing for maps vs diagrams
            # For now, use a general approach that works for both

            # Detect edges and contours
            edges = cv2.Canny(image, 20, 80, apertureSize=3)  # Lower thresholds for fine details
            contours, hierarchy = cv2.findContours(
                edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )

            # Process contours as map features
            significant_contours = []
            for contour in contours:
                area = cv2.contourArea(contour)
                if area > 100:  # Minimum area for map features
                    x, y, w, h = cv2.boundingRect(contour)
                    extent = area / (w * h) if w * h > 0 else 0

                    # Calculate shape complexity
                    perimeter = cv2.arcLength(contour, True)
                    if perimeter > 0:
                        compactness = (4 * np.pi * area) / (perimeter * perimeter)
                    else:
                        compactness = 0

                    # Map features: vary in shape complexity
                    # Diagrams: often more geometric
                    significant_contours.append({
                        "contour": contour,
                        "area": area,
                        "bounding_box": {"x": x, "y": y, "width": w, "height": h},
                        "extent": extent,
                        "compactness": compactness,
                        "perimeter": perimeter
                    })

            if significant_contours:
                regions.append({
                    "type": "map_diagram_features",
                    "contours": significant_contours,
                    "purpose": "geographic_features_symbols",
                    "count": len(significant_contours),
                    "confidence": 0.75
                })

            # Detect potential text/label areas (typically have high frequency content)
            label_areas = self._detect_label_areas(image)
            if label_areas:
                regions.extend(label_areas)

            # Detect color regions if we had color (for now in grayscale, look for intensity variations)
            intensity_regions = self._detect_intensity_regions(image)
            if intensity_regions:
                regions.extend(intensity_regions)

        except Exception as e:
            logger.error(f"Map/diagram region extraction failed: {e}")

        return regions

    def _extract_table_regions(self, image: np.ndarray,
                             classification_result: ClassificationResult) -> List[Dict[str, Any]]:
        """
        Extract regions of interest from table-dense pages.
        Focuses on grid structure and cell boundaries.
        """
        regions = []

        try:
            # Detect table structure using line detection
            edges = cv2.Canny(image, 50, 150, apertureSize=3)

            # Detect horizontal and vertical lines (table structure)
            horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 1))
            vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 25))

            horizontal_lines = cv2.morphologyEx(edges, cv2.MORPH_OPEN, horizontal_kernel)
            vertical_lines = cv2.morphologyEx(edges, cv2.MORPH_OPEN, vertical_kernel)

            # Find line segments
            h_lines = self.image_preprocessor.detect_lines(
                horizontal_lines, min_length=30, max_gap=5
            )
            v_lines = self.image_preprocessor.detect_lines(
                vertical_lines, min_length=30, max_gap=5
            )

            if h_lines or v_lines:
                regions.append({
                    "type": "table_structure",
                    "horizontal_lines": h_lines,
                    "vertical_lines": v_lines,
                    "purpose": "grid_cell_boundaries",
                    "h_count": len(h_lines),
                    "v_count": len(v_lines),
                    "confidence": 0.8
                })

            # Detect potential header regions (often have different text characteristics)
            # This would require more sophisticated text analysis

        except Exception as e:
            logger.error(f"Table region extraction failed: {e}")

        return regions

    def _detect_legend_areas(self, image: np.ndarray) -> List[Dict[str, Any]]:
        """
        Detect potential legend areas in charts (typically in corners).
        """
        regions = []
        try:
            h, w = image.shape

            # Check four corners for potential legend areas
            corner_size = min(w, h) // 4
            corners = [
                (0, 0, corner_size, corner_size),                           # Top-left
                (w - corner_size, 0, corner_size, corner_size),             # Top-right
                (0, h - corner_size, corner_size, corner_size),             # Bottom-left
                (w - corner_size, h - corner_size, corner_size, corner_size) # Bottom-right
            ]

            for i, (x, y, cw, ch) in enumerate(corners):
                if cw > 10 and ch > 10:  # Minimum size
                    corner_region = image[y:y+ch, x:x+cw]
                    # Calculate texture variance (legends often have varied patterns)
                    if corner_region.size > 0:
                        variance = np.var(corner_region.astype(float))
                        if variance > 100:  # Arbitrary threshold for texture
                            regions.append({
                                "type": "potential_legend",
                                "corner": ["top-left", "top-right", "bottom-left", "bottom-right"][i],
                                "bounding_box": {"x": x, "y": y, "width": cw, "height": ch},
                                "texture_variance": float(variance),
                                "purpose": "legend_or_key",
                                "confidence": min(variance / 1000.0, 0.9)
                            })
        except Exception as e:
            logger.warning(f"Legend detection failed: {e}")

        return regions

    def _detect_label_areas(self, image: np.ndarray) -> List[Dict[str, Any]]:
        """
        Detect potential label/text areas in maps and diagrams.
        """
        regions = []
        try:
            # Use morphological operations to find areas with character-like shapes
            # Labels often have small, dense components

            # Apply edge detection
            edges = cv2.Canny(image, 30, 100, apertureSize=3)

            # Dilate to connect character components
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
            dilated = cv2.dilate(edges, kernel, iterations=2)

            # Find contours
            contours, _ = cv2.findContours(
                dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )

            # Filter for label-like contours (small to medium size, certain aspect ratios)
            label_contours = []
            for contour in contours:
                area = cv2.contourArea(contour)
                if 10 < area < 500:  # Label-sized areas
                    x, y, w, h = cv2.boundingRect(contour)
                    aspect_ratio = w / h if h > 0 else 0
                    # Labels are often wider than tall or roughly square
                    if 0.3 < aspect_ratio < 3.0:
                        label_contours.append({
                            "contour": contour,
                            "area": area,
                            "bounding_box": {"x": x, "y": y, "width": w, "height": h},
                            "aspect_ratio": aspect_ratio
                        })

            if label_contours:
                regions.append({
                    "type": "label_areas",
                    "contours": label_contours,
                    "purpose": "text_labels_annotations",
                    "count": len(label_contours),
                    "confidence": 0.6
                })

        except Exception as e:
            logger.warning(f"Label area detection failed: {e}")

        return regions

    def _detect_intensity_regions(self, image: np.ndarray) -> List[Dict[str, Any]]:
        """
        Detect regions with distinct intensity patterns (useful for color-coded maps).
        """
        regions = []
        try:
            # Apply thresholding at multiple levels to find intensity bands
            thresholds = [50, 100, 150, 200]
            intensity_regions = []

            for thresh in thresholds:
                _, binary = cv2.threshold(image, thresh, 255, cv2.THRESH_BINARY_INV)
                contours, _ = cv2.findContours(
                    binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
                )

                # Filter contours by size
                for contour in contours:
                    area = cv2.contourArea(contour)
                    if area > 50:  # Minimum size for intensity regions
                        x, y, w, h = cv2.boundingRect(contour)
                        intensity_regions.append({
                            "threshold": thresh,
                            "area": area,
                            "bounding_box": {"x": x, "y": y, "width": w, "height": h}
                        })

            if intensity_regions:
                regions.append({
                    "type": "intensity_bands",
                    "regions": intensity_regions,
                    "purpose": "color_coded_regions_temperature_etc",
                    "count": len(intensity_regions),
                    "confidence": 0.5
                })

        except Exception as e:
            logger.warning(f"Intensity region detection failed: {e}")

        return regions

    def extract_chart_features(self, image: np.ndarray,
                             region: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract specific features from chart regions for further processing.

        Args:
            image: Source image
            region: Region dictionary from extract_visual_regions

        Returns:
            Dictionary of extracted features
        """
        features = {}

        try:
            region_type = region.get("type", "")

            if region_type == "chart_data_elements":
                # Extract features from data points/bars/etc.
                contours = region.get("contours", [])
                features = {
                    "element_count": len(contours),
                    "areas": [c["area"] for c in contours],
                    "average_area": np.mean([c["area"] for c in contours]) if contours else 0,
                    "size_variance": np.var([c["area"] for c in contours]) if len(contours) > 1 else 0
                }

            elif region_type == "horizontal_grid_lines" or region_type == "vertical_grid_lines":
                # Extract grid line features
                lines = region.get("lines", [])
                if lines:
                    if region_type == "horizontal_grid_lines":
                        lengths = [abs(l["x2"] - l["x1"]) for l in lines]
                        positions = [min(l["y1"], l["y2"]) for l in lines]  # Y positions
                    else:
                        lengths = [abs(l["y2"] - l["y1"]) for l in lines]
                        positions = [min(l["x1"], l["x2"]) for l in lines]  # X positions

                    features = {
                        "line_count": len(lines),
                        "average_length": np.mean(lengths) if lengths else 0,
                        "length_variance": np.var(lengths) if len(lengths) > 1 else 0,
                        "position_spacing": np.diff(sorted(positions)) if len(positions) > 1 else [],
                        "regularity": 1.0 - (np.var(np.diff(sorted(positions))) /
                                           (np.mean(np.diff(sorted(positions))) + 1e-6)) if len(positions) > 2 else 0
                    }

        except Exception as e:
            logger.error(f"Feature extraction failed for region {region_type}: {e}")

        return features