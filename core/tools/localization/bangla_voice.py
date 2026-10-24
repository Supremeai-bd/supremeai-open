from __future__ import annotations

import os
from dataclasses import dataclass

from core.logging_config import logger


@dataclass
class BanglaVoiceResult:
    text: str
    source: str
    language: str = "bn"


class BanglaVoice:
    def __init__(self, model_size: str = "small", prefer_coqui: bool = False) -> None:
        self.model_size = model_size
        self.prefer_coqui = prefer_coqui
        self._stt_available = self._check_stt_available()
        self._tts_available = self._check_tts_available()

    def _check_stt_available(self) -> bool:
        try:
            import whisper  # type: ignore

            return whisper is not None
        except Exception as e:
            try:
                import loguru

                loguru.logger.error(f"Tool execution error: {e}")
            except Exception as e:
                logger.warning(f"Exception suppressed: {e}")
            return False

    def _check_tts_available(self) -> bool:
        try:
            from TTS.api import TTS  # type: ignore

            return TTS is not None
        except Exception as e:
            try:
                import loguru

                loguru.logger.error(f"Tool execution error: {e}")
            except Exception as e:
                logger.warning(f"Exception suppressed: {e}")
            return False

    def transcribe(self, audio_path: str) -> BanglaVoiceResult:
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
        try:
            if self._stt_available:
                return self._transcribe_whisper(audio_path)
            return self._transcribe_whisper(audio_path)
        except Exception as exc:  # pylint: disable=broad-except
            raise RuntimeError(f"Bangla STT failed: {exc}") from exc

    def speak(self, text: str, output_path: str = "bangla_speech.mp3") -> BanglaVoiceResult:
        if not text:
            raise ValueError("Empty text")
        try:
            if self.prefer_coqui and self._tts_available:
                return self._speak_coqui(text, output_path)
            if self._tts_available:
                return self._speak_coqui(text, output_path)
            return self._speak_gtts(text, output_path)
        except Exception as exc:  # pylint: disable=broad-except
            raise RuntimeError(f"Bangla TTS failed: {exc}") from exc

    def _transcribe_whisper(self, audio_path: str) -> BanglaVoiceResult:
        try:
            import whisper  # type: ignore
        except ImportError as exc:
            raise RuntimeError("whisper is not installed") from exc
        model = whisper.load_model(self.model_size)
        result = model.transcribe(audio_path, language="bn")
        return BanglaVoiceResult(text=result.get("text", ""), source="whisper")

    def _speak_gtts(self, text: str, output_path: str) -> BanglaVoiceResult:
        try:
            from gtts import gTTS  # type: ignore
        except ImportError as exc:
            raise RuntimeError("gTTS is not installed") from exc
        tts = gTTS(text=text, lang="bn")
        tts.save(output_path)
        return BanglaVoiceResult(text=text, source="gtts", language="bn")

    def _speak_coqui(self, text: str, output_path: str) -> BanglaVoiceResult:
        try:
            from TTS.api import TTS  # type: ignore
        except ImportError as exc:
            raise RuntimeError("Coqui TTS is not installed") from exc
        tts = TTS(model_name="tts_models/bn/bn-IN/indic-tts-coqui-medium", progress_bar=False)
        tts.tts_to_file(text=text, file_path=output_path)
        return BanglaVoiceResult(text=text, source="coqui", language="bn")
