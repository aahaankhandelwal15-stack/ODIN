"""
Structural validation for table extraction results.
"""

import logging
from typing import List, Dict, Any
from app.models.structured_extraction import DocumentTableExtraction

logger = logging.getLogger(__name__)


class TableValidator:
    """
    Performs deterministic structural validation on table extraction results.
    """

    def __init__(self):
        """Initialize the table validator."""
        logger.debug("TableValidator initialized")

    def validate_table_structure(self, table: DocumentTableExtraction) -> List[Dict[str, Any]]:
        """
        Validate structural aspects of a table extraction.

        Args:
            table: DocumentTableExtraction model instance

        Returns:
            List of validation findings (empty if all passed)
        """
        findings = []

        # Check 1: Table has rows and columns
        if table.row_count == 0:
            findings.append({
                'validator': 'table',
                'check_name': 'empty_table',
                'status': 'failed',
                'severity': 'warning',
                'message': 'Table is empty (no rows)',
                'page_number': table.page_number,
                'table_reference': table.id
            })
        elif table.column_count == 0:
            findings.append({
                'validator': 'table',
                'check_name': 'empty_table_columns',
                'status': 'failed',
                'severity': 'warning',
                'message': 'Table is empty (no columns)',
                'page_number': table.page_number,
                'table_reference': table.id
            })

        # Check 2: Table data consistency (if not already validated by schema)
        if table.table_data and len(table.table_data) > 0:
            expected_columns = table.column_count
            for row_idx, row in enumerate(table.table_data):
                if len(row) != expected_columns:
                    findings.append({
                        'validator': 'table',
                        'check_name': 'inconsistent_row_width',
                        'status': 'failed',
                        'severity': 'error',
                        'message': f'Row {row_idx} has inconsistent column count: expected {expected_columns}, got {len(row)}',
                        'page_number': table.page_number,
                        'table_reference': table.id,
                        'details': {
                            'row_index': row_idx,
                            'expected_columns': expected_columns,
                            'actual_columns': len(row)
                        }
                    })

        # Check 3: Detect completely empty rows
        if table.table_data and len(table.table_data) > 0:
            empty_rows = []
            for row_idx, row in enumerate(table.table_data):
                if all(cell is None or cell == '' for cell in row):
                    empty_rows.append(row_idx)

            if empty_rows:
                findings.append({
                    'validator': 'table',
                    'check_name': 'empty_rows_detected',
                    'status': 'passed',  # This is informational, not necessarily a failure
                    'severity': 'info',
                    'message': f'Table contains {len(empty_rows)} completely empty row(s)',
                    'page_number': table.page_number,
                    'table_reference': table.id,
                    'details': {
                        'empty_row_indices': empty_rows,
                        'total_rows': table.row_count
                    }
                })

        # Check 4: Detect completely empty columns
        if table.table_data and len(table.table_data) > 0 and len(table.table_data[0]) > 0:
            empty_columns = []
            num_columns = len(table.table_data[0])
            for col_idx in range(num_columns):
                column_values = [row[col_idx] if col_idx < len(row) else None for row in table.table_data]
                if all(cell is None or cell == '' for cell in column_values):
                    empty_columns.append(col_idx)

            if empty_columns:
                findings.append({
                    'validator': 'table',
                    'check_name': 'empty_columns_detected',
                    'status': 'passed',  # Informational
                    'severity': 'info',
                    'message': f'Table contains {len(empty_columns)} completely empty column(s)',
                    'page_number': table.page_number,
                    'table_reference': table.id,
                    'details': {
                        'empty_column_indices': empty_columns,
                        'total_columns': table.column_count
                    }
                })

        # Check 5: Header-like first row detection (heuristic)
        if table.table_data and len(table.table_data) > 0:
            first_row = table.table_data[0]
            # Simple heuristic: if first row has mostly non-numeric values and others have numeric, it might be a header
            non_empty_first_row = [cell for cell in first_row if cell is not None and cell != '']
            if non_empty_first_row:
                # Count numeric-like cells in first row vs other rows
                first_row_numeric = sum(1 for cell in non_empty_first_row if self._is_numeric_like(cell))

                if table.row_count > 1:
                    other_rows_numeric = []
                    for row_idx in range(1, min(table.row_count, 6)):  # Check up to 5 data rows
                        if row_idx < len(table.table_data):
                            row = table.table_data[row_idx]
                            non_empty_row = [cell for cell in row if cell is not None and cell != '']
                            if non_empty_row:
                                numeric_count = sum(1 for cell in non_empty_row if self._is_numeric_like(cell))
                                other_rows_numeric.append(numeric_count / len(non_empty_row))

                    if other_rows_numeric:
                        avg_other_numeric = sum(other_rows_numeric) / len(other_rows_numeric)
                        first_row_numeric_ratio = first_row_numeric / len(non_empty_first_row) if non_empty_first_row else 0

                        # If first row has significantly fewer numeric values than data rows, likely a header
                        if first_row_numeric_ratio < 0.3 and avg_other_numeric > 0.7:
                            findings.append({
                                'validator': 'table',
                                'check_name': 'header_row_detected',
                                'status': 'passed',
                                'severity': 'info',
                                'message': 'First row appears to be a header row',
                                'page_number': table.page_number,
                                'table_reference': table.id,
                                'details': {
                                    'first_row_numeric_ratio': first_row_numeric_ratio,
                                    'avg_data_row_numeric_ratio': avg_other_numeric
                                }
                            })

        logger.debug(f"Table structure validation completed for document {table.document_id}, page {table.page_number}, table {table.table_index}. Found {len(findings)} issues.")
        return findings

    def _is_numeric_like(self, value: str) -> bool:
        """
        Check if a string value looks like a number.

        Args:
            value: String value to check

        Returns:
            True if the value looks numeric, False otherwise
        """
        if not value or not isinstance(value, str):
            return False

        # Remove common formatting
        cleaned = value.strip().replace(',', '').replace('$', '').replace('%', '')

        # Handle parentheses for negative numbers
        if cleaned.startswith('(') and cleaned.endswith(')'):
            cleaned = '-' + cleaned[1:-1]

        try:
            float(cleaned)
            return True
        except ValueError:
            return False