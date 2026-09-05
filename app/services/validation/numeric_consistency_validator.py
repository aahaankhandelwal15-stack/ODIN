"""
Numeric consistency validation for table extraction results.
"""

import logging
import re
from typing import List, Dict, Any, Optional, Tuple
from app.models.structured_extraction import DocumentTableExtraction

logger = logging.getLogger(__name__)


class NumericConsistencyValidator:
    """
    Performs deterministic numeric consistency checks on table extraction results.
    Only runs when deterministic structural signals support the check.
    """

    def __init__(self, tolerance: float = 0.01):
        """
        Initialize the numeric consistency validator.

        Args:
            tolerance: Tolerance for floating point comparisons (default 0.01 for 1 cent)
        """
        self.tolerance = tolerance
        logger.debug(f"NumericConsistencyValidator initialized with tolerance {tolerance}")

    def validate_numeric_consistency(self, table: DocumentTableExtraction) -> List[Dict[str, Any]]:
        """
        Validate numeric consistency in a table extraction.

        This validator only performs checks when deterministic signals support them,
        such as explicit total rows.

        Args:
            table: DocumentTableExtraction model instance

        Returns:
            List of validation findings (empty if all passed or no applicable checks)
        """
        findings = []

        # Only proceed if we have table data
        if not table.table_data or len(table.table_data) == 0:
            findings.append({
                'validator': 'numeric_consistency',
                'check_name': 'no_data_for_numeric_check',
                'status': 'skipped',
                'severity': 'info',
                'message': 'Skipping numeric consistency check: table contains no data',
                'page_number': table.page_number,
                'table_reference': table.id
            })
            return findings

        # Check for explicit total row
        total_row_info = self._detect_explicit_total_row(table)
        if total_row_info:
            total_row_index, total_row_label, total_columns = total_row_info
            findings.extend(self._validate_total_row(table, total_row_index, total_row_label, total_columns))
        else:
            findings.append({
                'validator': 'numeric_consistency',
                'check_name': 'no_explicit_total_row',
                'status': 'skipped',
                'severity': 'info',
                'message': 'Skipping numeric consistency check: no explicit total row detected',
                'page_number': table.page_number,
                'table_reference': table.id
            })

        logger.debug(f"Numeric consistency validation completed for document {table.document_id}, page {table.page_number}, table {table.table_index}. Found {len(findings)} applicable checks.")
        return findings

    def _detect_explicit_total_row(self, table: DocumentTableExtraction) -> Optional[Tuple[int, str, List[int]]]:
        """
        Detect if there's an explicit total row in the table.

        Returns:
            Tuple of (row_index, label, numeric_columns) if total row found, None otherwise
        """
        if not table.table_data or len(table.table_data) == 0:
            return None

        # Keywords that indicate a total row (case-insensitive)
        total_keywords = [
            'total', 'sum', 'grand total', 'subtotal',
            'aggregate', 'summary', 'final'
        ]

        for row_idx, row in enumerate(table.table_data):
            # Check each cell in the row for total keywords
            for col_idx, cell in enumerate(row):
                if isinstance(cell, str):
                    cell_lower = cell.lower().strip()
                    # Check if cell contains a total keyword
                    for keyword in total_keywords:
                        if keyword in cell_lower:
                            # Found potential total row, now identify which columns contain numeric values
                            numeric_columns = []
                            for check_col_idx, check_cell in enumerate(row):
                                if check_col_idx != col_idx and self._is_extractable_number(check_cell):
                                    numeric_columns.append(check_col_idx)

                            if numeric_columns:  # Only return if we found numeric columns to validate
                                return (row_idx, cell, numeric_columns)
                            break  # Found keyword in this cell, no need to check other keywords

        return None

    def _is_extractable_number(self, value: Any) -> bool:
        """
        Check if a value can be safely extracted as a number.

        Args:
            value: Value to check

        Returns:
            True if the value can be converted to a number, False otherwise
        """
        if not isinstance(value, str):
            return False

        if not value or value.strip() == '':
            return False

        # Remove common formatting
        cleaned = value.strip()

        # Handle parentheses for negative numbers: (123) -> -123
        if cleaned.startswith('(') and cleaned.endswith(')'):
            cleaned = '-' + cleaned[1:-1]

        # Remove currency symbols, commas, percentages
        cleaned = re.sub(r'[$,%\s]', '', cleaned)

        try:
            float(cleaned)
            return True
        except ValueError:
            return False

    def _extract_number(self, value: Any) -> Optional[float]:
        """
        Safely extract a number from a value.

        Args:
            value: Value to convert

        Returns:
            Extracted float or None if conversion fails
        """
        if not self._is_extractable_number(value):
            return None

        cleaned = value.strip()

        # Handle parentheses for negative numbers: (123) -> -123
        if cleaned.startswith('(') and cleaned.endswith(')'):
            cleaned = '-' + cleaned[1:-1]

        # Remove currency symbols, commas, percentages
        cleaned = re.sub(r'[$,%\s]', '', cleaned)

        try:
            return float(cleaned)
        except ValueError:
            return None

    def _validate_total_row(self, table: DocumentTableExtraction, total_row_index: int,
                           total_row_label: str, total_columns: List[int]) -> List[Dict[str, Any]]:
        """
        Validate that the total row matches the sum of preceding rows.

        Args:
            table: DocumentTableExtraction model instance
            total_row_index: Index of the total row
            total_row_label: Label/content of the total row cell
            total_columns: List of column indices that should be summed

        Returns:
            List of validation findings
        """
        findings = []

        # Validate each numeric column
        for col_idx in total_columns:
            # Extract the purported total from the total row
            total_value_str = table.table_data[total_row_index][col_idx] if col_idx < len(table.table_data[total_row_index]) else None
            purported_total = self._extract_number(total_value_str)

            if purported_total is None:
                findings.append({
                    'validator': 'numeric_consistency',
                    'check_name': 'total_row_non_numeric',
                    'status': 'failed',
                    'severity': 'error',
                    'message': f'Total row cell at column {col_idx} contains non-numeric value: "{total_value_str}"',
                    'page_number': table.page_number,
                    'table_reference': table.id,
                    'details': {
                        'total_row_index': total_row_index,
                        'column_index': col_idx,
                        'total_row_label': total_row_label,
                        'purported_total': total_value_str
                    }
                })
                continue

            # Calculate sum of the same column in data rows (excluding total row)
            calculated_sum = 0.0
            valid_data_rows = 0
            invalid_cells = []

            for row_idx in range(min(total_row_index, len(table.table_data))):  # Rows before total row
                if row_idx >= len(table.table_data):
                    break

                row = table.table_data[row_idx]
                if col_idx >= len(row):
                    invalid_cells.append({
                        'row_index': row_idx,
                        'reason': 'column_index_out_of_bounds'
                    })
                    continue

                cell_value = row[col_idx]
                extracted_value = self._extract_number(cell_value)

                if extracted_value is None:
                    invalid_cells.append({
                        'row_index': row_idx,
                        'value': cell_value,
                        'reason': 'non_numeric_or_empty'
                    })
                else:
                    calculated_sum += extracted_value
                    valid_data_rows += 1

            # Check if we have enough valid data to perform the check
            if valid_data_rows == 0:
                findings.append({
                    'validator': 'numeric_consistency',
                    'check_name': 'no_valid_data_for_sum',
                    'status': 'skipped',
                    'severity': 'info',
                    'message': f'Skipping column {col_idx} total validation: no valid numeric data found in data rows',
                    'page_number': table.page_number,
                    'table_reference': table.id,
                    'details': {
                        'total_row_index': total_row_index,
                        'column_index': col_idx,
                        'total_row_label': total_row_label,
                        'purported_total': purported_total
                    }
                })
                continue

            # Compare purported total with calculated sum
            difference = abs(purported_total - calculated_sum)
            within_tolerance = difference <= self.tolerance

            if not within_tolerance:
                findings.append({
                    'validator': 'numeric_consistency',
                    'check_name': 'total_mismatch',
                    'status': 'failed',
                    'severity': 'error',
                    'message': f'Total mismatch in column {col_idx}: calculated {calculated_sum:.2f} ≠ extracted {purported_total:.2f} (difference: {difference:.2f})',
                    'page_number': table.page_number,
                    'table_reference': table.id,
                    'details': {
                        'total_row_index': total_row_index,
                        'column_index': col_idx,
                        'total_row_label': total_row_label,
                        'calculated_sum': calculated_sum,
                        'purported_total': purported_total,
                        'difference': difference,
                        'tolerance': self.tolerance,
                        'valid_data_rows': valid_data_rows,
                        'invalid_cells': invalid_cells
                    }
                })
            else:
                findings.append({
                    'validator': 'numeric_consistency',
                    'check_name': 'total_match',
                    'status': 'passed',
                    'severity': 'info',
                    'message': f'Total matches in column {col_idx}: calculated {calculated_sum:.2f} = extracted {purported_total:.2f}',
                    'page_number': table.page_number,
                    'table_reference': table.id,
                    'details': {
                        'total_row_index': total_row_index,
                        'column_index': col_idx,
                        'total_row_label': total_row_label,
                        'calculated_sum': calculated_sum,
                        'purported_total': purported_total,
                        'difference': difference,
                        'tolerance': self.tolerance,
                        'valid_data_rows': valid_data_rows
                    }
                })

        return findings