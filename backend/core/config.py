import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent.parent / ".env")

DGIS_API_KEY = os.getenv("DGIS_API_KEY")
GIGACHAT_API = os.getenv("GIGACHAT_API")
GIGACHAT_SCOPE = os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")
