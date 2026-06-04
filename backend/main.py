import uvicorn
from fastapi import FastAPI
from core.cors import setup_cors
from api import geocode, places, chat, suggestions

app = FastAPI(title="Places API")

setup_cors(app)

app.include_router(geocode.router)
app.include_router(places.router)
app.include_router(chat.router)
app.include_router(suggestions.router)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)