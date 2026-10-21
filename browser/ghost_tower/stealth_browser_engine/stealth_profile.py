"""Coherent stealth fingerprint generation (deterministic, stdlib-only).

Design goals (per issue #502):
  - Coherent canvas PRNG: one session seed drives ALL noise, so every derived
    value is reproducible and internally consistent (no per-read entropy that
    anti-bot engines can flag as instability).
  - WebGL normalization: only STANDARD, widely deployed vendor/renderer pairs
    are emitted (Windows/Direct3D class strings). Exotic or driver-specific
    strings are intentionally absent from the table.
  - Natural input curves: cubic-Bezier pointer paths with bounded jitter.

Nothing in this module launches a browser or touches the network.
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Dict, List, Tuple

__all__ = [
    "StealthProfile",
    "bezier_path",
    "webgl_pairs",
]

# Standard ANGLE-on-D3D class pairs (vendor, renderer). Deliberately plain;
# the reflection contract bans specific driver strings and this table simply
# never contained them (asserted by the offline test battery).
_WEBGL_PAIRS: Tuple[Tuple[str, str], ...] = (
    ("Google Inc. (NVIDIA)", "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    ("Google Inc. (Intel)", "ANGLE (Intel, Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    ("Google Inc. (AMD)", "ANGLE (AMD, AMD Radeon(TM) Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    ("Google Inc. (Qualcomm)", "ANGLE (Qualcomm, Adreno (TM) 740 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
)


def webgl_pairs() -> Tuple[Tuple[str, str], ...]:
    """Read-only view of the normalized vendor/renderer table."""
    return _WEBGL_PAIRS


@dataclass(frozen=True)
class StealthProfile:
    """One deterministic browser fingerprint derived from a text seed.

    Determinism contract: identical seeds produce byte-identical fingerprints
    on every platform (hashlib + math only, no RNG state, no time, no I/O).
    """

    seed: str
    canvas_noise_seed: int
    webgl_vendor: str
    webgl_renderer: str
    audio_fingerprint: float
    hardware_concurrency: int
    device_memory_gb: int
    screen_width: int
    screen_height: int
    color_depth: int = 24

    def to_dict(self) -> Dict[str, object]:
        """Plain-dict view suitable for JS injection at the runtime tier."""
        return {
            "canvasNoiseSeed": self.canvas_noise_seed,
            "webglVendor": self.webgl_vendor,
            "webglRenderer": self.webgl_renderer,
            "audioFingerprint": self.audio_fingerprint,
            "hardwareConcurrency": self.hardware_concurrency,
            "deviceMemoryGb": self.device_memory_gb,
            "screen": [self.screen_width, self.screen_height],
            "colorDepth": self.color_depth,
        }

    def canvas_noise(self, width: int = 16, height: int = 16) -> List[List[int]]:
        """Deterministic per-pixel noise in 0..255 (coherent across calls).

        Same (seed, width, height) always yields the same matrix; the matrix
        is a smooth gradient + hash jitter so it survives visual inspection.
        """
        if width <= 0 or height <= 0:
            raise ValueError("canvas dimensions must be positive")
        base = self.canvas_noise_seed & 0xFFFFFFFF
        matrix: List[List[int]] = []
        for y in range(height):
            row: List[int] = []
            for x in range(width):
                mixed = hashlib.sha256(
                    f"{base}:{x}:{y}".encode("utf-8")
                ).digest()
                gradient = (x * 7 + y * 13) % 256
                row.append((mixed[0] + gradient) % 256)
            matrix.append(row)
        return matrix


def bezier_path(
    start: Tuple[float, float],
    end: Tuple[float, float],
    steps: int = 48,
    jitter: float = 1.5,
    seed: str = "input",
) -> List[Tuple[float, float]]:
    """Natural pointer gesture: cubic Bezier with deterministic jitter.

    Returns `steps` points from `start` (inclusive) toward `end` (exclusive of
    overshoot), never NaN, monotone in t. Deterministic per seed so tests and
    replays agree.
    """
    if steps < 2:
        raise ValueError("steps must be >= 2")
    x0, y0 = float(start[0]), float(start[1])
    x1, y1 = float(end[0]), float(end[1])
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    ctrl1 = (
        x0 + (x1 - x0) * 0.25 + ((digest[0] % 40) - 20),
        y0 + (y1 - y0) * 0.15 + ((digest[1] % 40) - 20),
    )
    ctrl2 = (
        x0 + (x1 - x0) * 0.75 + ((digest[2] % 40) - 20),
        y0 + (y1 - y0) * 0.85 + ((digest[3] % 40) - 20),
    )
    points: List[Tuple[float, float]] = []
    for i in range(steps):
        t = i / (steps - 1)
        u = 1.0 - t
        bx = (
            u * u * u * x0
            + 3 * u * u * t * ctrl1[0]
            + 3 * u * t * t * ctrl2[0]
            + t * t * t * x1
        )
        by = (
            u * u * u * y0
            + 3 * u * u * t * ctrl1[1]
            + 3 * u * t * t * ctrl2[1]
            + t * t * t * y1
        )
        # Bounded deterministic jitter that fades at both endpoints.
        fade = math.sin(math.pi * t)
        jx = ((digest[(4 + i) % 32] % 200) / 100.0 - 1.0) * jitter * fade
        jy = ((digest[(4 + i + 7) % 32] % 200) / 100.0 - 1.0) * jitter * fade
        points.append((bx + jx, by + jy))
    return points


def _pick_pair(digest: bytes) -> Tuple[str, str]:
    return _WEBGL_PAIRS[digest[5] % len(_WEBGL_PAIRS)]


def generate(seed: str) -> StealthProfile:
    """Derive a fully deterministic fingerprint from `seed` (fail-closed)."""
    if not seed or not isinstance(seed, str):
        raise ValueError("seed must be a non-empty string")
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    vendor, renderer = _pick_pair(digest)
    cores = 4 + (digest[6] % 13)  # 4..16, plausible power-of-two-ish range
    memory_choices = (2, 4, 8, 8, 16, 16, 32)
    memory = memory_choices[digest[7] % len(memory_choices)]
    widths = (1366, 1440, 1536, 1600, 1920, 2560)
    width = widths[digest[8] % len(widths)]
    height_by_width = {
        1366: 768,
        1440: 900,
        1536: 864,
        1600: 900,
        1920: 1080,
        2560: 1440,
    }
    height = height_by_width[width]
    audio = 0.0000001 + (int.from_bytes(digest[9:13], "big") % 10_000) / 100_000_000.0
    return StealthProfile(
        seed=seed,
        canvas_noise_seed=int.from_bytes(digest[0:4], "big") & 0x7FFFFFFF,
        webgl_vendor=vendor,
        webgl_renderer=renderer,
        audio_fingerprint=audio,
        hardware_concurrency=cores,
        device_memory_gb=memory,
        screen_width=width,
        screen_height=height,
    )
