from pathlib import Path

from fastapi import HTTPException

from clients.gigachat_client import gigachat_request
from models.chat import ChatContext

SYSTEM_PROMPT_FILE = Path(__file__).parent.parent / "prompts" / "system.md"

def _load_system_prompt() -> str:
    if SYSTEM_PROMPT_FILE.exists():
        return SYSTEM_PROMPT_FILE.read_text(encoding="utf-8").strip()
    return ""


def build_places_context(context: ChatContext | None) -> str:
    if not context or type(context) != ChatContext:
        return ""

    lines = []
    if context.address:
        lines.append(f"User address: {context.address}")

    if context.places:
        lines.append("Places:")
        for i, place in enumerate(context.places, start=1):
            parts = []
            if place.name:
                parts.append(place.name)
            if place.category:
                parts.append(place.category)
            if place.address:
                parts.append(place.address)
            if place.distance_label:
                parts.append(place.distance_label)

            if parts:
                lines.append(f"{i}. " + " - ".join(parts))

    return "\n".join(lines)


def _ensure_alternating_roles(messages):
    """GigaChat requires alternating user/assistant roles.
    Merge consecutive same-role messages into one."""
    if not messages:
        return messages
    merged = [messages[0]]
    for msg in messages[1:]:
        if msg["role"] == merged[-1]["role"]:
            merged[-1]["content"] += "\n" + msg["content"]
        else:
            merged.append(msg)
    return merged


async def gigachat_complete(messages, places_context: str = ""):
    system_prompt = _load_system_prompt()

    system_content = system_prompt
    if places_context:
        system_content += "\n\n" + places_context

    if system_content:
        messages = [{"role": "system", "content": system_content}] + messages

    messages = _ensure_alternating_roles(messages)
    print(messages)
    data = await gigachat_request(messages)

    reply = data.get("reply")
    if not reply:
        choices = data.get("choices") or []
        if choices:
            message = choices[0].get("message") or {}
            reply = message.get("content")

    if not reply:
        raise HTTPException(502, "Unexpected GigaChat response")

    return reply