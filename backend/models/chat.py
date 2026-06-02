from pydantic import BaseModel
from .places import ChatPlace

class HistoryMessage(BaseModel):
    role: str
    content: str

class ChatContext(BaseModel):
    address: str | None = None
    places: list[ChatPlace] = []

class ChatIn(BaseModel):
    message: str
    history: list[HistoryMessage] = []
    context: ChatContext | None = None

class ChatOut(BaseModel):
    reply: str
