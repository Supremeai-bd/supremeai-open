"""SWE benchmark gate (plan Way 15) — frozen corpus + confusion-matrix gate."""

from .runner import BenchmarkReport, corpus_fingerprint, load_corpus, run_benchmark

__all__ = ["BenchmarkReport", "corpus_fingerprint", "load_corpus", "run_benchmark"]
