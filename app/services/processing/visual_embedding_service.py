"""
Visual Embedding Service for ODIN V1
Service for generating lightweight visual embeddings from image regions for multimodal indexing.
"""

import cv2
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
import logging
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler
import pickle
import os

logger = logging.getLogger(__name__)


class VisualEmbeddingService:
    """
    Service for generating lightweight visual embeddings from image regions.
    Creates compact feature vectors suitable for indexing and similarity search.
    """

    def __init__(self, embedding_dim: int = 64):
        """
        Initialize the visual embedding service.

        Args:
            embedding_dim: Target dimension for embeddings (default 64 for lightweight)
        """
        self.embedding_dim = embedding_dim
        self.scaler = StandardScaler()
        self.pca = PCA(n_components=embedding_dim)
        self.is_fitted = False

        # Feature extractors
        self.feature_extractors = [
            self._extract_hog_features,
            self._extract_lbp_features,
            self._extract_hu_moments,
            self._extract_texture_features,
            self._extract_shape_features
        ]

    def extract_features(self, image: np.ndarray,
                        regions: List[Dict[str, Any]]) -> np.ndarray:
        """
        Extract visual features from image regions and combine into embedding.

        Args:
            image: Source image (grayscale)
            regions: List of region dictionaries from visual region service

        Returns:
            Feature vector as numpy array
        """
        if image is None or image.size == 0:
            return np.zeros(self.embedding_dim)

        # Extract features from each region
        region_features = []
        for region in regions:
            features = self._extract_region_features(image, region)
            if features is not None and len(features) > 0:
                region_features.append(features)

        # Also extract global image features
        global_features = self._extract_global_features(image)
        if global_features is not None and len(global_features) > 0:
            region_features.append(global_features)

        if not region_features:
            return np.zeros(self.embedding_dim)

        # Concatenate all features
        combined_features = np.concatenate(region_features)

        # Normalize and reduce dimensionality
        embedding = self._process_features(combined_features)

        return embedding

    def _extract_region_features(self, image: np.ndarray,
                               region: Dict[str, Any]) -> Optional[np.ndarray]:
        """
        Extract features from a specific region.

        Args:
            image: Source image
            region: Region dictionary

        Returns:
            Feature vector for the region or None
        """
        try:
            # Extract region from image if bounding box provided
            if "bounding_box" in region:
                bbox = region["bounding_box"]
                x, y, w, h = bbox["x"], bbox["y"], bbox["width"], bbox["height"]
                # Ensure bounds are within image
                x = max(0, x)
                y = max(0, y)
                w = min(w, image.shape[1] - x)
                h = min(h, image.shape[0] - y)
                if w > 0 and h > 0:
                    region_image = image[y:y+h, x:x+w]
                else:
                    return None
            else:
                # Use full image if no bounding box
                region_image = image

            if region_image.size == 0:
                return None

            # Resize to standard size for feature extraction
            region_image = cv2.resize(region_image, (64, 64))

            # Extract features using multiple methods
            features = []
            for extractor in self.feature_extractors:
                try:
                    feat = extractor(region_image)
                    if feat is not None and len(feat) > 0:
                        features.extend(feat)
                except Exception as e:
                    logger.warning(f"Feature extraction failed for {extractor.__name__}: {e}")

            if features:
                return np.array(features, dtype=np.float32)
            else:
                return None

        except Exception as e:
            logger.error(f"Region feature extraction failed: {e}")
            return None

    def _extract_global_features(self, image: np.ndarray) -> Optional[np.ndarray]:
        """
        Extract global features from the entire image.

        Args:
            image: Source image

        Returns:
            Global feature vector or None
        """
        try:
            # Resize for global feature extraction
            resized = cv2.resize(image, (128, 128))

            features = []
            for extractor in self.feature_extractors:
                try:
                    feat = extractor(resized)
                    if feat is not None and len(feat) > 0:
                        features.extend(feat)
                except Exception as e:
                    logger.warning(f"Global feature extraction failed for {extractor.__name__}: {e}")

            if features:
                return np.array(features, dtype=np.float32)
            else:
                return None

        except Exception as e:
            logger.error(f"Global feature extraction failed: {e}")
            return None

    def _extract_hog_features(self, image: np.ndarray) -> List[float]:
        """
        Extract Histogram of Oriented Gradients features.
        """
        try:
            # Use HOG descriptor
            win_size = (64, 64)
            block_size = (16, 16)
            block_stride = (8, 8)
            cell_size = (8, 8)
            nbins = 9

            hog = cv2.HOGDescriptor(win_size, block_size, block_stride, cell_size, nbins)
            hog_features = hog.compute(image)

            if hog_features is not None:
                return hog_features.flatten().tolist()
            else:
                return []
        except Exception as e:
            logger.warning(f"HOG feature extraction failed: {e}")
            return []

    def _extract_lbp_features(self, image: np.ndarray) -> List[float]:
        """
        Extract Local Binary Pattern features.
        """
        try:
            # Simple LBP implementation
            lbp_image = np.zeros_like(image)
            rows, cols = image.shape

            for i in range(1, rows - 1):
                for j in range(1, cols - 1):
                    center = image[i, j]
                    code = 0
                    # 8 neighbors
                    neighbors = [
                        image[i-1, j-1], image[i-1, j], image[i-1, j+1],
                        image[i, j+1], image[i+1, j+1], image[i+1, j],
                        image[i+1, j-1], image[i, j-1]
                    ]
                    for k, neighbor in enumerate(neighbors):
                        if neighbor >= center:
                            code |= (1 << k)
                    lbp_image[i, j] = code

            # Create histogram
            hist, _ = np.histogram(lbp_image, bins=256, range=(0, 256))
            # Normalize
            hist = hist.astype(float)
            hist_sum = hist.sum()
            if hist_sum > 0:
                hist = hist / hist_sum
            return hist.tolist()
        except Exception as e:
            logger.warning(f"LBP feature extraction failed: {e}")
            return []

    def _extract_hu_moments(self, image: np.ndarray) -> List[float]:
        """
        Extract Hu Moment features (rotation invariant).
        """
        try:
            # Calculate moments
            moments = cv2.moments(image)
            if moments["m00"] != 0:
                hu_moments = cv2.HuMoments(moments)
                # Convert to log scale as recommended
                hu_moments = np.log(np.abs(hu_moments))
                return hu_moments.flatten().tolist()
            else:
                return []
        except Exception as e:
            logger.warning(f"Hu Moments feature extraction failed: {e}")
            return []

    def _extract_texture_features(self, image: np.ndarray) -> List[float]:
        """
        Extract texture features using statistical measures.
        """
        try:
            features = []
            # Basic statistical features
            features.append(np.mean(image))
            features.append(np.std(image))
            features.append(np.var(image))

            # Higher order statistics
            from scipy import stats
            features.append(stats.skew(image.flatten()))
            features.append(stats.kurtosis(image.flatten()))

            # Gradient features
            grad_x = cv2.Sobel(image, cv2.CV_64F, 1, 0, ksize=3)
            grad_y = cv2.Sobel(image, cv2.CV_64F, 0, 1, ksize=3)
            gradient_magnitude = np.sqrt(grad_x**2 + grad_y**2)
            features.append(np.mean(gradient_magnitude))
            features.append(np.std(gradient_magnitude))

            # Local binary pattern contrast
            lbp = self._compute_lbp_simple(image)
            if lbp.size > 0:
                features.append(np.std(lbp))

            return [float(f) for f in features]
        except Exception as e:
            logger.warning(f"Texture feature extraction failed: {e}")
            return []

    def _compute_lbp_simple(self, image: np.ndarray) -> np.ndarray:
        """Simple LBP computation."""
        lbp_image = np.zeros_like(image)
        rows, cols = image.shape

        for i in range(1, rows - 1):
            for j in range(1, cols - 1):
                center = image[i, j]
                code = 0
                neighbors = [
                    image[i-1, j-1], image[i-1, j], image[i-1, j+1],
                    image[i, j+1], image[i+1, j+1], image[i+1, j],
                    image[i+1, j-1], image[i, j-1]
                ]
                for k, neighbor in enumerate(neighbors):
                    if neighbor >= center:
                        code |= (1 << k)
                lbp_image[i, j] = code

        return lbp_image

    def _extract_shape_features(self, image: np.ndarray) -> List[float]:
        """
        Extract shape-based features.
        """
        try:
            features = []
            # Edge density
            edges = cv2.Canny(image, 50, 150)
            edge_density = np.sum(edges > 0) / (image.shape[0] * image.shape[1])
            features.append(edge_density)

            # Contour-based features
            contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if contours:
                areas = [cv2.contourArea(c) for c in contours]
                if areas:
                    features.append(np.mean(areas))
                    features.append(np.std(areas))
                    features.append(len(contours))  # Number of contours
                else:
                    features.extend([0.0, 0.0, 0.0])
            else:
                features.extend([0.0, 0.0, 0.0])

            # Aspect ratio of bounding box
            if contours:
                all_points = np.vstack([c.reshape(-1, 2) for c in contours])
                if len(all_points) > 0:
                    x, y, w, h = cv2.boundingRect(all_points)
                    aspect_ratio = w / h if h > 0 else 0
                    features.append(aspect_ratio)
                else:
                    features.append(0.0)
            else:
                features.append(0.0)

            return [float(f) for f in features]
        except Exception as e:
            logger.warning(f"Shape feature extraction failed: {e}")
            return []

    def _process_features(self, features: np.ndarray) -> np.ndarray:
        """
        Process raw features into final embedding.
        Applies normalization and dimensionality reduction.
        """
        try:
            # Handle empty features
            if len(features) == 0:
                return np.zeros(self.embedding_dim)

            # Reshape for sklearn
            features_2d = features.reshape(1, -1)

            # Fit transformers if not already fitted
            if not self.is_fitted:
                # For fitting, we need multiple samples - in practice this would be done
                # on a training set. For now, we'll use a simple normalization approach.
                # In production, this would be pre-fitted on a representative dataset.
                self.scaler.fit(features_2d)
                # For PCA with single sample, we'll just use the first components
                simplified_pca = PCA(n_components=min(self.embedding_dim, features_2d.shape[1]))
                simplified_pca.fit(features_2d)
                self.pca = simplified_pca
                self.is_fitted = True

            # Transform features
            normalized = self.scaler.transform(features_2d)
            reduced = self.pca.transform(normalized)

            # Ensure we have the right dimensionality
            if reduced.shape[1] < self.embedding_dim:
                # Pad with zeros
                padded = np.zeros((1, self.embedding_dim))
                padded[:, :reduced.shape[1]] = reduced
                reduced = padded
            elif reduced.shape[1] > self.embedding_dim:
                # Truncate
                reduced = reduced[:, :self.embedding_dim]

            return reduced.flatten()

        except Exception as e:
            logger.error(f"Feature processing failed: {e}")
            # Return zeros as fallback
            return np.zeros(self.embedding_dim)

    def create_embedding_from_analysis(self, image: np.ndarray,
                                     classification_result: Any,
                                     regions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Create a complete embedding result with metadata.

        Args:
            image: Source image
            classification_result: Page classification result
            regions: Extracted visual regions

        Returns:
            Dictionary containing embedding and metadata
        """
        embedding = self.extract_features(image, regions)

        result = {
            "embedding": embedding.tolist() if isinstance(embedding, np.ndarray) else embedding,
            "embedding_dim": len(embedding) if hasattr(embedding, '__len__') else self.embedding_dim,
            "num_regions": len(regions),
            "classification": classification_result.classification if classification_result else None,
            "confidence": classification_result.classification_confidence if classification_result else 0.0,
            "feature_extractors_used": [f.__name__ for f in self.feature_extractors]
        }

        return result