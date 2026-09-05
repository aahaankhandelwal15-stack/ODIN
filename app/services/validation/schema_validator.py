"""
Schema and type validation for extraction results.
"""

import logging
import uuid
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, ValidationError, field_validator
from app.models.extraction import DocumentTextExtraction
from app.models.structured_extraction import DocumentTableExtraction, DocumentChartAssociation

logger = logging.getLogger(__name__)


class TextExtractionSchema(BaseModel):
    """Schema for validating text extraction results."""
    document_id: str
    page_number: int
    extraction_method: str
    raw_text: Optional[str] = None
    normalized_text: Optional[str] = None
    confidence: Optional[float] = None
    language: Optional[str] = None
    extraction_metadata: Optional[Dict[str, Any]] = None

    @field_validator('page_number')
    @classmethod
    def page_number_positive(cls, v):
        if v <= 0:
            raise ValueError('Page_number must be positive')
        return v

    @field_validator('confidence')
    @classmethod
    def confidence_range(cls, v):
        if v is not None and (v < 0.0 or v > 1.0):
            raise ValueError('Confidence must be between 0.0 and 1.0')
        return v


class TableExtractionSchema(BaseModel):
    """Schema for validating table extraction results."""
    document_id: str
    page_number: int
    table_index: int
    extraction_method: str
    row_count: int
    column_count: int
    table_data: List[List[str]]
    extraction_confidence: Optional[float] = None
    structure_confidence: Optional[float] = None
    source_artifact_reference: Optional[str] = None
    extraction_metadata: Optional[Dict[str, Any]] = None
    cell_metadata: Optional[List[List[Dict[str, Any]]]] = None

    @field_validator('page_number', 'table_index')
    @classmethod
    def non_negative(cls, v):
        if v < 0:
            raise ValueError('Page/table index must be non-negative')
        return v

    @field_validator('row_count', 'column_count')
    @classmethod
    def positive_count(cls, v):
        if v <= 0:
            raise ValueError('Row/column count must be positive')
        return v

    @field_validator('extraction_confidence', 'structure_confidence')
    @classmethod
    def confidence_range(cls, v):
        if v is not None and (v < 0.0 or v > 1.0):
            raise ValueError('Confidence must be between 0.0 and 1.0')
        return v

    @field_validator('table_data')
    @classmethod
    def table_data_consistent(cls, v):
        if not v:
            raise ValueError('Table data cannot be empty')
        if len(v) == 0:
            raise ValueError('Table must have at least one row')
        first_row_len = len(v[0]) if v[0] else 0
        for i, row in enumerate(v):
            if len(row) != first_row_len:
                raise ValueError(f'Row {i} has inconsistent column count: expected {first_row_len}, got {len(row)}')
        return v


class ChartAssociationSchema(BaseModel):
    """Schema for validating chart association results."""
    document_id: str
    page_number: int
    chart_index: int
    associated_table_id: Optional[str] = None
    association_method: str
    association_confidence: float
    chart_metadata: Optional[Dict[str, Any]] = None
    resolution_status: str

    @field_validator('page_number', 'chart_index')
    @classmethod
    def non_negative(cls, v):
        if v < 0:
            raise ValueError('Page/chart index must be non-negative')
        return v

    @field_validator('association_confidence')
    @classmethod
    def confidence_range(cls, v):
        if v < 0.0 or v > 1.0:
            raise ValueError('Association confidence must be between 0.0 and 1.0')
        return v

    @field_validator('resolution_status')
    @classmethod
    def valid_resolution_status(cls, v):
        valid_statuses = ['resolved', 'unresolved', 'partial']
        if v not in valid_statuses:
            raise ValueError(f'Resolution status must be one of {valid_statuses}')
        return v


