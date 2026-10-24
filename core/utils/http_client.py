"""
শেয়ার্ড HTTP ক্লায়েন্ট ইউটিলিটি — httpx AsyncClient-এর পুনরাবৃত্তিমূলক ব্যবহার
দূর করতে একটি কেন্দ্রীয় ফ্যাক্টরি এবং স্ট্যান্ডার্ড এরর হ্যান্ডলিং।

আগে প্রতিটি ফাংশনে `async with httpx.AsyncClient(timeout=X) as client:` লিখতে হতো
এবং `_handle_api_error()` প্রতি মডিউলে আলাদা করে ডিফাইন করা হতো।
এখন এই শেয়ার্ড মডিউল থেকে ইম্পোর্ট করলেই চলবে।
"""

from typing import Any

import httpx

from core.logging_config import logger

_shared_client: httpx.AsyncClient | None = None


async def close_shared_client() -> None:
    """Close the process-wide client during application shutdown."""
    global _shared_client
    if _shared_client is not None:
        await _shared_client.aclose()
        _shared_client = None


def set_shared_client(client: httpx.AsyncClient | None) -> None:
    """Register the application-managed client used by helper functions."""
    global _shared_client
    _shared_client = client


def get_shared_client() -> httpx.AsyncClient | None:
    """Return the application-managed client, if the app lifespan is active."""
    return _shared_client


# বাংলা মন্তব্য: Anti-Silent Hanging — প্রতিটি HTTP কলে সর্বোচ্চ ১০ সেকেন্ড টাইমআউট এনফোর্সড
DEFAULT_TIMEOUT = httpx.Timeout(10.0, connect=5.0)
# বাংলা মন্তব্য: Unbounded outbound concurrency রোধে bounded connection pool।
DEFAULT_LIMITS = httpx.Limits(max_connections=100, max_keepalive_connections=20)


async def safe_fetch(
    url: str,
    *,
    client: httpx.AsyncClient | None = None,
    **kwargs: Any,
) -> httpx.Response:
    """Fetch with the lifespan-managed pool when one is available."""
    managed = client or get_shared_client()
    kwargs.setdefault("timeout", DEFAULT_TIMEOUT)
    if managed is not None:
        return await managed.get(url, **kwargs)

    async with create_async_client() as fallback:
        return await fallback.get(url, **kwargs)


def create_async_client(
    timeout: float | httpx.Timeout = DEFAULT_TIMEOUT,
    **kwargs: Any,
) -> httpx.AsyncClient:
    """কনফিগার করা httpx.AsyncClient তৈরি করে।

    Args:
        timeout: রিকোয়েস্ট টাইমআউট সেকেন্ডে।
        **kwargs: httpx.AsyncClient-এ পাস করার অতিরিক্ত আর্গুমেন্ট।

    Returns:
        httpx.AsyncClient ইন্সট্যান্স (context manager হিসেবে ব্যবহার করুন)।
    """
    kwargs.setdefault("limits", DEFAULT_LIMITS)
    return httpx.AsyncClient(timeout=timeout, **kwargs)


def handle_api_error(exc: Exception, status_code: int | None = None) -> str:
    """API এরর থেকে স্ট্যান্ডার্ড ইউজার-ফ্রেন্ডলি মেসেজ তৈরি করে।

    সব MCP টুল এবং API ক্লায়েন্ট থেকে এই একটি ফাংশন কল করলেই
    সামঞ্জস্যপূর্ণ এরর রেসপন্স পাওয়া যাবে।

    Args:
        exc: ক্যাচ করা এক্সেপশন।
        status_code: HTTP স্ট্যাটাস কোড (যদি থাকে)।

    Returns:
        মানবপঠনযোগ্য এরর মেসেজ স্ট্রিং।
    """
    if status_code == 401:
        return "Error: Invalid API key. Check API key or token configuration."
    if status_code == 403:
        return "Error: Permission denied. Check token permissions for this resource."
    if status_code == 404:
        return "Error: Service not found. Verify the resource name or path."
    if status_code == 429:
        return "Error: Rate limit exceeded. Please wait before retrying."
    return f"Error: API request failed - {type(exc).__name__}"


async def safe_api_call(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    json_data: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    timeout: float | httpx.Timeout = DEFAULT_TIMEOUT,
) -> tuple[bool, dict[str, Any] | str]:
    """নিরাপদ API কল — এরর হ্যান্ডলিং সহ HTTP রিকোয়েস্ট পাঠায়।

    Args:
        method: HTTP মেথড ('GET', 'POST', ইত্যাদি)।
        url: টার্গেট URL।
        headers: HTTP হেডার।
        json_data: JSON বডি।
        params: কোয়েরি প্যারামিটার।
        timeout: টাইমআউট সেকেন্ডে।

    Returns:
        (success, data) টাপল। সফল হলে (True, response_dict),
        ���্যর্থ হলে (False, error_message_str)।
    """
    try:
        managed = get_shared_client()
        if managed is not None:
            response = await managed.request(
                method,
                url,
                headers=headers,
                json=json_data,
                params=params,
                timeout=timeout,
            )
        else:
            async with create_async_client(timeout=timeout) as fallback:
                response = await fallback.request(
                    method,
                    url,
                    headers=headers,
                    json=json_data,
                    params=params,
                )

        response.raise_for_status()
        return (True, response.json())
    except httpx.HTTPStatusError as e:
        error_msg = handle_api_error(e, e.response.status_code)
        logger.warning(f"HTTP error calling {url}: {error_msg}")
        return (False, error_msg)
    except Exception as e:
        error_msg = handle_api_error(e)
        logger.error(f"Request failed for {url}: {error_msg}")
        return (False, error_msg)
