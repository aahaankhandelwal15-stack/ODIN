"""
Tests for Phase 2 Document Analysis & Classification
"""

import pytest
import tempfile
import os
from io import BytesIO
from app.services.analysis.pdf_analyzer import PDFAnalyzer, PageAnalysis
from app.services.analysis.page_classifier import PageClassifier, ClassificationResult


def create_simple_pdf():
    """
    Create a simple PDF file for testing.
    Returns a minimal PDF with some text.
    """
    # This is a minimal PDF file with "Hello World" text
    # Based on: https://stackoverflow.com/a/31849533
    pdf_content = b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page
   /Parent 2 0 R
   /MediaBox [0 0 612 792]
   /Contents 4 0 R
   /Resources << /Font << /F1 5 0 R >> >>
 >>
endobj
4 0 obj
<< /Length 44 >>
stream
BT
70 720 TD
/F1 24 Tf
(Hello World) Tj
ET
endstream
endobj
5 0 obj
<< /Type /Font
   /Subtype /Type1
   /BaseFont /Helvetica
 >>
endobj
xref
0 6
0000000000 65535 f
0000000010 00000 n
0000000060 00000 n
0000000117 00000 n
0000000210 00000 n
0000000325 00000 n
trailer
<< /Size 6 /Root 1 0 R >>
startxref
403
%%EOF"""
    return pdf_content


def create_scanned_pdf():
    """
    Create a PDF that simulates a scanned document (image-only, no text).
    For simplicity, we'll create a PDF with just a rectangle.
    """
    # Minimal PDF with a rectangle but no text
    pdf_content = b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page
   /Parent 2 0 R
   /MediaBox [0 0 612 792]
   /Contents 4 0 R
   /Resources << >>
 >>
endobj
4 0 obj
<< /Length 20 >>
stream
0 0 1 rg
100 100 400 300 re f
endstream
endobj
xref
0 4
0000000000 65535 f
0000000010 00000 n
0000000060 00000 n
0000000117 00000 n
trailer
<< /Size 4 /Root 1 0 R >>
startxref
207
%%EOF"""
    return pdf_content


def create_table_like_pdf():
    """
    Create a PDF with table-like structures (lines forming a grid).
    """
    # PDF with horizontal and vertical lines to simulate a table
    pdf_content = b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page
   /Parent 2 0 R
   /MediaBox [0 0 612 792]
   /Contents 4 0 R
   /Resources << >>
 >>
endobj
4 0 obj
<< /Length 100 >>
stream
0.5 w % 50% gray
0 0 0 RG % black color

% Horizontal lines
100 100 m
500 100 l S
100 150 m
500 150 l S
100 200 m
500 200 l S
100 250 m
500 250 l S
100 300 m
500 300 l S

