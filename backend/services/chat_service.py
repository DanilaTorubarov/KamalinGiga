from fastapi import HTTPException

from clients.gigachat_client import gigachat_request


def build_places_context(context):
    if not context:
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


async def gigachat_complete(messages):
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

