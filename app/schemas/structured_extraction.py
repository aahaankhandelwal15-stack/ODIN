"""
Pydantic schemas for structured table and chart extraction results.
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime


class TableExtractionBase(BaseModel):
    table_id: str = Field(..., max_length=36)
    page_number: int = Field(..., gt=0)
    table_index: int = Field(..., ge=0)
    extraction_method: str = Field(..., max_length=50)  # opencv_plus_ocr, etc.
    row_count: int = Field(..., gt=0)
    column_count: int = Field(..., gt=0)
    table_data: List[List[str]] = Field(...)  # 2D array of cell texts
    extraction_confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    structure_confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    source_artifact_reference: Optional[str] = None
    extraction_metadata: Optional[Dict[str, Any]] = None


class TableExtractionCreate(TableExtractionBase):
    pass


class TableExtractionResponse(TableExtractionBase):
    created_at: datetime

    class Config:
        from_attributes = True


class ChartAssociationBase(BaseModel):
    association_id: str = Field(..., max_length=36)
    page_number: int = Field(..., gt=0)
    chart_index: int = Field(..., ge=0)
    associated_table_id: Optional[str] = Field(None, max_length=36)
    association_method: str = Field(..., max_length=50)  # same_page, adjacent_page, etc.
    association_confidence: float = Field(..., ge=0.0, le=1.0)
    chart_metadata: Optional[Dict[str, Any]] = None
    resolution_status: str = Field(..., max_length=30)  # resolved, unresolved, partial


class ChartAssociationCreate(ChartAssociationBase):
    pass


class ChartAssociationResponse(ChartAssociationBase):
    created_at: datetime

    class Config:
        from_attributes = True


class StructuredExtractionResult(BaseModel):
    document_id: str
    status: str
    page_count: int
    tables_extracted: int
    charts_processed: int
    charts_resolved: int
    charts_unresolved: int
    failed_pages: List[Dict[str, Any]] = []


class StructuredExtractionSummary(BaseModel):
    document_id: str
    status: str
    page_count: int
    tables: List[TableExtractionResponse]
    charts: List[ChartAssociationResponse]
    table_count: int
    chart_count: int


class TableCellDetail(BaseModel):
    text: str
    row_index: int
    column_index: int
    confidence: float = Field(ge=0.0, le=1.0)
    bounding_box: Optional[Dict[str, int]] = None  # x, y, width, height
    extraction_method: Optional[str] = None


class TableWithDetailsResponse(TableExtractionResponse):
    cells: List[List[TableCellDetail]]