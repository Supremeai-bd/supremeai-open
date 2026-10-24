#!/usr/bin/env python3
"""
Bangla Translator
Automatic Bangla translation for UI and content.
Priority: 🟡 Medium
"""

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Bangla character ranges
BANGLA_REGEX = re.compile(r'[\u0980-\u09FF]')


def load_translations(file_path: str = "data/bangla_translations.json") -> dict[str, str]:
    """JSON ফাইল থেকে ট্রান্সলেশন ডায়নামিক্যালি লোড করুন। (Bangla: ডায়নামিক ট্রান্সলেশন লোডার)"""
    path = Path(file_path)
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            logger.warning(f"Failed to load translations from {file_path}: {exc}")
    return DEFAULT_TRANSLATIONS


# Common English to Bangla translations
DEFAULT_TRANSLATIONS = {
    # UI Elements
    'hello': 'হ্যালো',
    'welcome': 'স্বাগতম',
    'login': 'লগইন',
    'logout': 'লগআউট',
    'register': 'নিবন্ধন',
    'submit': 'জমা দিন',
    'cancel': 'বাতিল',
    'save': 'সংরক্ষণ',
    'delete': 'মুছে ফেলুন',
    'edit': 'সম্পাদনা',
    'view': 'দেখুন',
    'search': 'অনুসন্ধান',
    'settings': 'সেটিংস',
    'profile': 'প্রোফাইল',
    'home': 'হোম',
    'dashboard': 'ড্যাশবোর্ড',
    'admin': 'অ্যাডমিন',

    # Messages
    'success': 'সফল',
    'error': 'ত্রুটি',
    'warning': 'সতর্কতা',
    'info': 'তথ্য',
    'loading': 'লোড হচ্ছে',
    'please wait': 'দয়া করে অপেক্ষা করুন',
    'no results found': 'কোন ফলাফল পাওয়া যায়নি',
    'required field': 'আবশ্যকীয় ক্ষেত্র',

    # Numbers
    'one': 'এক',
    'two': 'দুই',
    'three': 'তিন',
    'four': 'চার',
    'five': 'পাঁচ',
}


@dataclass
class TranslationResult:
    """Result of a translation."""
    original_text: str
    translated_text: str
    confidence: float
    source: str
    timestamp: datetime


class BanglaTranslator:
    """
    Translates English text to Bangla.
    """

    def __init__(self, dictionary_path: str | None = None):
        self.dictionary = DEFAULT_TRANSLATIONS.copy()
        self.dictionary_path = dictionary_path
        self.translation_history: list[TranslationResult] = []

        if dictionary_path:
            self._load_dictionary(dictionary_path)

    def _load_dictionary(self, path: str) -> None:
        """Load custom dictionary from file."""
        dict_file = Path(path)
        if dict_file.exists():
            with open(dict_file, 'r', encoding='utf-8') as f:
                custom_dict = json.load(f)
                self.dictionary.update(custom_dict)
            logger.info(f"Loaded {len(custom_dict)} custom translations")

    def _is_bangla(self, text: str) -> bool:
        """Check if text is already in Bangla."""
        return bool(BANGLA_REGEX.search(text))

    def _translate_word(self, word: str) -> tuple[str, float]:
        """Translate a single word."""
        word_lower = word.lower()

        if word_lower in self.dictionary:
            return self.dictionary[word_lower], 1.0

        # Fallback: return original with low confidence
        return word, 0.0

    def translate_text(self, text: str) -> TranslationResult:
        """Translate English text to Bangla."""
        if self._is_bangla(text):
            return TranslationResult(
                original_text=text,
                translated_text=text,
                confidence=1.0,
                source='original',
                timestamp=datetime.now()
            )

        # Tokenize and translate
        words = text.split()
        translated_words = []
        total_confidence = 0.0

        for word in words:
            translated, confidence = self._translate_word(word)
            translated_words.append(translated)
            total_confidence += confidence

        avg_confidence = total_confidence / len(words) if words else 0.0

        result = TranslationResult(
            original_text=text,
            translated_text=' '.join(translated_words),
            confidence=avg_confidence,
            source='dictionary' if avg_confidence > 0.5 else 'mixed',
            timestamp=datetime.now()
        )

        self.translation_history.append(result)
        return result

    def translate_file(self, file_path: str, output_path: str | None = None) -> str:
        """Translate a file's contents to Bangla."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        content = path.read_text(encoding='utf-8')

        # For JSON files, translate values
        if path.suffix == '.json':
            data = json.loads(content)
            translated_data = self._translate_dict(data)
            output = json.dumps(translated_data, ensure_ascii=False, indent=2)
        else:
            lines = content.split('\n')
            translated_lines = [self.translate_text(line).translated_text for line in lines]
            output = '\n'.join(translated_lines)

        out_path = Path(output_path or f"{file_path}.bn")
        out_path.write_text(output, encoding='utf-8')

        logger.info(f"Translated file saved to: {out_path}")
        return str(out_path)

    def _translate_dict(self, data: dict, prefix: str = '') -> dict:
        """Recursively translate dictionary values."""
        result = {}

        for key, value in data.items():
            if isinstance(value, str):
                result[key] = self.translate_text(value).translated_text
            elif isinstance(value, dict):
                result[key] = self._translate_dict(value, f"{prefix}.{key}")
            elif isinstance(value, list):
                result[key] = [self._translate_dict(v, f"{prefix}.{key}") if isinstance(v, dict) else self.translate_text(v).translated_text if isinstance(v, str) else v for v in value]
            else:
                result[key] = value

        return result

    def batch_translate(self, texts: list[str]) -> list[TranslationResult]:
        """Translate multiple texts."""
        return [self.translate_text(text) for text in texts]

    def get_translation_stats(self) -> dict[str, Any]:
        """Get translation statistics."""
        if not self.translation_history:
            return {"total_translations": 0}

        total = len(self.translation_history)
        avg_confidence = sum(r.confidence for r in self.translation_history) / total
        high_confidence = sum(1 for r in self.translation_history if r.confidence >= 0.8)

        return {
            'total_translations': total,
            'average_confidence': round(avg_confidence, 2),
            'high_confidence_count': high_confidence,
            'language_detected': 'bangla'
        }


def main():
    """Main entry point for Bangla translation."""
    import argparse

    parser = argparse.ArgumentParser(description="Translate text to Bangla")
    parser.add_argument('--text', help='Text to translate')
    parser.add_argument('--file', help='File to translate')
    parser.add_argument('--dictionary', help='Custom dictionary JSON file')

    args = parser.parse_args()

    translator = BanglaTranslator(args.dictionary)

    if args.text:
        result = translator.translate_text(args.text)
        print(f"\nOriginal: {result.original_text}")
        print(f"Translated: {result.translated_text}")
        print(f"Confidence: {result.confidence:.2f}")

    elif args.file:
        output = translator.translate_file(args.file)
        print(f"File translated: {output}")

    else:
        # Interactive mode
        print("Enter English text (or 'quit' to exit):")
        while True:
            try:
                text = input("> ")
                if text.lower() == 'quit':
                    break
                result = translator.translate_text(text)
                print(f"Bangla: {result.translated_text}")
            except EOFError:
                break


if __name__ == "__main__":
    main()
