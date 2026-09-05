import fitz  # PyMuPDF
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)


class TextExtractor:
    """
    Native PDF text extraction using PyMuPDF.

    This extractor opens the original PDF and extracts text from each page.
    It does not perform any layout analysis or reconstruction.
    """

    def __init__(self):
        """Initialize the text extractor."""
        pass

    def extract_text_from_bytes(self, pdf_bytes: bytes) -> List[Optional[str]]:
        """
        Extract text from each page of a PDF provided as bytes.

        Args:
            pdf_bytes: Raw PDF file bytes

        Returns:
            List of extracted text strings, one per page (None if extraction fails for a page)
        """
        try:
            # Open PDF from bytes
            pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")
            page_count = pdf_document.page_count

            logger.info(f"Extracting text from PDF with {page_count} pages")

            extracted_texts = []
            for page_num in range(page_count):
                page = pdf_document[page_num]
                try:
                    # Extract text from the page
                    text = page.get_text("text")  # plain text
                    extracted_texts.append(text)
                except Exception as e:
                    logger.warning(f"Failed to extract text from page {page_num + 1}: {e}")
                    extracted_texts.append(None)

            pdf_document.close()
            logger.info(f"Completed text extraction from {len(extracted_texts)} pages")

            return extracted_texts

        except Exception as e:
            logger.error(f"Failed to extract text from PDF: {e}")
            raise

    def extract_text_from_bytes_with_details(self, pdf_bytes: bytes) -> List[dict]:
        """
        Extract text from each page with additional details.

        Args:
            pdf_bytes: Raw PDF file bytes

        Returns:
            List of dictionaries containing text and metadata for each page
        """
        try:
            pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")
            page_count = pdf_document.page_count

            results = []
            for page_num in range(page_count):
                page = pdf_document[page_num]
                try:
                    text = page.get_text("text")
                    # Get text length for metadata
                    text_length = len(text)
                    results.append({
                        "text": text,
                        "text_length": text_length,
                        "page_number": page_num + 1
                    })
                except Exception as e:
                    logger.warning(f"Failed to extract text from page {page_num + 1}: {e}")
                    results.append({
                        "text": None,
                        "text_length": 0,
                        "page_number": page_num + 1,
                        "error": str(e)
                    })

            pdf_document.close()
            return results

        except Exception as e:
            logger.error(f"Failed to extract text from PDF: {e}")
            raise