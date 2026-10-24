"""
SupremeAI — Video-to-Code Pipeline
==================================

Video frame analysis pipeline that:
- Extracts key frames from video at configurable intervals
- Analyzes frames for UI components using vision model
- Generates code (React components, Tailwind CSS) from analyzed frames
- Supports MP4, WebM, MOV formats
- Uses ffmpeg for frame extraction (with graceful fallback)
- Caches frame analysis results
- Returns structured component tree + generated code
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import subprocess
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile

from brain.model_router import ModelRouter
from core.cache import get_cache
from core.logging_config import logger
from core.upload_validator import validate_upload
from services.config_service import ConfigService

router = APIRouter(prefix="/video-to-code", tags=["video-to-code"])


class VideoFormat(StrEnum):
    MP4 = "mp4"
    WEBM = "webm"
    MOV = "mov"
    AVI = "avi"
    AUTO = "auto"


@dataclass(frozen=True)
class UIComponent:
    """A UI component extracted from video frame analysis."""

    id: str
    component_type: str  # button, card, form, navbar, etc.
    framework_hint: str  # react, vue, vanilla
    position: tuple[int, int, int, int]  # x, y, width, height
    properties: dict[str, Any]
    detected_text: str | None


@dataclass(frozen=True)
class CodeGenerationResult:
    """Result of video-to-code generation.

    Issue #449: ``error`` is set when generation produced an error-marker
    instead of real code, so callers can report honest failure — the old
    contract advertised ``status: success`` on error output.
    """

    component_tree: list[UIComponent]
    generated_code: str
    framework: str
    styling: str  # tailwind, css-modules, styled-components
    confidence: float
    error: str | None = None


# ── Constants ────────────────────────────────────────────────────────────────
FRAME_INTERVAL_SECONDS = 2  # Extract frame every N seconds
MAX_VIDEO_SIZE_MB = 50
VIDEO_CACHE_TTL = 3600  # 1 hour


class VideoFrameExtractor:
    """
    Extracts key frames from video using ffmpeg.
    Has graceful fallback when ffmpeg is unavailable.
    """

    @staticmethod
    def _check_ffmpeg() -> bool:
        """Check if ffmpeg is available."""
        try:
            result = subprocess.run(
                ["ffmpeg", "-version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0
        except (subprocess.SubprocessError, FileNotFoundError):
            return False

    async def extract_frames(
        self,
        video_path: str,
        interval: int = FRAME_INTERVAL_SECONDS,
        max_frames: int = 10,
    ) -> list[str]:
        """
        Extract frames from video at specified intervals.

        Args:
            video_path: Path to video file.
            interval: Seconds between frame extraction.
            max_frames: Maximum frames to extract.

        Returns:
            List of paths to extracted frame images.
        """
        if not self._check_ffmpeg():
            # Issue #449 honest-failure: the old "fallback" passed the VIDEO
            # FILE ITSELF to the vision model as an "image" — guaranteed
            # garbage output advertised as success. Refuse loudly instead.
            raise RuntimeError(
                "ffmpeg is not available on this deployment — video frame "
                "extraction is impossible. Install ffmpeg (or use the "
                "ci-docker image which bundles it) to enable video-to-code."
            )

        output_dir = Path(video_path).parent / f"frames_{Path(video_path).stem}"
        output_dir.mkdir(exist_ok=True)

        output_pattern = str(output_dir / "frame_%03d.jpg")

        cmd = [
            "ffmpeg",
            "-i",
            video_path,
            "-vf",
            f"fps=1/{interval}",
            "-vframes",
            str(max_frames),
            "-q:v",
            "2",
            output_pattern,
        ]

        try:
            # বাংলা মন্তব্য (Wave-3 perf): আগে এখানে blocking subprocess.run() ছিল —
            # ffmpeg extraction শেষ না হওয়া পর্যন্ত (সর্বোচ্চ ১২০ সেকেন্ড) ইভেন্ট লুপ
            # সম্পূর্ণ ফ্রিজ হয়ে যেত, ফলে একই worker-এ চলা অন্য সব request থেমে যেত।
            # তাই asyncio.create_subprocess_exec + await communicate() ব্যবহার করা
            # হয়েছে — argument construction, output-dir handling, stderr capture ও
            # logging আগের আচরণের হুবহু মতো।
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                _, stderr_data = await asyncio.wait_for(proc.communicate(), timeout=120)
            except TimeoutError:
                # বাংলা মন্তব্য: timeout হলে child ffmpeg-কে kill করতে হয় নইলে
                # zombie প্রসেস রয়ে যায় (আগে subprocess.run-এর timeout এটা করত)।
                try:
                    proc.kill()
                except ProcessLookupError as kill_err:
                    # বাংলা মন্তব্য: প্রসেস ইতিমধ্যে বন্ধ হয়ে গেলে kill আর লাগে না —
                    # সেটা silent swallow নয়, লাউড warning।
                    logger.warning(f"ffmpeg already exited before kill: {kill_err}")
                await proc.wait()
                raise
            if proc.returncode != 0:
                # বাংলা মন্তব্য: subprocess.run(check=True) এর সমতুল্য — non-zero exit
                # হলে CalledProcessError, যাতে নিচের logging/error path আগের মতোই থাকে।
                raise subprocess.CalledProcessError(proc.returncode, cmd, stderr=stderr_data)
            return [str(p) for p in output_dir.glob("*.jpg")][:max_frames]
        except (subprocess.SubprocessError, TimeoutError) as e:
            logger.error(f"Frame extraction failed: {e}")
            raise RuntimeError(f"Frame extraction failed: {e}") from e

    async def _fallback_extract(self, video_path: str, max_frames: int) -> list[str]:
        """REMOVED (issue #449): the video-file-as-image fallback was dishonest.

        extract_frames() now raises a clear error when ffmpeg is unavailable
        instead of passing the raw video file to the vision model.
        """
        raise RuntimeError(
            "_fallback_extract removed (issue #449): it fed the raw video file "
            "to the vision model as an 'image'. Install ffmpeg instead."
        )


class FrameAnalyzer:
    """
    Analyzes video frames using vision model to extract UI components.
    """

    def __init__(self, llm_router: ModelRouter | None = None) -> None:
        self.llm_router = llm_router or ModelRouter()
        self.cache = get_cache()

    def _cache_key(self, frame_path: str, offset: int) -> str:
        stat = os.stat(frame_path) if os.path.exists(frame_path) else None
        stat_str = f"{stat.st_mtime}" if stat else ""
        return f"frame_analysis:{hashlib.sha256((frame_path + stat_str).encode()).hexdigest()[:16]}"

    async def analyze(
        self,
        frame_path: str,
        timestamp_seconds: int = 0,
        framework_hint: str = "react",
    ) -> list[UIComponent]:
        """
        Analyze a frame image for UI components.

        Args:
            frame_path: Path to frame image.
            timestamp_seconds: Timestamp for context.
            framework_hint: Preferred framework for code gen.

        Returns:
            List of detected UI components.
        """
        cache_key = self._cache_key(frame_path, timestamp_seconds)
        cached = await self.cache.get(cache_key)
        if cached:
            return [UIComponent(**c) if isinstance(c, dict) else c for c in cached]

        import base64

        # NOTE (issue #2249): the base64 payload previously fed the legacy
        # `images=[...]` kwarg, which NO provider in the retired services/llm
        # stack ever consumed (payloads were text-only). The read is kept for
        # exact file-validation parity; the kwarg is no longer forwarded.
        with open(frame_path, "rb") as f:
            base64_image = base64.b64encode(f.read()).decode("utf-8")  # noqa: F841 — see note above

        prompt = (
            f"Analyze this UI design screenshot and extract all components. "
            f"Focus on {framework_hint} component patterns. "
            "Return JSON array: "
            '{"id", "component_type", "position": [x, y, w, h], "properties": {}, "detected_text"}. '
            "Include buttons, forms, cards, navigation, text blocks, images."
        )

        try:
            max_tokens = await ConfigService.get_config(None, "llm_max_tokens_video", 1500)
            result = await self.llm_router.async_route_and_generate(
                prompt=prompt,
                task_type="vision",
                max_tokens=max_tokens,
                # NOTE (issue #2249): the legacy `images=[...]` kwarg was dropped
                # here — git archaeology on the retired providers.py confirms NO
                # provider ever consumed it (payload built text-only parts), so
                # removing it is a zero-capability-change cleanup.
            )

            text = result.get("text", "") if isinstance(result, dict) else ""
            text = re.sub(r"^```(?:json)?\s*", "", text.strip())
            text = re.sub(r"\s*```$", "", text)

            data = json.loads(text)
            components = [
                UIComponent(
                    id=item.get("id", f"c_{i}"),
                    component_type=item.get("component_type", "unknown"),
                    framework_hint=framework_hint,
                    position=tuple(item.get("position", [0, 0, 100, 50]))[:4],
                    properties=item.get("properties", {}),
                    detected_text=item.get("detected_text"),
                )
                for i, item in enumerate(data)
            ]

            await self.cache.set(cache_key, [c.__dict__ for c in components], ttl=VIDEO_CACHE_TTL)
            return components

        except Exception as e:
            logger.error(f"Frame analysis failed: {e}")
            return []


class CodeGenerator:
    """
    Generates code from UI component tree.
    """

    def __init__(self, llm_router: ModelRouter | None = None) -> None:
        self.llm_router = llm_router or ModelRouter()
        self.cache = get_cache()

    async def generate(
        self,
        components: list[UIComponent],
        framework: str = "react",
        styling: str = "tailwind",
    ) -> str:
        """
        Generate component code from UI component tree.

        Args:
            components: List of UI components.
            framework: Target framework (react, vue, svelte).
            styling: Styling approach (tailwind, css-modules, styled-components).

        Returns:
            Generated component code.
        """
        cache_key = f"code_gen:{framework}:{styling}:{hashlib.sha256(str([c.id for c in components]).encode()).hexdigest()[:16]}"

        cached = await self.cache.get(cache_key)
        if cached:
            return cached  # type: ignore

        component_descriptions = []
        for c in components:
            desc = f"- {c.id}: {c.component_type}"
            if c.detected_text:
                desc += f' with text "{c.detected_text}"'
            component_descriptions.append(desc)

        prompt = (
            f"You are a UI component generator. Generate a complete {framework} component "
            f"using {styling} for styling. Component tree:\n"
            + "\n".join(component_descriptions)
            + "\n\nReturn only valid code, no markdown."
        )

        try:
            max_tokens = await ConfigService.get_config(None, "llm_max_tokens_video", 2000)
            result = await self.llm_router.async_route_and_generate(
                prompt=prompt,
                task_type="generation",
                max_tokens=max_tokens,
            )

            code = result.get("text", "") if isinstance(result, dict) else ""

            # Clean up code formatting
            code = re.sub(r"^```(?:jsx?|tsx?|css)?\s*", "", code.strip())
            code = re.sub(r"\s*```$", "", code)

            await self.cache.set(cache_key, code, ttl=VIDEO_CACHE_TTL)
            return code

        except Exception as e:
            logger.error(f"Code generation failed: {e}")
            return f"// Error generating code: {e}"


class VideoToCodePipeline:
    """
    Main pipeline that orchestrates video-to-code conversion.
    """

    def __init__(
        self,
        extractor: VideoFrameExtractor | None = None,
        analyzer: FrameAnalyzer | None = None,
        generator: CodeGenerator | None = None,
    ) -> None:
        self.extractor = extractor or VideoFrameExtractor()
        self.analyzer = analyzer or FrameAnalyzer()
        self.generator = generator or CodeGenerator()
        self.cache = get_cache()
        logger.info("VideoToCodePipeline initialized")

    async def process(
        self,
        video_path: str,
        framework: str = "react",
        styling: str = "tailwind",
        interval: int = FRAME_INTERVAL_SECONDS,
    ) -> CodeGenerationResult:
        """
        Full pipeline: extract → analyze → generate.

        Args:
            video_path: Path to video file.
            framework: Target UI framework.
            styling: CSS styling approach.
            interval: Frame extraction interval in seconds.

        Returns:
            CodeGenerationResult with all components and generated code.
        """
        # Step 1: Extract frames
        frames = await self.extractor.extract_frames(video_path, interval)

        # Step 2: Analyze all frames
        all_components: list[UIComponent] = []
        for i, frame in enumerate(frames):
            components = await self.analyzer.analyze(
                str(frame), timestamp_seconds=i * interval, framework_hint=framework
            )
            all_components.extend(components)

        # Deduplicate by ID
        seen = set()
        deduped = []
        for c in all_components:
            if c.id not in seen:
                seen.add(c.id)
                deduped.append(c)

        # Step 3: Generate code
        code = await self.generator.generate(deduped, framework, styling)

        return CodeGenerationResult(
            component_tree=deduped,
            generated_code=code,
            framework=framework,
            styling=styling,
            confidence=0.8 if all_components else 0.4,
            error=code.startswith("// Error generating code") or None,
        )


# Singleton
_pipeline_instance: VideoToCodePipeline | None = None


def get_video_pipeline() -> VideoToCodePipeline:
    """Get or create the singleton VideoToCodePipeline instance."""
    global _pipeline_instance
    if _pipeline_instance is None:
        _pipeline_instance = VideoToCodePipeline()
    return _pipeline_instance


@router.post("/process")
async def process_video(
    file: UploadFile = File(...),
    framework: str = "react",
    styling: str = "tailwind",
):
    """Upload a video and generate UI component code."""
    await validate_upload(file)

    if not file.content_type or not file.content_type.startswith("video/"):
        raise HTTPException(status_code=400, detail="File must be a video")

    # Save temporarily
    import tempfile

    suffix = Path(file.filename or "video.mp4").suffix or ".mp4"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        result = await get_video_pipeline().process(tmp_path, framework, styling)
        # Issue #449 honest-failure: an error-marker "code" or an error field
        # must NOT be advertised as success.
        if result.error or result.generated_code.startswith("// Error generating code"):
            raise HTTPException(
                status_code=502,
                detail={
                    "status": "failed",
                    "error": "VIDEO_CODE_GENERATION_FAILED",
                    "detail": result.generated_code[:300],
                },
            )
        return {
            "status": "success",
            "framework": result.framework,
            "styling": result.styling,
            "component_count": len(result.component_tree),
            "code": result.generated_code,
            "confidence": result.confidence,
        }
    except HTTPException:
        raise
    except RuntimeError as e:
        # ffmpeg missing / frame extraction failed — honest 503, not success.
        raise HTTPException(
            status_code=503,
            detail={
                "status": "failed",
                "error": "VIDEO_PIPELINE_UNAVAILABLE",
                "detail": str(e)[:300],
            },
        ) from e
    finally:
        os.unlink(tmp_path)
