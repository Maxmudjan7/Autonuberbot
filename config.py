# config.py
import os
from pathlib import Path
from dotenv import load_dotenv

# .env faylidan sozlamalarni yuklash
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# Asosiy Telegram Bot sozlamalari
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# Telethon (Userbot) uchun Telegram API sozlamalari
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")

# Userbot sessiya fayli nomi
SESSION_NAME = os.getenv("SESSION_NAME", "userbot_session")
