"""src/utils/audio_cache.py — Ephemeral SHA-256 keyed audio cache.

Design notes (honesty + portability):
- EPHEMERAL BY CONTRACT: caches synthesized audio for repeated phrases
  (e.g. "সিস্টেম সম্পূর্ণ স্বাভাবিক আছে" status summaries) to eliminate
  redundant network round-trips. Entries live in memory or a temp
  directory — never in persistent storage, never across reboots, and
  never treated as a source of truth.
- KEY = SHA-256 over the exact synthesis inputs (text + voice + rate +
  pitch) so a cache hit is byte-equivalent to a fresh synthesis.
- TWO BACKENDS:
    memory (default) — dict + LRU eviction + TTL via an injectable clock.
    temp             — one file per key under a private temp directory
                       (tempfile.mkdtemp), same TTL semantics, removed
                       on close() (and best-effort on GC).
- BOUNDS: max_entries (LRU eviction) + ttl_s (lazy expiry on read) keep
  the cache O(bytes-cap), never unbounded.
- ZERO DEPENDENCIES: hashlib + tempfile + collections only.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
import time
from collections import OrderedDict
from typing import Optional


class AudioCacheError(RuntimeError):
    """Raised when a cache backend cannot be initialized or written."""


class AudioCache:
    """Ephemeral audio cache keyed by SHA-256 of the synthesis inputs."""

    def __init__(
        self,
        backend: str = "memory",
        max_entries: int = 128,
        ttl_s: float = 3600.0,
        clock=time.monotonic,
    ) -> None:
        if backend not in ("memory", "temp"):
            raise AudioCacheError(
                "unknown cache backend %r; expected 'memory' or 'temp'" % backend
            )
        if max_entries < 1:
            raise AudioCacheError("max_entries must be >= 1")
        if ttl_s <= 0:
            raise AudioCacheError("ttl_s must be > 0")
        self.backend = backend
        self.max_entries = int(max_entries)
        self.ttl_s = float(ttl_s)
        self._clock = clock
        self._hits = 0
        self._misses = 0
        if backend == "memory":
            self._store: "OrderedDict[str, tuple[bytes, float]]" = OrderedDict()
            self._temp_dir: Optional[str] = None
        else:
            try:
                self._temp_dir = tempfile.mkdtemp(prefix="supremeai-voice-cache-")
            except OSError as exc:
                raise AudioCacheError("cannot create temp cache dir: %s" % exc) from exc
            self._store = OrderedDict()  # key -> (size, expires_at) index

    # -- key derivation ------------------------------------------------------

    @staticmethod
    def key_for(text: str, voice: str = "", rate: str = "", pitch: str = "") -> str:
        """SHA-256 over the exact synthesis inputs (stable, collision-safe)."""
        digest = hashlib.sha256()
        for part in (text, voice, rate, pitch):
            digest.update(part.encode("utf-8"))
            digest.update(b"\x1f")  # unit separator: no field-boundary bleed
        return digest.hexdigest()

    # -- core operations ------------------------------------------------------

    def get(self, key: str) -> Optional[bytes]:
        """Return cached audio or None (expired/absent). Counts statistics."""
        entry = self._store.get(key)
        if entry is None:
            self._misses += 1
            return None
        if self.backend == "memory":
            audio, expires_at = entry
            if self._clock() >= expires_at:
                del self._store[key]
                self._misses += 1
                return None
            self._store.move_to_end(key)  # LRU touch
            self._hits += 1
            return audio
        # temp backend: entry is (size, expires_at); file holds the bytes
        _size, expires_at = entry
        path = self._path(key)
        if self._clock() >= expires_at or not os.path.exists(path):
            self._store.pop(key, None)
            self._delete_file(path)
            self._misses += 1
            return None
        try:
            with open(path, "rb") as handle:
                audio = handle.read()
        except OSError:
            self._store.pop(key, None)
            self._misses += 1
            return None
        self._store.move_to_end(key)
        self._hits += 1
        return audio

    def put(self, key: str, audio: bytes) -> None:
        """Store audio under key; evict LRU beyond max_entries."""
        if not audio:
            return  # never cache empty payloads
        expires_at = self._clock() + self.ttl_s
        if self.backend == "memory":
            self._store[key] = (bytes(audio), expires_at)
            self._store.move_to_end(key)
            while len(self._store) > self.max_entries:
                self._store.popitem(last=False)
            return
        path = self._path(key)
        try:
            with open(path, "wb") as handle:
                handle.write(audio)
        except OSError as exc:
            raise AudioCacheError("temp cache write failed: %s" % exc) from exc
        self._store[key] = (len(audio), expires_at)
        self._store.move_to_end(key)
        while len(self._store) > self.max_entries:
            stale_key, _ = self._store.popitem(last=False)
            self._delete_file(self._path(stale_key))

    # -- statistics -----------------------------------------------------------

    def stats(self) -> dict:
        """Honest telemetry: hits, misses, entries, cached bytes."""
        cached_bytes = 0
        if self.backend == "memory":
            cached_bytes = sum(len(audio) for audio, _ in self._store.values())
        else:
            cached_bytes = sum(size for size, _ in self._store.values())
        return {
            "backend": self.backend,
            "entries": len(self._store),
            "cached_bytes": cached_bytes,
            "hits": self._hits,
            "misses": self._misses,
            "max_entries": self.max_entries,
            "ttl_s": self.ttl_s,
        }

    # -- lifecycle ------------------------------------------------------------

    def clear(self) -> None:
        """Drop every entry (memory) or wipe the temp directory (temp)."""
        if self.backend == "memory":
            self._store.clear()
            return
        for key in list(self._store):
            self._delete_file(self._path(key))
        self._store.clear()

    def close(self) -> None:
        """Release resources; temp backend removes its private directory."""
        self.clear()
        if self._temp_dir:
            try:
                os.rmdir(self._temp_dir)
            except OSError:
                pass  # best-effort: dir may still hold raced files
            self._temp_dir = None

    def __del__(self):  # pragma: no cover - GC best effort
        try:
            self.close()
        except Exception:
            pass

    # -- internals -------------------------------------------------------------

    def _path(self, key: str) -> str:
        if not self._temp_dir:  # pragma: no cover - post-close misuse
            raise AudioCacheError("temp cache already closed")
        return os.path.join(self._temp_dir, key)

    @staticmethod
    def _delete_file(path: str) -> None:
        try:
            os.unlink(path)
        except OSError:
            pass  # best-effort cleanup
