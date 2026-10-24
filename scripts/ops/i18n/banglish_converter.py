#!/usr/bin/env python3
"""
Banglish Converter
Convert Banglish text to proper Bangla and vice versa.
Priority: 🟡 Medium
"""

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Banglish to Bangla character mappings
BANGLISH_TO_BANGLA_MAPPINGS = {
    # Vowels
    'a': 'া',
    'e': 'ে',
    'i': 'ি',
    'o': 'ো',
    'u': 'ু',
    'A': 'া',
    'E': 'ে',
    'I': 'ি',
    'O': 'ো',
    'U': 'ু',

    # Consonants (common Banglish patterns)
    'k': 'ক',
    'kh': 'খ',
    'g': 'গ',
    'gh': 'ঘ',
    'ch': 'চ',
    'chh': 'ছ',
    'j': 'জ',
    'jh': 'ঝ',
    't': 'ট',
    'th': 'ঠ',
    'd': 'ড',
    'dh': 'ঢ',
    'n': 'ন',
    'ta': 'ত',
    'tha': 'থ',
    'da': 'দ',
    'dha': 'ধ',
    'na': 'ন',
    'p': 'প',
    'f': 'ফ',
    'ph': 'ফ',
    'b': 'ব',
    'bh': 'ভ',
    'm': 'ম',
    'z': 'য',
    'zh': 'য়',
    'r': 'র',
    'l': 'ল',
    'sh': 'শ',
    's': 'স',
    'h': 'হ',
    'yo': 'য়',
    'rri': 'ড়',
    'rrih': 'ঢ়',
    'yy': 'য়',
}

# Bangla vowels (for detection)
BANGLA_VOWELS = ['া', 'ি', 'ী', 'ু', 'ূ', 'ৃ', 'ে', 'ৈ', 'ৗ', 'ো', 'ৌ']


@dataclass
class ConversionResult:
    """Result of text conversion."""
    original: str
    converted: str
    conversion_type: str
    confidence: float
    timestamp: datetime


class BanglishConverter:
    """
    Converts between Banglish and Bangla scripts.
    """

    def __init__(self):
        self.conversion_history: list[ConversionResult] = []

    def _is_bangla(self, text: str) -> bool:
        """Check if text contains Bangla characters."""
        bangla_pattern = re.compile(r'[\u0980-\u09FF]')
        return bool(bangla_pattern.search(text))

    def _is_banglish(self, text: str) -> bool:
        """Check if text is in Banglish (Latin script with Bangla intent)."""
        # Banglish uses Latin characters but follows Bangla phonetics
        if self._is_bangla(text):
            return False

        # Check for common Banglish patterns
        banglish_patterns = [
            r'[aeiou]h?[aeiou]?',
            r'(kh|gh|ch|jh|th|dh|sh|ny)',
            r'[aeiou][aeiou]',
        ]

        text_lower = text.lower()
        for pattern in banglish_patterns:
            if re.search(pattern, text_lower):
                return True
        return False

    def banglish_to_bangla(self, text: str) -> ConversionResult:
        """Convert Banglish text to proper Bangla."""
        if not self._is_banglish(text):
            return ConversionResult(
                original=text,
                converted=text,
                conversion_type='none',
                confidence=0.0,
                timestamp=datetime.now()
            )

        result = text
        confidence = 0.0

        # Apply character mappings
        for pattern, replacement in BANGLISH_TO_BANGLA_MAPPINGS.items():
            result = re.sub(re.escape(pattern), replacement, result, flags=re.IGNORECASE)

        # Basic vowel placement (simplified)
        # In Bangla, vowels come after consonants
        result = re.sub(r'([ক-হ])([aeiou])', r'\1\2া', result)

        # Calculate confidence based on matches
        matched_chars = sum(1 for c in text.lower() if c in 'aeiou' or c in BANGLISH_TO_BANGLA_MAPPINGS)
        confidence = min(matched_chars / max(len(text), 1), 1.0)

        output = ConversionResult(
            original=text,
            converted=result,
            conversion_type='banglish_to_bangla',
            confidence=confidence,
            timestamp=datetime.now()
        )

        self.conversion_history.append(output)
        return output

    def bangla_to_banglish(self, text: str) -> ConversionResult:
        """Convert Bangla text to Banglish romanization."""
        if not self._is_bangla(text):
            return ConversionResult(
                original=text,
                converted=text,
                conversion_type='none',
                confidence=0.0,
                timestamp=datetime.now()
            )

        # Reverse mapping for Bangla to Banglish
        reverse_mappings = {v: k for k, v in BANGLISH_TO_BANGLA_MAPPINGS.items()}

        result = text
        for bangla_char, banglish in reverse_mappings.items():
            result = result.replace(bangla_char, banglish)

        output = ConversionResult(
            original=text,
            converted=result,
            conversion_type='bangla_to_banglish',
            confidence=0.8,
            timestamp=datetime.now()
        )

        self.conversion_history.append(output)
        return output

    def convert_file(self, file_path: str, output_path: str | None = None) -> str:
        """Convert file content between Banglish and Bangla."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        content = path.read_text(encoding='utf-8')

        if self._is_bangla(content):
            converted = self.bangla_to_banglish(content).converted
        else:
            converted = self.banglish_to_bangla(content).converted

        out_path = Path(output_path or f"{file_path}.converted")
        out_path.write_text(converted, encoding='utf-8')

        logger.info(f"Converted file saved to: {out_path}")
        return str(out_path)

    def batch_convert(self, texts: list[str]) -> list[ConversionResult]:
        """Convert multiple texts."""
        return [self.banglish_to_bangla(text) if self._is_banglish(text) else self.bangla_to_banglish(text) for text in texts]

    def get_conversion_stats(self) -> dict[str, Any]:
        """Get conversion statistics."""
        if not self.conversion_history:
            return {"total_conversions": 0}

        total = len(self.conversion_history)
        avg_confidence = sum(r.confidence for r in self.conversion_history) / total

        type_counts = {}
        for r in self.conversion_history:
            type_counts[r.conversion_type] = type_counts.get(r.conversion_type, 0) + 1

        return {
            'total_conversions': total,
            'average_confidence': round(avg_confidence, 2),
            'conversion_types': type_counts
        }


def main():
    """Main entry point for Banglish conversion."""
    import argparse

    parser = argparse.ArgumentParser(description="Convert between Banglish and Bangla")
    parser.add_argument('--banglish-to-bangla', action='store_true', help='Convert Banglish to Bangla')
    parser.add_argument('--bangla-to-banglish', action='store_true', help='Convert Bangla to Banglish')
    parser.add_argument('--text', help='Text to convert')
    parser.add_argument('--file', help='File to convert')
    parser.add_argument('--output', help='Output file path')

    args = parser.parse_args()

    converter = BanglishConverter()

    if args.text:
        if args.bangla_to_banglish:
            result = converter.bangla_to_banglish(args.text)
        else:
            result = converter.banglish_to_bangla(args.text)

        print(f"\nOriginal: {result.original}")
        print(f"Converted: {result.converted}")
        print(f"Type: {result.conversion_type}")

    elif args.file:
        output = args.output or f"{args.file}.converted"
        result_path = converter.convert_file(args.file, output)
        print(f"File converted: {result_path}")


if __name__ == "__main__":
    main()
