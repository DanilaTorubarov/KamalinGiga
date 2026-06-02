import httpx
from fastapi import HTTPException
from urllib.parse import urlparse

from core.config import GIGACHAT_API, GIGACHAT_SCOPE

def _validate_gigachat_url(value):
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise HTTPException(503, "GIGACHAT_API must be a full http(s) URL")
    return value

async def gigachat_request(messages):
    if not GIGACHAT_API:
        raise HTTPException(503, "GIGACHAT_API is not configured")

    url = _validate_gigachat_url(GIGACHAT_API)

    payload = {"messages": messages, "scope": GIGACHAT_SCOPE}

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(url, json=payload)

    if r.status_code != 200:
        raise HTTPException(502, f"GigaChat error {r.status_code}")

    return r.json()