class SchemaValidator:
    """
    Validates extraction results against expected schemas using Pydantic v2.
    """

    def __init__(self):
        """Initialize the schema validator."""
        logger.debug("SchemaValidator initialized")

    def validate_text_extraction(self, extraction: DocumentTextExtraction) -> List[Dict[str, Any]]:
        """
        Validate a text extraction result.

        Args:
            extraction: DocumentTextExtraction model instance

        Returns:
            List of validation findings (empty if all passed)
        """
        findings = []
        try:
            # Convert SQLAlchemy model to dict for validation
            extraction_dict = {
                'document_id': str(extraction.document_id) if isinstance(extraction.document_id, uuid.UUID) else extraction.document_id,
                'page_number': extraction.page_number,
                'extraction_method': extraction.extraction_method,
                'raw_text': extraction.raw_text,
                'normalized_text': extraction.normalized_text,
                'confidence': extraction.confidence,
                'language': extraction.language,
                'extraction_metadata': extraction.extraction_metadata
            }

            # Validate against schema
            TextExtractionSchema.model_validate(extraction_dict)
            logger.debug(f"Text extraction validation passed for document {extraction.document_id}, page {extraction.page_number}")

        except ValidationError as e:
            for error in e.errors():
                findings.append({
                    'validator': 'schema',
                    'check_name': f'text_extraction_{error["loc"][0] if error["loc"] else "unknown"}',
                    'status': 'failed',
                    'severity': 'error',
                    'message': f"Schema validation failed: {error['msg']}",
                    'page_number': extraction.page_number,
                    'details': {
                        'field': str(error['loc']) if error['loc'] else None,
                        'input': error.get('input'),
                        'type': error['type']
                    }
                })
                logger.warning(f"Text extraction schema validation failed: {error['msg']}")
        except Exception as e:
            findings.append({
                'validator': 'schema',
                'check_name': 'text_extraction_validation_error',
                'status': 'error',
                'severity': 'critical',
                'message': f"Validation process failed: {str(e)}",
                'page_number': extraction.page_number,
                'details': {'exception': str(e)}
            })
            logger.error(f"Text extraction validation error: {str(e)}")

        return findings

    def validate_table_extraction(self, table: DocumentTableExtraction) -> List[Dict[str, Any]]:
        """
        Validate a table extraction result.

        Args:
            table: DocumentTableExtraction model instance

        Returns:
            List of validation findings (empty if all passed)
        """
        findings = []
        try:
            # Convert SQLAlchemy model to dict for validation
            table_dict = {
                'document_id': str(table.document_id) if isinstance(table.document_id, uuid.UUID) else table.document_id,
                'page_number': table.page_number,
                'table_index': table.table_index,
                'extraction_method': table.extraction_method,
                'row_count': table.row_count,
                'column_count': table.column_count,
                'table_data': table.table_data,
                'extraction_confidence': table.extraction_confidence,
                'structure_confidence': table.structure_confidence,
                'source_artifact_reference': table.source_artifact_reference,
                'extraction_metadata': table.extraction_metadata,
                'cell_metadata': table.cell_metadata
            }

            # Validate against schema
            TableExtractionSchema.model_validate(table_dict)
            logger.debug(f"Table extraction validation passed for document {table.document_id}, page {table.page_number}, table {table.table_index}")

        except ValidationError as e:
            for error in e.errors():
                findings.append({
                    'validator': 'schema',
                    'check_name': f'table_extraction_{error["loc"][0] if error["loc"] else "unknown"}',
                    'status': 'failed',
                    'severity': 'error',
                    'message': f"Schema validation failed: {error['msg']}",
                    'page_number': table.page_number,
                    'table_reference': table.id,
                    'details': {
                        'field': str(error['loc']) if error['loc'] else None,
                        'input': error.get('input'),
                        'type': error['type']
                    }
                })
                logger.warning(f"Table extraction schema validation failed: {error['msg']}")
        except Exception as e:
            findings.append({
                'validator': 'schema',
                'check_name': 'table_extraction_validation_error',
                'status': 'error',
                'severity': 'critical',
                'message': f"Validation process failed: {str(e)}",
                'page_number': table.page_number,
                'table_reference': table.id,
                'details': {'exception': str(e)}
            })
            logger.error(f"Table extraction validation error: {str(e)}")

        return findings

    def validate_chart_association(self, association: DocumentChartAssociation) -> List[Dict[str, Any]]:
        """
        Validate a chart association result.

        Args:
            association: DocumentChartAssociation model instance

        Returns:
            List of validation findings (empty if all passed)
        """
        findings = []
        try:
            # Convert SQLAlchemy model to dict for validation
            association_dict = {
                'document_id': str(association.document_id) if isinstance(association.document_id, uuid.UUID) else association.document_id,
                'page_number': association.page_number,
                'chart_index': association.chart_index,
                'associated_table_id': str(association.associated_table_id) if isinstance(association.associated_table_id, uuid.UUID) else association.associated_table_id,
                'association_method': association.association_method,
                'association_confidence': association.association_confidence,
                'chart_metadata': association.chart_metadata,
                'resolution_status': association.resolution_status
            }

            # Validate against schema
            ChartAssociationSchema.model_validate(association_dict)
            logger.debug(f"Chart association validation passed for document {association.document_id}, page {association.page_number}, chart {association.chart_index}")

        except ValidationError as e:
            for error in e.errors():
                findings.append({
                    'validator': 'schema',
                    'check_name': f'chart_association_{error["loc"][0] if error["loc"] else "unknown"}',
                    'status': 'failed',
                    'severity': 'error',
                    'message': f"Schema validation failed: {error['msg']}",
                    'page_number': association.page_number,
                    'table_reference': association.associated_table_id,
                    'details': {
                        'field': str(error['loc']) if error['loc'] else None,
                        'input': error.get('input'),
                        'type': error['type']
                    }
                })
                logger.warning(f"Chart association schema validation failed: {error['msg']}")
        except Exception as e:
            findings.append({
                'validator': 'schema',
                'check_name': 'chart_association_validation_error',
                'status': 'error',
                'severity': 'critical',
                'message': f"Validation process failed: {str(e)}",
                'page_number': association.page_number,
                'table_reference': association.associated_table_id,
                'details': {'exception': str(e)}
            })
            logger.error(f"Chart association validation error: {str(e)}")

        return findings