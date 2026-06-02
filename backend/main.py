from fastapi import FastAPI
from core.cors import setup_cors
from api import geocode, places, chat

app = FastAPI(title="Places API")

setup_cors(app)

app.include_router(geocode.router)
app.include_router(places.router)
app.include_router(chat.router)
