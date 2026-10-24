"""Zero-token extractive summarization engine using sentence salience scoring."""

from __future__ import annotations

import collections
import re


class ExtractiveSummarizer:
    """Ranks and extracts the most informative sentences without calling an LLM or incurring token costs."""

    _STOPWORDS = frozenset(
        {
            "a",
            "about",
            "above",
            "after",
            "again",
            "against",
            "all",
            "am",
            "an",
            "and",
            "any",
            "are",
            "aren't",
            "as",
            "at",
            "be",
            "because",
            "been",
            "before",
            "being",
            "below",
            "between",
            "both",
            "but",
            "by",
            "can",
            "can't",
            "cannot",
            "could",
            "couldn't",
            "did",
            "didn't",
            "do",
            "does",
            "doesn't",
            "doing",
            "don't",
            "down",
            "during",
            "each",
            "few",
            "for",
            "from",
            "further",
            "had",
            "hadn't",
            "has",
            "hasn't",
            "have",
            "haven't",
            "having",
            "he",
            "he'd",
            "he'll",
            "he's",
            "her",
            "here",
            "here's",
            "hers",
            "herself",
            "him",
            "himself",
            "his",
            "how",
            "how's",
            "i",
            "i'd",
            "i'll",
            "i'm",
            "i've",
            "if",
            "in",
            "into",
            "is",
            "isn't",
            "it",
            "it's",
            "its",
            "itself",
            "let's",
            "me",
            "more",
            "most",
            "mustn't",
            "my",
            "myself",
            "no",
            "nor",
            "not",
            "of",
            "off",
            "on",
            "once",
            "only",
            "or",
            "other",
            "ought",
            "our",
            "ours",
            "ourselves",
            "out",
            "over",
            "own",
            "same",
            "shan't",
            "she",
            "she'd",
            "she'll",
            "she's",
            "should",
            "shouldn't",
            "so",
            "some",
            "such",
            "than",
            "that",
            "that's",
            "the",
            "their",
            "theirs",
            "them",
            "themselves",
            "then",
            "there",
            "there's",
            "these",
            "they",
            "they'd",
            "they'll",
            "they're",
            "they've",
            "this",
            "those",
            "through",
            "to",
            "too",
            "under",
            "until",
            "up",
            "very",
            "was",
            "wasn't",
            "we",
            "we'd",
            "we'll",
            "we're",
            "we've",
            "were",
            "weren't",
            "what",
            "what's",
            "when",
            "when's",
            "where",
            "where's",
            "which",
            "while",
            "who",
            "who's",
            "whom",
            "why",
            "why's",
            "with",
            "won't",
            "would",
            "wouldn't",
            "you",
            "you'd",
            "you'll",
            "you're",
            "you've",
            "your",
            "yours",
            "yourself",
            "yourselves",
        }
    )

    @classmethod
    def split_sentences(cls, text: str) -> list[str]:
        """Splits raw text into clean, trimmed sentences."""
        if not text:
            return []
        raw = re.split(r"(?<=[.!?])\s+", text)
        sentences = [s.strip() for s in raw if len(s.strip()) > 10]
        return sentences

    def summarize(self, text: str, max_sentences: int = 5, max_chars: int = 2000) -> str:
        """Extracts top salient sentences using term-frequency and positional weighting."""
        sentences = self.split_sentences(text)
        if not sentences:
            return ""
        if len(sentences) <= max_sentences and len(text) <= max_chars:
            return text.strip()

        # 1. Word frequency counting across document
        words = re.findall(r"\b[a-zA-Z]{3,}\b", text.lower())
        meaningful_words = [w for w in words if w not in self._STOPWORDS]
        if not meaningful_words:
            return " ".join(sentences[:max_sentences])[:max_chars]

        word_counts = collections.Counter(meaningful_words)
        max_freq = max(word_counts.values()) if word_counts else 1

        # 2. Score each sentence
        scored_sentences: list[tuple[int, float, str]] = []
        for idx, sentence in enumerate(sentences):
            sentence_words = re.findall(r"\b[a-zA-Z]{3,}\b", sentence.lower())
            if not sentence_words:
                continue

            # Term frequency sum
            raw_score = sum(word_counts[w] / max_freq for w in sentence_words if w in word_counts)

            # Length normalization (ideal sentence 12-35 words)
            length = len(sentence_words)
            if length < 5:
                length_mult = 0.5
            elif length > 45:
                length_mult = 0.8
            else:
                length_mult = 1.0

            # Positional bias: lead sentences carry higher baseline salience
            position_bias = 1.2 if idx < 3 else 1.0

            final_score = (raw_score / max(1, length)) * length_mult * position_bias
            scored_sentences.append((idx, final_score, sentence))

        if not scored_sentences:
            return " ".join(sentences[:max_sentences])[:max_chars]

        # 3. Pick top-N highest scoring sentences
        top_candidates = sorted(scored_sentences, key=lambda x: x[1], reverse=True)[:max_sentences]

        # 4. Reorder candidates by their original appearance order for coherence
        top_in_order = sorted(top_candidates, key=lambda x: x[0])

        # 5. Build summary up to character budget
        result: list[str] = []
        current_len = 0
        for _, _, sentence in top_in_order:
            if current_len + len(sentence) + 1 > max_chars:
                break
            result.append(sentence)
            current_len += len(sentence) + 1

        return " ".join(result) if result else (sentences[0][:max_chars])
