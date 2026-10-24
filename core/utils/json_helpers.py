"""
JSON সিরিয়ালাইজেশন ইউটিলিটি — MCP টুল রেসপন্সে বারবার ব্যবহৃত
`json.dumps(..., ensure_ascii=False)` প্যাটার্ন সরলীকরণ।

MCP টুলগুলো সব সময় `json.dumps({"error": ...}, ensure_ascii=False)` বা
`json.dumps({"success": True, ...}, ensure_ascii=False)` লেখে। এই হেল্পার
ফাংশনগুলো সেই বয়লারপ্লেট দূর করে এবং সামঞ্জস্যপূর্ণ রেসপন্স ফরম্যাট নিশ্চিত করে।
"""

import json
from typing import Any


def json_response(data: dict[str, Any]) -> str:
    """ডিকশনারি থেকে JSON স্ট্রিং তৈরি করে (ensure_ascii=False সহ)।

    Args:
        data: সিরিয়ালাইজ করার ডিকশনারি।

    Returns:
        JSON স্ট্রিং (ইউনিকোড সংরক্ষিত)।
    """
    return json.dumps(data, ensure_ascii=False)


def json_error(message: str) -> str:
    """স্ট্যান্ডার্ড এরর JSON রেসপন্স তৈরি করে।

    Args:
        message: এরর মেসেজ।

    Returns:
        '{"error": "..."}' ফরম্যাটে JSON স্ট্রিং।
    """
    return json.dumps({"error": message}, ensure_ascii=False)


def json_success(message: str = "", **extra: Any) -> str:
    """স্ট্যান্ডার্ড সাফল্য JSON রেসপন্স তৈরি করে।

    Args:
        message: ঐচ্ছিক সাফল্যের মেসেজ।
        **extra: রেসপন্সে অতিরিক্ত কী-ভ্যালু পেয়ার।

    Returns:
        '{"success": true, ...}' ফরম্যাটে JSON স্ট্রিং।
    """
    data: dict[str, Any] = {"success": True}
    if message:
        data["message"] = message
    data.update(extra)
    return json.dumps(data, ensure_ascii=False)
