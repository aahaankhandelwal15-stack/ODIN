import re
import logging

logger = logging.getLogger(__name__)


class TextNormalizer:
    """
    Conservative text normalizer for extracted text.

    Operations:
    - Normalize line endings to \n
    - Remove null and control characters (except \n and \t)
    - Replace multiple consecutive whitespace characters with a single space
    - Strip leading and trailing whitespace
    - Preserve meaningful paragraph separation (double newlines)
    """

    @staticmethod
    def normalize(text: str) -> str:
        """
        Normalize extracted text conservatively.

        Args:
            text: Raw extracted text

        Returns:
            Normalized text
        """
        if not text:
            return ""

        # Normalize line endings
        text = text.replace('\r\n', '\n').replace('\r', '\n')

        # Remove null and control characters except \n and \t
        # We'll keep \n (newline) and \t (tab) as they are meaningful for structure
        cleaned_chars = []
        for char in text:
            if char == '\n' or char == '\t':
                cleaned_chars.append(char)
            elif ord(char) < 32:  # Control characters (0-31) except \n (10) and \t (9)
                continue
            else:
                cleaned_chars.append(char)
        text = ''.join(cleaned_chars)

        # Replace multiple spaces/tabs with a single space, but be careful with newlines
        # We want to avoid collapsing newlines with spaces, so we process line by line
        lines = text.split('\n')
        normalized_lines = []
        for line in lines:
            # Replace multiple spaces/tabs with a single space in each line
            line = re.sub(r'[ \t]+', ' ', line)
            # Strip leading and trailing whitespace from each line
            line = line.strip()
            normalized_lines.append(line)

        # Rejoin lines with single newline
        text = '\n'.join(normalized_lines)

        return text