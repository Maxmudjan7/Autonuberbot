# crypto_utils.py
"""
Bank darajasidagi ma'lumotlarni shifrlash (AES-256 Fernet) vositasi.
Foydalanuvchi kartalari (karta raqami va CVV) bazada shifrlangan holatda saqlanadi.
"""

import os
import logging
from pathlib import Path
from cryptography.fernet import Fernet
from dotenv import set_key

import config

logger = logging.getLogger(__name__)

ENV_FILE = config.BASE_DIR / ".env"

def _get_or_create_key() -> bytes:
    key_str = os.getenv("ENCRYPTION_KEY", "").strip()
    if not key_str:
        new_key = Fernet.generate_key()
        key_str = new_key.decode("utf-8")
        try:
            set_key(str(ENV_FILE), "ENCRYPTION_KEY", key_str)
            os.environ["ENCRYPTION_KEY"] = key_str
            logger.info("🔐 Yangi AES-256 shifrlash kaliti yaratildi va .env fayliga saqlandi.")
        except Exception as e:
            logger.warning(f".env ga ENCRYPTION_KEY saqlashda ogohlantirish: {e}")
    return key_str.encode("utf-8")

_FERNET_KEY = _get_or_create_key()
_FERNET = Fernet(_FERNET_KEY)

def encrypt_data(plain_text: str) -> str:
    """Ochiq matnni (karta raqami, CVV) AES-256 bilan shifrlaydi"""
    if not plain_text:
        return ""
    try:
        token = _FERNET.encrypt(str(plain_text).encode("utf-8"))
        return token.decode("utf-8")
    except Exception as e:
        logger.error(f"Shifrlash xatosi: {e}")
        return plain_text

def decrypt_data(cipher_text: str) -> str:
    """Shifrlangan matnni ochadi. Agar shifrlanmagan eski ma'lumot bo'lsa, o'zini qaytaradi"""
    if not cipher_text:
        return ""
    # Fernet tokenlari har doim 'gAAAAA' bilan boshlanadi
    if not str(cipher_text).startswith("gAAAAA"):
        return str(cipher_text)
    try:
        decrypted = _FERNET.decrypt(str(cipher_text).encode("utf-8"))
        return decrypted.decode("utf-8")
    except Exception as e:
        logger.error(f"Deshifrlash xatosi: {e}")
        return cipher_text

