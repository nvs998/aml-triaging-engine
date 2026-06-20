import os

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AQ.Ab8RN6LxQjsalas52vBlkiatUOsdGDKcL0o3Fwmz6yp6Qzh7mA")
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))
