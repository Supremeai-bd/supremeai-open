# backend/skills/core_doc_summarizer.py
import os

from core.config_cache import config_cache
from core.logging_config import logger

# বাংলা মন্তব্য: google-genai প্যাকেজ CI-তে ঠিকমতো install না থাকলে graceful fallback
try:
    from google import genai
    from google.genai import types

    _GENAI_AVAILABLE = True
except ImportError:
    _GENAI_AVAILABLE = False
    genai = None  # type: ignore[assignment]
    types = None  # type: ignore[assignment]

from core.resilience.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError

# বাংলা মন্তব্য: Doc Summarizer এর জন্য প্রথক Circuit Breaker রেজিস্ট্রি
# knowledge_qa এর ব্রেকার থেকে আলাদা রাখা হয়েছে যাতে একটা failure অন্যটার সার্কিট block না করে
_gemini_summarizer_breaker: CircuitBreaker = CircuitBreaker(
    name="gemini_doc_summarizer",
    failure_threshold=5,
    recovery_timeout=60,
)


def execute_tool(payload: dict) -> dict:
    """Strict Supreme Tool Contract for Sandbox-isolated File Summarization"""
    try:
        # ১. ইনপুট স্যানিটাইজেশন
        file_content = payload.get("file_content", "").strip()
        summary_length = payload.get("summary_length", "concise")  # concise, detailed

        if not file_content:
            return {
                "success": False,
                "error": "Document content is empty or unreadable.",
            }

        # ২. ডিফেন্সিভ সাইজ গার্ড (বাজেট এনফোর্সমেন্ট)
        # অতিরিক্ত বড় ফাইল হলে টোকেন কস্ট ও লেটেন্সি বাউন্ডারি ব্রেক করা রুখতে
        if len(file_content) > 100000:  # আনুমানিক ২৫,০০০ শব্দ
            return {
                "success": False,
                "error": "Document exceeds the maximum permissible payload for this skill.",
            }

        # ৩. মডার্ন Gemini Client ইনিশিয়ালাইজেশন
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            return {
                "success": False,
                "error": "Gemini API key configuration drift detected.",
            }

        client = genai.Client(api_key=api_key)

        # ৪. কনটেক্সট স্পেসিফিক প্রম্পট ইঞ্জিনিয়ারিং
        system_instruction = (
            "You are an expert document intelligence agent operating in a secure corporate sandbox. "
            "Your task is to analyze the provided document content and extract a structured summary. "
            "Highlight the core objectives, key action items, and financial metrics if present. "
            "Maintain an objective corporate tone and do not extrapolate facts beyond the text."
        )

        user_prompt = f"""
        [Target Length: {summary_length.upper()}]

        [Document Source Content]
        {file_content}
        """

        # বাংলা মন্তব্য: Circuit Breaker দিয়ে Gemini ইনফারেন্স কল র্যাপ করা হতেছে
        # OPEN স্টেটে Gemini API হিট না করে তাৎক্ষণিক ফরোয়ার্ড রিজেক্ট হয়
        try:
            response = _gemini_summarizer_breaker.call(
                client.models.generate_content,
                model="gemini-2.5-flash",
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=config_cache.get("core_doc_summarizer_temperature", 0.3),
                ),
            )
        except CircuitBreakerOpenError as cb_exc:
            logger.warning(f"🚨 Doc Summarizer Circuit Breaker OPEN: {cb_exc}")
            return {
                "success": False,
                "error": "LLM infrastructure is temporarily unavailable. Circuit breaker active. Please retry in 60 seconds.",
            }

        return {
            "success": True,
            "result": {
                "summary": response.text.strip(),
                "extracted_bytes_processed": len(file_content.encode("utf-8")),
                "model_enforced": "gemini-2.5-flash",
            },
        }

    except Exception as e:
        logger.error(f"Critical execution barrier inside core_doc_summarizer: {e!s}")
        return {"success": False, "error": f"File analysis exception: {e!s}"}
