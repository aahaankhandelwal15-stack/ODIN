# Phase 6: Validation, Quality Gates & Extraction Quality Assessment - Implementation Plan

## Overview
Phase 6 implements a comprehensive validation framework that assesses the quality of extractions from Phases 4 and 5, applies validation gates based on configurable thresholds, and produces quality assessments with explainable scoring. This phase does not modify existing functionality but adds validation as a post-processing step.

## Validation Architecture

### Core Components
1. **SchemaValidator** - Validates extracted data against expected schemas/types using Pydantic v2
2. **TableValidator** - Performs deterministic structural validation on tables (row/column consistency, data types)
3. **NumericConsistencyValidator** - Checks for deterministic numeric relationships (explicit totals, sums)
4. **QualityAssessor** - Computes explainable quality scores from validation outcomes and extraction signals
5. **ValidationPersistenceService** - Stores validation results and findings using existing database patterns
6. **ValidationAPIEndpoints** - RESTful endpoints for triggering validation and retrieving results

## Implementation Approach

### 1. Schema/Type Validation (Pydantic v2)
- Validate text extractions against expected content patterns
- Validate table extractions for consistent column types (where determinable)
- Use existing Pydantic v2 infrastructure from Phases 4/5 schemas
- Conservative approach: only validate where types can be reasonably inferred

### 2. Structural Table Validation
- Row count consistency: Verify no rows have missing/extra columns
- Header consistency: Detect if first row looks like a header
- Data type consistency per column (basic: numeric vs text detection)
- Empty table detection
- All checks are deterministic and deterministic

### 3. Numeric Consistency Checks
Only where explicitly justified:
- Explicit total rows: Detect rows labeled "Total", "Sum", etc. and validate column sums
- Explicit subtotals: Similar to totals but for sections
- Cross-table consistency: When same data appears in multiple tables
- Never infer or guess - only validate explicit relationships

### 4. Extraction Quality Assessment
Deterministic scoring (0-100) based on:
- OCR confidence (from Phase 4): 0-30 points
- Validation outcomes: 0-40 points (passed validations)
- Table structure quality: 0-20 points (row/column consistency, header detection)
- Extraction completeness: 0-10 points (ratio of expected vs actual content)
- Explainable breakdown: Each component shows contribution to final score

### 5. Configuration & Thresholds
- `VALIDATION_AUTO_APPROVE_THRESHOLD`: Default 85 (configurable)
- Per-validation-type enable/disable flags
- Per-document-type validation profiles (based on Phase 2/3 classifications)

### 6. Persistence & Traceability
- **ValidationRun**: One record per validation execution
- **ValidationFinding**: Individual findings (pass/fail) with severity and description
- Link to source extractions via foreign keys
- Store timestamp, configuration used, and overall score
- Full traceability: ValidationRun → ValidationFinding → Source Extraction

### 7. Idempotency & Change Detection
- Input hash: Combine document content + extraction results + config version
- Skip validation if inputs unchanged and validation exists
- Force re-validation option
- Store input hash with ValidationRun for change detection

### 8. Partial Failure Handling
- Distinguish validation check failures from validator failures
- Continue validation if individual checks fail
- Record both successful and failed checks
- Never let validation failure block document processing flow

### 9. Unresolved Charts Handling
- Charts marked as "unresolved" in Phase 5 are NOT treated as validated structured data
- Validation skips chart-only associations (no table to validate)
- Chart validation limited to: association confidence, metadata consistency
- Clear distinction: resolved charts → validate associated table; unresolved charts → validate association quality only

### 10. API Endpoints
- `POST /{document_id}/validate`: Trigger validation for document
- `GET /{document_id}/validation`: Get latest validation results
- `GET /{document_id}/validation/history`: Get validation history
- `GET /{validation_run_id}/findings`: Get detailed findings for a run

## Component Details

### SchemaValidator
- Validates text extractions: checks for expected patterns (dates, IDs, codes)
- Validates table extractions: column type consistency (when sample size allows)
- Uses Pydantic v2 models dynamically generated from observed data patterns
- Conservative: marks as "unknown" rather than incorrect when uncertain

