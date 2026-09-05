import logging
from typing import Optional, Tuple
import numpy as np

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


class OCRExtractor:
    """
    OCR extraction using Tesseract.

    This extractor takes a preprocessed image (numpy array) and extracts text using Tesseract OCR.
    It returns the extracted text and confidence when available.
    """

    def __init__(self, language: str = 'eng'):
        """
        Initialize the OCR extractor.

        Args:
            language: Language code for OCR (default: 'eng' for English)
        """
        if not TESSERACT_AVAILABLE:
            raise RuntimeError(
                "Tesseract OCR is not available. Please install Tesseract OCR and ensure it is in your PATH."
            )
        self.language = language

    def extract_text(self, image: np.ndarray) -> Tuple[Optional[str], Optional[float], dict]:
        """
        Extract text from an image using Tesseract OCR.

        Args:
            image: Preprocessed image as numpy array (grayscale)

        Returns:
            Tuple of (text, confidence, metadata)
            - text: Extracted text string, or None if OCR failed
            - confidence: OCR confidence value (0-100) if available, otherwise None
            - metadata: Additional OCR metadata (e.g., language, word confidences)
        """
        if image is None or image.size == 0:
            logger.warning("Received empty image for OCR")
            return None, None, {}

        try:
            # Perform OCR
            # We'll use image_to_data to get detailed information including confidence
            data = pytesseract.image_to_data(
                image,
                language=self.language,
                output_type=pytesseract.Output.DICT
            )

            # Extract text and confidence
            text = data['text']
            # Join non-empty text parts
            full_text = ' '.join([t for t in text if t.strip()]).strip()

            # Calculate average confidence (only for words with confidence > 0)
            confidences = [int(c) for c in data['conf'] if int(c) > 0]
            avg_confidence = sum(confidences) / len(confidences) if confidences else None

            # Prepare metadata
            metadata = {
                'language': self.language,
                'word_count': len([t for t in text if t.strip()]),
                'raw_data': data  # Optionally include raw data for debugging
            }

            logger.info(f"OCR extraction completed. Text length: {len(full_text)}, Confidence: {avg_confidence}")

            return full_text, avg_confidence, metadata

        except Exception as e:
            logger.error(f"OCR extraction failed: {e}")
            return None, None, {'error': str(e)}

    def extract_text_simple(self, image: np.ndarray) -> Optional[str]:
        """
        Extract text using the simple image_to_string method.

        Args:
            image: Preprocessed image as numpy array (grayscale)

        Returns:
            Extracted text string, or None if OCR failed
        """
        if image is None or image.size == 0:
            logger.warning("Received empty image for OCR")
            return None

        try:
            text = pytesseract.image_to_string(image, language=self.language)
            return text.strip() if text.strip() else None
        except Exception as e:
            logger.error(f"OCR extraction (simple) failed: {e}")
            return None