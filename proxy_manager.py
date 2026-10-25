# proxy_manager.py
"""
Avtomatlashtirilgan Proksi va IP Rotatsiya Menejeri:
- SOCKS5 / HTTP proksilarni Telethon va Smart Glocal ga ulash.
- Har 1 daqiqada (yoki sozlangan vaqtda) IP manzilni avtomatik yangilash (Rotating Proxy).
- Har bir yangi avto-xarid oldidan IP ni majburiy yangilash (Change IP URL orqali).
"""

import asyncio
import logging
import re
import urllib.request
import urllib.error
import socks
from urllib.parse import urlparse

import database

logger = logging.getLogger(__name__)

_rotation_task = None

def is_proxy_enabled() -> bool:
    return database.get_setting("proxy_enabled", "false").lower() in ("true", "1", "yes")

def get_proxy_string() -> str:
    return database.get_setting("proxy_url", "").strip()

def get_rotation_url() -> str:
    return database.get_setting("proxy_rotation_url", "").strip()

def get_rotation_interval_seconds() -> int:
    try:
        mins = float(database.get_setting("proxy_auto_rotate_minutes", "1"))
        return max(15, int(mins * 60))
    except Exception:
        return 60

def parse_proxy(proxy_str: str):
    """
    Proksi matnini (socks5://user:pass@host:port yoki host:port:user:pass)
    Telethon formatiga o'tkazadi: (socks.SOCKS5, host, port, rdns, username, password)
    """
    if not proxy_str:
        return None

    # Agar protocol bo'lmasa, socks5 deb taxmin qilamiz
    raw = proxy_str.strip()
    if not re.match(r'^[a-zA-Z0-9]+:\/\/', raw):
        # host:port:user:pass yoki host:port formati
        parts = raw.split(':')
        if len(parts) == 4:
            host, port, user, pwd = parts
            return (socks.SOCKS5, host, int(port), True, user, pwd)
        elif len(parts) == 2:
            host, port = parts
            return (socks.SOCKS5, host, int(port), True, None, None)
        raw = "socks5://" + raw

    parsed = urlparse(raw)
    scheme = (parsed.scheme or "socks5").lower()
    
    if "socks4" in scheme:
        p_type = socks.SOCKS4
    elif "http" in scheme:
        p_type = socks.HTTP
    else:
        p_type = socks.SOCKS5

    host = parsed.hostname
    port = parsed.port or (1080 if p_type != socks.HTTP else 8080)
    user = parsed.username
    password = parsed.password

    if not host:
        return None

    return (p_type, host, port, True, user, password)

def get_telethon_proxy():
    """Telethon TelegramClient uchun proksi sozlamasini qaytaradi"""
    if not is_proxy_enabled():
        return None
    p_str = get_proxy_string()
    if not p_str:
        return None
    try:
        return parse_proxy(p_str)
    except Exception as e:
        logger.error(f"Proksi sozlamasini o'qishda xatolik: {e}")
        return None

async def rotate_ip(reason: str = "avtomatik 1 daqiqalik davr") -> bool:
    """
    Mobil proksi provayderining Change IP (Rotatsiya) havolasini chaqirib,
    IP manzilni majburiy ravishda yangilaydi.
    """
    rot_url = get_rotation_url()
    if not rot_url:
        logger.debug("IP rotatsiya URL manzili kiritilmagan.")
        return False

    logger.info(f"🔄 IP manzil yangilanmoqda ({reason})... Havola: {rot_url[:35]}...")
    try:
        loop = asyncio.get_running_loop()
        def _fetch():
            req =urllib.request.Request(rot_url, headers={"User-Agent": "Autonuberbot/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.read().decode('utf-8', errors='ignore')

        res_text = await loop.run_in_executor(None, _fetch)
        logger.info(f"✅ IP muvaffaqiyatli yangilandi! Provayder javobi: {res_text[:120].strip()}")
        # Modem IP o'zgarishi va barqarorlashishi uchun 4 soniya kutish
        await asyncio.sleep(4)
        return True
    except Exception as e:
        logger.warning(f"⚠️ IP rotatsiya havolasini chaqirishda ogohlantirish: {e}")
        return False

async def trigger_rotation_before_purchase():
    """Har bir yangi avto-xarid oldidan IP ni darhol yangilaydi"""
    if is_proxy_enabled() and get_rotation_url():
        await rotate_ip(reason="yangi premium buyurtmasi oldidan")

async def _auto_rotation_loop():
    """Har 1 daqiqada (yoki sozlangan vaqtda) fonda aylanib turuvchi rotatsiya sikli"""
    logger.info("🌐 Proksi avtomatik IP rotatsiya foni ishga tushdi.")
    while True:
        try:
            interval = get_rotation_interval_seconds()
            await asyncio.sleep(interval)
            if is_proxy_enabled() and get_rotation_url():
                await rotate_ip(reason=f"har {interval} soniyalik davriy yangilanish")
        except asyncio.CancelledError:
            logger.info("Proksi rotatsiya foni to'xtatildi.")
            break
        except Exception as e:
            logger.error(f"Proksi avto-rotatsiya siklida xatolik: {e}")
            await asyncio.sleep(10)

def start_background_rotation():
    """Asosiy bot dasturi ishga tushganda fon vazifasini yoqadi"""
    global _rotation_task
    if _rotation_task is None or _rotation_task.done():
        _rotation_task = asyncio.create_task(_auto_rotation_loop())

