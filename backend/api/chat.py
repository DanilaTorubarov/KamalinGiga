from fastapi import APIRouter
from models.chat import ChatIn, ChatOut
from services.chat_service import build_places_context, gigachat_complete

router = APIRouter(prefix="/api")

@router.post("/chat", response_model=ChatOut)
async def api_chat(body: ChatIn):
    messages = []

    for h in body.history:
        if h.role in ("user", "assistant"):
            messages.append({"role": h.role, "content": h.content})

    messages.append({"role": "user", "content": body.message})

    ctx = build_places_context(body.context)
    reply = await gigachat_complete(messages, ctx)
    return ChatOut(reply=reply)
