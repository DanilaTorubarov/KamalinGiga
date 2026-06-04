import ssl
import certifi
import httpx
from fastapi import HTTPException
from pathlib import Path

from core.config import GIGACHAT_API_KEY, GIGACHAT_SCOPE


CERT_PATH = Path(__file__).parent.parent / "certs" / "russian_trusted_root_ca.pem"

ssl_context = ssl.create_default_context(cafile=certifi.where())
ssl_context.load_verify_locations(cafile=str(CERT_PATH))

GIGACHAT_OAUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
GIGACHAT_CHAT_URL = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"

GIGACHAT_REQUEST_TOKEN = None


async def gigachat_update_request_token():
    print("=========== Запрос на обновление токена")
    global GIGACHAT_REQUEST_TOKEN
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': 'application/json',
        'RqUID': '0031ce0b-2850-4ca4-b14c-65a457c458df',
        'Authorization': f'Basic {GIGACHAT_API_KEY}'
    }

    async with httpx.AsyncClient(timeout=30, verify=ssl_context) as client:
        r = await client.post(
            GIGACHAT_OAUTH_URL,
            headers=headers,
            data={"scope": GIGACHAT_SCOPE},
        )
        if r.status_code != 200:
            raise HTTPException(503, "GIGACHAT_API is not configured. API_KEY is invalid" + str(r.text))
        GIGACHAT_REQUEST_TOKEN = r.json()["access_token"]
        print(GIGACHAT_REQUEST_TOKEN)


async def gigachat_request(messages, repeat: bool = True):
    if not GIGACHAT_API_KEY:
        raise HTTPException(503, "GIGACHAT_API is not configured. API_KEY is empty")

    if GIGACHAT_REQUEST_TOKEN is None:
        await gigachat_update_request_token()

    headers = {"Authorization": f"Bearer {GIGACHAT_REQUEST_TOKEN}"}
    payload = {"model": "GigaChat", "messages": messages}

    async with httpx.AsyncClient(timeout=30, headers=headers, verify=ssl_context) as client:
        r = await client.post(GIGACHAT_CHAT_URL, json=payload)

    if r.status_code != 200:
        if repeat:
            await gigachat_update_request_token()
            return await gigachat_request(messages, False)

        raise HTTPException(502, f"GigaChat error {r.status_code}")

    return r.json()