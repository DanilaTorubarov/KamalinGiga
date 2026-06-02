from pydantic import BaseModel

class ChatPlace(BaseModel):
    name: str | None = None
    address: str | None = None
    category: str | None = None
    distance_label: str | None = None
