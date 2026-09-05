"""
Test API endpoints for Phase 2 analysis functionality
"""
from fastapi.testclient import TestClient


def test_health_endpoint():
    """Test the health endpoint still works."""
    from app.main import app
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


def test_analyze_endpoint_requires_document():
    """Test that analyze endpoint returns 404 for non-existent document."""
    from app.main import app
    client = TestClient(app)
    response = client.post("/documents/00000000-0000-0000-0000-000000000000/analyze")
    # Should return 404 since document doesn't exist
    assert response.status_code == 404


def test_get_pages_endpoint_requires_document():
    """Test that get pages endpoint returns 404 for non-existent document."""
    from app.main import app
    client = TestClient(app)
    response = client.get("/documents/00000000-0000-0000-0000-000000000000/pages")
    # Should return 404 since document doesn't exist
    assert response.status_code == 404


def test_openapi_docs_available():
    """Test that OpenAPI documentation is available."""
    from app.main import app
    client = TestClient(app)
    response = client.get("/docs")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_openapi_json_available():
    """Test that OpenAPI JSON schema is available."""
    from app.main import app
    client = TestClient(app)
    response = client.get("/openapi.json")
    assert response.status_code == 200
    data = response.json()
    assert "openapi" in data
    # Check that our new endpoints are in the schema
    paths = data["paths"]
    assert "/documents/{document_id}/analyze" in paths
    assert "/documents/{document_id}/pages" in paths