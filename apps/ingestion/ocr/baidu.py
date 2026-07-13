# coding=utf-8
"""
Baidu OCR integration for scanned PDF text extraction.
Uses Baidu's general text recognition API.
"""
import base64
import json
import logging
import time

import requests

from maxkb.const import CONFIG

logger = logging.getLogger("maxkb.ocr")

# Baidu OCR endpoints
BAIDU_TOKEN_URL = "https://aip.baidubce.com/oauth/2.0/token"
BAIDU_OCR_URL = "https://aip.baidubce.com/rest/2.0/ocr/v1/general_basic"

_token_cache = {"token": None, "expires_at": 0}


def _get_access_token() -> str:
    """Get or refresh Baidu OCR access token (cached for 25 days)."""
    now = time.time()
    if _token_cache["token"] and now < _token_cache["expires_at"]:
        return _token_cache["token"]

    api_key = CONFIG.get("BAIDU_OCR_API_KEY")
    secret_key = CONFIG.get("BAIDU_OCR_SECRET_KEY")

    if not api_key or not secret_key:
        raise ValueError("BAIDU_OCR_API_KEY or BAIDU_OCR_SECRET_KEY not configured")

    resp = requests.post(
        BAIDU_TOKEN_URL,
        data={"grant_type": "client_credentials", "client_id": api_key, "client_secret": secret_key},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()

    _token_cache["token"] = data["access_token"]
    _token_cache["expires_at"] = now + data.get("expires_in", 2592000) - 3600  # 30 days - 1 hour
    return _token_cache["token"]


def ocr_image(image_bytes: bytes) -> str:
    """OCR a single image using Baidu OCR.

    Args:
        image_bytes: PNG/JPG image binary data.

    Returns:
        Extracted text, or empty string on failure.
    """
    token = _get_access_token()

    # Baidu OCR accepts base64-encoded images up to 4MB
    img_base64 = base64.b64encode(image_bytes).decode("utf-8")

    resp = requests.post(
        f"{BAIDU_OCR_URL}?access_token={token}",
        data={"image": img_base64},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    if "error_code" in data:
        logger.error(f"Baidu OCR error: {data.get('error_msg', 'unknown')}")
        return ""

    words = [item["words"] for item in data.get("words_result", [])]
    return "\n".join(words)


def ocr_pdf_page(pdf_page_image_bytes: bytes) -> str:
    """OCR a single PDF page (already converted to image).

    Args:
        pdf_page_image_bytes: Single PDF page as PNG image bytes.

    Returns:
        Extracted text.
    """
    try:
        return ocr_image(pdf_page_image_bytes)
    except Exception as e:
        logger.warning(f"OCR failed for PDF page: {e}")
        return ""


def is_ocr_needed(text: str) -> bool:
    """Check if OCR is needed based on extracted text quality.

    Returns True if the text is likely from a scanned/image PDF
    (very little text extracted, or full of image placeholders).
    """
    if not text or len(text.strip()) < 50:
        return True
    # Check for image placeholders like ![image](image_0_0)
    if text.count("![image]") > len(text) / 100:
        return True
    return False
