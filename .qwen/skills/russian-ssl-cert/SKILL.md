---
name: russian-ssl-cert
description: Fix SSL CERTIFICATE_VERIFY_FAILED errors for Russian APIs (GigaChat, Sberbank) by adding Russian Trusted Root CA to httpx SSL context
source: auto-skill
extracted_at: '2026-06-03T16:01:49.430Z'
---

# Handling SSL Errors with Russian API Services

## The problem

Russian government/banking APIs (GigaChat, Sberbank, etc.) use TLS certificates signed by the **Russian Trusted Root CA**, which is **not included** in Python's `certifi` bundle. This causes `httpx.ConnectError: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: self-signed certificate in certificate chain`.

## The fix: combine certifi + Russian CA in a custom SSL context

Do NOT use `verify=False` — it disables all SSL verification. Instead, create an SSL context that trusts both the standard Mozilla CA bundle (via `certifi`) AND the Russian Trusted Root CA:

```python
import ssl
import certifi
from pathlib import Path

CERT_PATH = Path(__file__).parent.parent / "certs" / "russian_trusted_root_ca.pem"

ssl_context = ssl.create_default_context(cafile=certifi.where())
ssl_context.load_verify_locations(cafile=str(CERT_PATH))
```

Then pass `verify=ssl_context` to **every** `httpx.AsyncClient` that calls Russian endpoints:

```python
async with httpx.AsyncClient(timeout=30, verify=ssl_context) as client:
    r = await client.post("https://ngw.devices.sberbank.ru:9443/api/v2/oauth")
```

## Certificate source

The Russian Trusted Root CA PEM file can be downloaded from:
`https://gu-st.ru/content/lending/russian_trusted_root_ca_pem.crt`

Save it at `backend/certs/russian_trusted_root_ca.pem` (or equivalent path in your project).

**Why:** The `.cer` URL (`russian_trusted_root_ca.cer`) returned 404 as of 2026-06-03 — use the `.crt`/PEM variant instead. Also, `certifi` is always available since it's a dependency of `httpx`.

## Common pitfalls

1. **Missing `global` keyword** — when updating a module-level variable (e.g. `GIGACHAT_REQUEST_TOKEN`) inside an async function, you MUST declare `global GIGACHAT_REQUEST_TOKEN`. Without it, Python creates a local variable and the module-level one stays unchanged, causing the token to never be cached and the auth function to run on every request.

2. **Wrong endpoint URL** — OAuth token endpoints and chat/completion endpoints are different URLs. Don't accidentally POST chat messages to the OAuth URL. For GigaChat:
   - Auth: `https://ngw.devices.sberbank.ru:9443/api/v2/oauth`
   - Chat: `https://gigachat.devices.sberbank.ru/api/v1/chat/completions`

## GigaChat OAuth request format (critical — not standard Bearer auth)

The OAuth token request is NOT a simple POST with `Authorization: Bearer <key>`. It requires:

```python
headers = {
    "Content-Type": "application/x-www-form-urlencoded",
    "Accept": "application/json",
    "RqUID": "<unique-uuid>",          # required by Sber
    "Authorization": f"Basic {GIGACHAT_API_KEY}",  # Basic auth, NOT Bearer!
}
data={"scope": GIGACHAT_SCOPE}  # must be form-urlencoded body, NOT JSON, NOT empty
```

Key differences from a naive implementation:
- **Basic** auth (not Bearer) — the API key is the ClientID:ClientSecret base64-encoded value provided by Sber
- **form-urlencoded** body with `scope` — httpx uses `data=` for this (NOT `json=`)
- **RqUID** header — a UUID string, required by the Sber API gateway
- Without these, you get 503 "GIGACHAT_API is not configured" even though the key is valid

## Chat completion request format

After obtaining the access_token via OAuth, the chat request uses **Bearer** auth:

```python
headers = {"Authorization": f"Bearer {GIGACHAT_REQUEST_TOKEN}"}
payload = {"model": "GigaChat", "messages": messages}  # NOT {"scope": ...}
```

The chat endpoint is `https://gigachat.devices.sberbank.ru/api/v1/chat/completions` — a completely different host from the OAuth endpoint.

## GigaChat message structure requirements (critical — causes 502 if violated)

GigaChat enforces strict message format rules that differ from OpenAI's more lenient API. Violating any of these causes **502 Bad Gateway** from the chat endpoint:

1. **Only ONE `system` role message** — multiple system messages are rejected. If you have both a system prompt AND a places context, merge them into a single system message:
   ```python
   system_content = system_prompt + "\n\n" + places_context
   messages = [{"role": "system", "content": system_content}] + messages
   ```

2. **Alternating user/assistant roles** — consecutive messages with the same role are rejected. The API requires the pattern: `system → user → assistant → user → assistant → ...`. You must merge consecutive same-role messages:
   ```python
   def ensure_alternating_roles(messages):
       if not messages:
           return messages
       merged = [messages[0]]
       for msg in messages[1:]:
           if msg["role"] == merged[-1]["role"]:
               merged[-1]["content"] += "\n" + msg["content"]
           else:
               merged.append(msg)
       return merged
   ```

3. **Debugging tip** — when requests from a website/browser fail with 502 but the same endpoint works in Postman, compare the actual message arrays being sent. Log `messages` before the API call to spot structural violations (duplicate system messages, consecutive user messages, etc.). The difference is usually in the message structure, not the endpoint logic.

## System prompt storage pattern

For multi-line system prompts (which LLM chat APIs typically require), store them in a separate file (e.g., `prompts/system.md`) rather than `.env`. Reasons:
- `.env` is for key=value pairs — multi-line strings need awkward escaping
- `.md` files support natural multi-line text, easy to read and edit
- Changes to prompts don't require restarting the container (read at request time)

```python
SYSTEM_PROMPT_FILE = Path(__file__).parent.parent / "prompts" / "system.md"

def load_system_prompt() -> str:
    if SYSTEM_PROMPT_FILE.exists():
        return SYSTEM_PROMPT_FILE.read_text(encoding="utf-8").strip()
    return ""
```