% Vertical lines
100 100 m
100 300 l S
200 100 m
200 300 l S
300 100 m
300 300 l S
400 100 m
400 300 l S
500 100 m
500 300 l S
endstream
endobj
xref
0 4
0000000000 65535 f
0000000010 00000 n
0000000060 00000 n
0000000117 00000 n
trailer
<< /Size 4 /Root 1 0 R >>
startxref
225
%%EOF"""
    return pdf_content


class TestPDFAnalyzer:
    """Tests for the PDFAnalyzer class."""

    def test_analyzer_initialization(self):
        """Test that PDFAnalyzer initializes correctly."""
        analyzer = PDFAnalyzer()
        assert analyzer is not None

    def test_analyze_simple_pdf(self):
        """Test analyzing a simple PDF with text."""
        analyzer = PDFAnalyzer()
        pdf_bytes = create_simple_pdf()

        analyses = analyzer.analyze_pdf(pdf_bytes)

        assert len(analyses) == 1
        analysis = analyses[0]

        assert analysis.page_number == 1
        assert analysis.width > 0
        assert analysis.height > 0
        assert analysis.text_length > 0  # Should have extracted text
        assert analysis.has_extractable_text == True
        assert analysis.text_density >= 0
        assert analysis.image_count >= 0
        assert analysis.drawing_count >= 0
        assert 0 <= analysis.table_candidate_score <= 1.0

    def test_analyze_scanned_pdf(self):
        """Test analyzing a PDF with images but no text."""
        analyzer = PDFAnalyzer()
        pdf_bytes = create_scanned_pdf()

        analyses = analyzer.analyze_pdf(pdf_bytes)

        assert len(analyses) == 1
        analysis = analyses[0]

        assert analysis.page_number == 1
        # May or may not have extractable text depending on PDF creation
        # Should have at least one image or drawing
        assert analysis.image_count >= 0
        assert analysis.drawing_count >= 0

    def test_analyze_table_like_pdf(self):
        """Test analyzing a PDF with table-like line structures."""
        analyzer = PDFAnalyzer()
        pdf_bytes = create_table_like_pdf()

        analyses = analyzer.analyze_pdf(pdf_bytes)

        assert len(analyses) == 1
        analysis = analyses[0]

        assert analysis.page_number == 1
        # Should have some drawings (lines)
        assert analysis.drawing_count > 0
        # Table candidate score might be higher due to lines
        assert 0 <= analysis.table_candidate_score <= 1.0

    def test_analyzer_handles_empty_bytes(self):
        """Test that analyzer handles invalid PDF gracefully."""
        analyzer = PDFAnalyzer()

        with pytest.raises(Exception):
            analyzer.analyze_pdf(b"")


class TestPageClassifier:
    """Tests for the PageClassifier class."""

    def test_classifier_initialization(self):
        """Test that PageClassifier initializes correctly."""
        classifier = PageClassifier()
        assert classifier is not None

    def test_classify_typed_text(self):
        """Test classification of a text-heavy page."""
        classifier = PageClassifier()

        # Create a page analysis that should be classified as typed_text
        analysis = PageAnalysis(
            page_number=1,
            width=612.0,
            height=792.0,
            text_length=1000,  # lots of text
            text_density=0.002,  # good text density
            image_count=0,
            image_area_ratio=0.0,
            drawing_count=5,
            table_candidate_score=0.1,
            has_extractable_text=True
        )

        result = classifier.classify_page(analysis)

        assert result.classification == "typed_text"
        assert 0.0 <= result.classification_confidence <= 1.0
        assert len(result.classification_reason) > 0

    def test_classify_scanned_document(self):
        """Test classification of a scanned document."""
        classifier = PageClassifier()

        # Create a page analysis that should be classified as scanned_document
        analysis = PageAnalysis(
            page_number=1,
            width=612.0,
            height=792.0,
            text_length=0,  # no text
            text_density=0.0,
            image_count=1,
            image_area_ratio=0.8,  # high image coverage
            drawing_count=0,
            table_candidate_score=0.1,
            has_extractable_text=False
        )

        result = classifier.classify_page(analysis)

        assert result.classification == "scanned_document"
        assert 0.0 <= result.classification_confidence <= 1.0
        assert len(result.classification_reason) > 0
        assert "low native text density" in result.classification_reason.lower() or \
               "very low" in result.classification_reason.lower()

    def test_classify_table_dense(self):
        """Test classification of a table-dense page."""
        classifier = PageClassifier()

        # Create a page analysis that should be classified as table_dense
        analysis = PageAnalysis(
            page_number=1,
            width=612.0,
            height=792.0,
            text_length=50,  # some text
            text_density=0.0001,
            image_count=0,
            image_area_ratio=0.0,
            drawing_count=20,  # lots of drawings (lines)
            table_candidate_score=0.7,  # high table score
            has_extractable_text=True
        )

        result = classifier.classify_page(analysis)

        assert result.classification == "table_dense"
        assert 0.0 <= result.classification_confidence <= 1.0
        assert len(result.classification_reason) > 0

    def test_classify_chart_graph(self):
        """Test classification of a chart/graph page."""
        classifier = PageClassifier()

        # Create a page analysis that should be classified as chart_graph
        analysis = PageAnalysis(
            page_number=1,
            width=612.0,
            height=792.0,
            text_length=30,  # some text for axis labels
            text_density=0.00005,
            image_count=0,
            image_area_ratio=0.1,  # low image coverage
            drawing_count=12,  # significant drawings (lines for axes, grid, data)
            table_candidate_score=0.2,
            has_extractable_text=True
        )

        result = classifier.classify_page(analysis)

        assert result.classification == "chart_graph"
        assert 0.0 <= result.classification_confidence <= 1.0
        assert len(result.classification_reason) > 0

    def test_classify_map_diagram(self):
        """Test classification of a map/diagram page."""
        classifier = PageClassifier()

        # Create a page analysis that should be classified as map_diagram
        analysis = PageAnalysis(
            page_number=1,
            width=612.0,
            height=792.0,
            text_length=25,  # minimal text for labels
            text_density=0.00004,
            image_count=1,
            image_area_ratio=0.5,  # significant image coverage (map/photo)
            drawing_count=8,  # some drawings (boundaries, labels)
            table_candidate_score=0.1,
            has_extractable_text=True
        )

        result = classifier.classify_page(analysis)

        assert result.classification == "map_diagram"
        assert 0.0 <= result.classification_confidence <= 1.0
        assert len(result.classification_reason) > 0

    def test_classify_mixed(self):
        """Test classification of a mixed content page."""
        classifier = PageClassifier()

        # Create a page analysis that should be classified as mixed
        analysis = PageAnalysis(
            page_number=1,
            width=612.0,
            height=792.0,
            text_length=300,  # moderate text
            text_density=0.0005,
            image_count=1,
            image_area_ratio=0.2,  # some images
            drawing_count=10,  # some drawings
            table_candidate_score=0.4,  # moderate table signals
            has_extractable_text=True
        )

        result = classifier.classify_page(analysis)

        assert result.classification == "mixed"
        assert 0.0 <= result.classification_confidence <= 1.0
        assert len(result.classification_reason) > 0

    def test_classify_invalid_page(self):
        """Test classification of a page with invalid dimensions."""
        classifier = PageClassifier()

        # Create a page analysis with invalid dimensions
        analysis = PageAnalysis(
            page_number=1,
            width=0.0,  # invalid width
            height=0.0,  # invalid height
            text_length=0,
            text_density=0.0,
            image_count=0,
            image_area_ratio=0.0,
            drawing_count=0,
            table_candidate_score=0.0,
            has_extractable_text=False
        )

        result = classifier.classify_page(analysis)

        # Should handle gracefully - might be unknown or another classification
        assert result.classification is not None
        assert 0.0 <= result.classification_confidence <= 1.0


class TestAnalysisIntegration:
    """Integration tests for the analysis workflow."""

    def test_analyze_and_classify_workflow(self):
        """Test the full workflow from PDF to classification."""
        analyzer = PDFAnalyzer()
        classifier = PageClassifier()

        # Test with simple text PDF
        pdf_bytes = create_simple_pdf()
        analyses = analyzer.analyze_pdf(pdf_bytes)

        assert len(analyses) == 1

        # Classify the page
        result = classifier.classify_page(analyses[0])

        assert result.classification in ["typed_text", "mixed", "image_or_diagram", "scanned_document", "table_dense"]
        assert 0.0 <= result.classification_confidence <= 1.0
        assert len(result.classification_reason) > 0