### TableValidator
- Structural checks:
  - All rows have same column count
  - No completely empty rows/columns (unless expected)
  - Header detection: first row contains non-numeric, unique-ish values
  - Monotonic columns: detection of ID/sequence columns
- Data consistency:
  - Numeric columns: all values parse as numbers (when detected as numeric)
  - Date columns: consistent format (when detected as date)
  - Text columns: reasonable length distributions

### NumericConsistencyValidator
- Only runs when explicit total/subtotal rows detected:
  - Row contains keywords: "Total", "Sum", "Grand Total", "Subtotal"
  - Numeric columns in total row ≈ sum of same columns in data rows (within tolerance)
  - Tolerance: 0.01 for floating point, exact for integers
- Cross-table validation:
  - Same checksum of normalized data indicates duplicate table
  - Explicitly linked tables (from Phase 5 metadata) show consistent data

### QualityAssessor
- Weighted scoring algorithm:
  - OCR Confidence (extraction.confidence): weight 0.3
  - Validation Pass Rate: weight 0.4
  - Structure Quality: weight 0.2 (based on TableValidator structural checks)
  - Completeness: weight 0.1 (ratio of cells with content vs expected)
- Each component 0-100, final score 0-100
- Explainable breakdown returned with score

### ValidationPersistenceService
- Uses existing SQLAlchemy patterns from app.core.database
- ValidationRun model: document_id, status, score, config_snapshot, input_hash
- ValidationFinding model: validation_run_id, check_type, severity, description, location
- Automatic cleanup: optional retention policy
- Indexes for performance: document_id, created_at, status

## Implementation Order

1. Create validation database models (ValidationRun, ValidationFinding)
2. Implement SchemaValidator component
3. Implement TableValidator component  
4. Implement NumericConsistencyValidator component
5. Implement QualityAssessor component
6. Implement ValidationPersistenceService
7. Create validation orchestration service
8. Implement API endpoints
9. Add comprehensive tests
10. Integrate with existing pipeline (optional auto-validation after Phase 5)

## Dependencies & Constraints
- **CPU-only**: No new GPU dependencies, no external AI APIs
- **Backward compatibility**: All existing functionality preserved
- **Traceability**: All validation results traceable to source extractions
- **Deterministic**: Same inputs always produce same validation results
- **Explainable**: Quality scores broken down into contributing factors
- **Configurable**: Validation behavior adjustable via environment/settings

## Testing Strategy
- Unit tests for each validation component
- Integration tests for validation service
- End-to-end tests for API endpoints
- Regression tests to ensure Phases 1-5 unaffected
- Edge case testing: empty documents, malformed extractions, boundary values

## Files to Create/Modify

**New Files:**
- `app/models/validation.py` - ValidationRun and ValidationFinding models
- `app/services/validation/` directory:
  - `__init__.py`
  - `schema_validator.py`
  - `table_validator.py`
  - `numeric_consistency_validator.py`
  - `quality_assessor.py`
  - `validation_persistence_service.py`
  - `validation_service.py` (orchestrator)
- `app/schemas/validation.py` - Pydantic schemas for validation
- `app/api/endpoints/validation.py` - Validation API endpoints
- `tests/test_validation.py` - Comprehensive test suite

**Modified Files:**
- `app/api/main.py` - Add validation router
- `app/core/config.py` - Add validation configuration options
- Potentially: Update structured extraction service to call validation (optional)

## Integration Points
- Runs after Phase 5 structured extraction (optional automatic trigger)
- Can be triggered manually via API
- Uses same database session patterns as existing services
- Reuses storage backend for artifact references
- Leverages existing analysis results for classification-aware validation

## Success Criteria
- All validation components implemented and tested
- Quality scores produced with explainable breakdown
- Validation results persisted and retrievable
- API endpoints functional and tested
- No regressions in existing Phase 1-5 functionality (49/49 tests still pass)
- CPU-only implementation maintained
- Deterministic behavior: same inputs → same outputs
- Proper handling of unresolved charts (not treated as validated data)