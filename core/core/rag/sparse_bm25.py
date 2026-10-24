# SupremeAI 2.0 — Sparse BM25 Keyword Search Engine
# বাংলা মন্তব্য: এটি Okapi BM25 অ্যালগরিদমের সাহায্যে টেক্সট এবং বাংলা টোকেনাইজার প্রয়োগ করে কিওয়ার্ড সার্চ পরিচালনা করে।

import math
import re
from typing import Any


class SparseBM25Index:
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.documents: list[dict[str, Any]] = []
        self.doc_len: list[int] = []
        self.avg_doc_len: float = 0.0
        self.doc_freqs: dict[str, int] = {}
        self.idf: dict[str, float] = {}
        self.corpus_size: int = 0

    def tokenize(self, text: str) -> list[str]:
        # বাংলা মন্তব্য: বাংলা এবং ইংরেজি অক্ষর সমন্বিত টোকেনাইজেশন
        if not text:
            return []
        text_clean = re.sub(r"[^\w\s\u0980-\u09FF]", " ", text.lower())
        tokens = [t.strip() for t in text_clean.split() if t.strip()]
        return tokens

    def fit(self, documents: list[dict[str, Any]], text_key: str = "text") -> None:
        """
        Index documents for BM25 search.
        Each document should be a dict containing text_key.
        """
        self.documents = documents
        self.corpus_size = len(documents)
        if self.corpus_size == 0:
            self.avg_doc_len = 0.0
            return

        self.doc_len = []
        self.doc_freqs = {}

        total_words = 0
        for doc in documents:
            text = doc.get(text_key, "")
            tokens = self.tokenize(text)
            self.doc_len.append(len(tokens))
            total_words += len(tokens)

            # Count unique terms in document
            unique_terms = set(tokens)
            for term in unique_terms:
                self.doc_freqs[term] = self.doc_freqs.get(term, 0) + 1

        self.avg_doc_len = total_words / self.corpus_size if self.corpus_size > 0 else 0.0

        # Calculate Inverse Document Frequency (IDF) with smoothing
        self.idf = {}
        for term, freq in self.doc_freqs.items():
            idf_val = math.log((self.corpus_size - freq + 0.5) / (freq + 0.5) + 1.0)
            self.idf[term] = max(idf_val, 0.01)

    def search(self, query: str, top_k: int = 10, text_key: str = "text") -> list[dict[str, Any]]:
        """
        Perform Okapi BM25 keyword search for given query.
        Returns top_k matching documents with 'bm25_score'.
        """
        if not self.documents or not query.strip():
            return []

        query_tokens = self.tokenize(query)
        if not query_tokens:
            return []

        scores = [0.0] * self.corpus_size

        for idx, doc in enumerate(self.documents):
            doc_tokens = self.tokenize(doc.get(text_key, ""))
            if not doc_tokens:
                continue

            # Term frequencies in current document
            tf_map: dict[str, int] = {}
            for t in doc_tokens:
                tf_map[t] = tf_map.get(t, 0) + 1

            doc_len = self.doc_len[idx]
            len_norm = (
                1.0
                - self.b
                + self.b * (doc_len / self.avg_doc_len if self.avg_doc_len > 0 else 1.0)
            )

            score = 0.0
            for q_term in query_tokens:
                if q_term not in tf_map:
                    continue
                tf = tf_map[q_term]
                idf_val = self.idf.get(q_term, 0.0)
                numerator = tf * (self.k1 + 1.0)
                denominator = tf + self.k1 * len_norm
                score += idf_val * (numerator / denominator)

            scores[idx] = score

        # Rank results
        ranked_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        results = []
        for i in ranked_indices[:top_k]:
            if scores[i] <= 0.0:
                continue
            doc_copy = dict(self.documents[i])
            doc_copy["bm25_score"] = float(scores[i])
            results.append(doc_copy)

        return results
