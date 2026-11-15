# proxy_manager.py
"""
Avtomatlashtirilgan Proksi va IP Rotatsiya Menejeri:
- SOCKS5 / HTTP proksilarni Telethon va Smart Glocal ga ulash.
- Har bir yangi avto-xarid oldidan IP ni majburiy yangilash (Session ID va Change IP URL orqali).
- Fonda har 1 daqiqada (yoki sozlangan vaqtda) IP manzilni avtomatik yangilash (Rotating Proxy).
"""

import asyncio
import logging
import re
import urllib.request
import urllib.error
import ssl
import socks
from urllib.parse import urlparse
import uuid

import database

logger = logging.getLogger(__name__)

_rotation_task = None
_current_ip = None
_current_session_id = uuid.uuid4().hex[:8]

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

def get_http_proxy_with_session() -> str:
    """
    HTTP/HTTPS so'rovlar (Smart Glocal va IP tekshirish) uchun
    sessiya bo'yicha ajratilgan proksi havolasini qaytaradi.
    """
    raw = get_proxy_string()
    if not raw:
        return None

    # Agar protocol bo'lmasa, http deb hisoblaymiz
    if not re.match(r'^[a-zA-Z0-9]+:\/\/', raw):
        raw = "http://" + raw

    parsed = urlparse(raw)
    host = parsed.hostname
    port = parsed.port or 823
    user = parsed.username
    pwd = parsed.password

    if not host:
        return None

    sess = _current_session_id or uuid.uuid4().hex[:8]
    if user:
        if "__session-" not in user:
            user_sess = f"{user}__session-{sess}"
        else:
            user_sess = user
        if pwd:
            return f"http://{user_sess}:{pwd}@{host}:{port}"
        return f"http://{user_sess}@{host}:{port}"
    return f"http://{host}:{port}"

def get_telethon_proxy():
    """Telethon TelegramClient uchun proksi sozlamasini qaytaradi"""
    if not is_proxy_enabled():
        return None
    raw = get_proxy_string()
    if not raw:
        return None
    try:
        if not re.match(r'^[a-zA-Z0-9]+:\/\/', raw):
            raw = "socks5://" + raw

        parsed = urlparse(raw)
        scheme = (parsed.scheme or "socks5").lower()
        p_type = socks.HTTP if "http" in scheme else socks.SOCKS5
        host = parsed.hostname
        port = parsed.port or (1080 if p_type != socks.HTTP else 8080)
        user = parsed.username
        password = parsed.password

        sess = _current_session_id or uuid.uuid4().hex[:8]
        if user and "__session-" not in user:
            user = f"{user}__session-{sess}"

        if not host:
            return None
        return (p_type, host, port, True, user, password)
    except Exception as e:
        logger.error(f"Proksi sozlamasini o'qishda xatolik: {e}")
        return None

def fetch_current_ip_sync() -> str:
    """Joriy tashqi IP manzilni aniqlaydi (proksi orqali yoki to'g'ridan-to'g'ri)"""
    ctx = ssl.create_default_context()
    if is_proxy_enabled():
        p_url = get_http_proxy_with_session()
        if p_url:
            opener = urllib.request.build_opener(
                urllib.request.ProxyHandler({'http': p_url, 'https': p_url}),
                urllib.request.HTTPSHandler(context=ctx)
            )
        else:
            opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx))
    else:
        opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx))

    req = urllib.request.Request("https://api.ipify.org", headers={"User-Agent": "Autonuberbot/1.0"})
    with opener.open(req, timeout=8) as resp:
        return resp.read().decode().strip()

async def get_current_ip() -> str:
    """Asinxron joriy IP manzilni olish"""
    global _current_ip
    try:
        loop = asyncio.get_running_loop()
        ip = await loop.run_in_executor(None, fetch_current_ip_sync)
        if ip:
            _current_ip = ip
        return _current_ip or "Noma'lum"
    except Exception as e:
        logger.warning(f"IP manzilni aniqlashda ogohlantirish: {e}")
        return _current_ip or "Noma'lum"

async def rotate_ip(reason: str = "avtomatik") -> str:
    """
    IP manzilni yangilaydi:
    1. Yangi session ID yaratadi (DataImpulse/Residential proksilar uchun yangi IP beradi).
    2. Agar Change IP (Rotatsiya) URL mavjud bo'lsa, uni chaqiradi (Mobil proksilar uchun).
    3. Yangilangan IP manzilni qaytaradi.
    """
    global _current_session_id, _current_ip
    _current_session_id = uuid.uuid4().hex[:8]

    rot_url = get_rotation_url()
    if rot_url:
        logger.info(f"🔄 Mobil proksi IP rotatsiya URL chaqirilmoqda ({reason})...")
        try:
            loop = asyncio.get_running_loop()
            def _fetch_rot():
                req = urllib.request.Request(rot_url, headers={"User-Agent": "Autonuberbot/1.0"})
                with urllib.request.urlopen(req, timeout=12) as resp:
                    return resp.read().decode('utf-8', errors='ignore')
            await loop.run_in_executor(None, _fetch_rot)
            await asyncio.sleep(4)
        except Exception as e:
            logger.warning(f"⚠️ IP rotatsiya havolasini chaqirishda ogohlantirish: {e}")

    # Yangi IP ni aniqlash
    new_ip = await get_current_ip()
    logger.info(f"🔄 IP yangilandi: {new_ip} ({reason}, session: {_current_session_id})")
    return new_ip

async def trigger_rotation_before_purchase() -> str:
    """Har bir yangi avto-xarid oldidan IP ni darhol yangilaydi va yangi IP qaytaradi"""
    if is_proxy_enabled():
        return await rotate_ip(reason="yangi premium buyurtmasi oldidan")
    else:
        return await get_current_ip()

async def _auto_rotation_loop():
    """Har 1 daqiqada (yoki sozlangan vaqtda) fonda aylanib turuvchi rotatsiya sikli"""
    logger.info("🌐 Proksi avtomatik IP rotatsiya foni ishga tushdi.")
    while True:
        try:
            interval = get_rotation_interval_seconds()
            await asyncio.sleep(interval)
            if is_proxy_enabled():
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
