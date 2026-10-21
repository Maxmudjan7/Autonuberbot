import asyncio
import re
import logging
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import (
    SessionPasswordNeededError,
    UsernameNotOccupiedError,
    UsernameInvalidError
)
import config
import database

logger = logging.getLogger(__name__)

# Faol mijozlar kesh (ub_id -> TelegramClient)
active_clients = {}

# Vaqtinchalik login qilish uchun sessiyalar (admin_id -> dict)
login_sessions = {}

def get_client_for_session(session_string: str = None, session_name: str = config.SESSION_NAME):
    if session_string:
        return TelegramClient(StringSession(session_string), config.API_ID, config.API_HASH)
    return TelegramClient(session_name, config.API_ID, config.API_HASH)

async def get_working_client():
    """Raqam olish uchun faol userbot clientini qaytaradi"""
    # 1. Diskdagi asosiy sessiya fayli (eng barqaror)
    if 'default' in active_clients and active_clients['default'].is_connected():
        return active_clients['default'], None

    try:
        c = TelegramClient(config.SESSION_NAME, config.API_ID, config.API_HASH)
        await c.connect()
        if await c.is_user_authorized():
            active_clients['default'] = c
            return c, None
    except Exception as e:
        logger.warning(f"Disk sessiya ulanmadi: {e}")

    # 2. Bazadagi aktiv userbotlarni tekshirish
    ub_record = database.get_active_userbot()
    if ub_record and ub_record[4]: # session_string
        ub_id = ub_record[0]
        if ub_id in active_clients and active_clients[ub_id].is_connected():
            return active_clients[ub_id], ub_id
        
        try:
            c = TelegramClient(StringSession(ub_record[4]), config.API_ID, config.API_HASH)
            await c.connect()
            if await c.is_user_authorized():
                active_clients[ub_id] = c
                return c, ub_id
        except Exception as e:
            logger.error(f"Userbot #{ub_id} sessiyasi yaroqsiz: {e}")

    return None, None

async def check_userbot_status():
    """Kamida bitta faol userbot bormi?"""
    try:
        c, _ = await get_working_client()
        return c is not None
    except Exception as e:
        logger.error(f"Userbot status xatosi: {e}")
        return False

# ==========================================
# BOT ICHIDAN LOGIN QILISH (TELEFON + KOD)
# ==========================================

async def start_phone_login(admin_id: int, phone: str):
    """Admin bot ichidan telefon raqam kiritganda kod so'rash"""
    client = TelegramClient(StringSession(), config.API_ID, config.API_HASH)
    await client.connect()
    
    try:
        code_request = await client.send_code_request(phone)
        login_sessions[admin_id] = {
            "client": client,
            "phone": phone,
            "phone_code_hash": code_request.phone_code_hash
        }
        return True, "Kod yuborildi"
    except Exception as e:
        await client.disconnect()
        return False, str(e)

async def complete_phone_login(admin_id: int, code: str, password: str = None):
    """Admin kod kiritganda kirishni yakunlash"""
    if admin_id not in login_sessions:
        return False, "Sessiya topilmadi! Qaytadan urinib ko'ring."

    session_data = login_sessions[admin_id]
    client = session_data["client"]
    phone = session_data["phone"]
    phone_code_hash = session_data["phone_code_hash"]

    try:
        if password:
            await client.sign_in(password=password)
        else:
            try:
                await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
            except SessionPasswordNeededError:
                return "2fa_required", "Ikki bosqichli parol (2FA) talab qilinadi."

        me = await client.get_me()
        session_str = client.session.save()
        name = me.first_name or phone
        tg_id = str(me.id)

        # Bazaga yangi userbot sifatida qo'shish
        ub_id = database.add_userbot_record(name, phone, tg_id, session_str)

        # Tozalash
        del login_sessions[admin_id]
        return True, f"✅ <b>{name}</b> (+{phone}) muvaffaqiyatli qo'shildi!"
    except Exception as e:
        return False, str(e)

# ==========================================
# DILLER BOT BILAN ISHLASH
# ==========================================

async def request_number_from_diller(diller_username: str, command: str = "/getNumber"):
    """Diller botidan yangi raqam so'rash"""
    if not diller_username:
        return None, None, "Diller boti belgilanmagan! Iltimos, /admin -> «🤖 Any botlar» orqali diller bot qo'shing."

    c, ub_id = await get_working_client()
    if not c:
        return None, None, "Faol Userbot hisobi topilmadi! Iltimos, «🤖 Userbotlar» bo'limidan akkaunt qo'shing."

    try:
        try:
            entity = await c.get_input_entity(diller_username)
        except (UsernameNotOccupiedError, UsernameInvalidError, ValueError):
            return None, None, f"«{diller_username}» nomli Telegram bot topilmadi! Diller bot username to'g'riligini tekshiring."

        sent_msg = await c.send_message(entity, command)

        for _ in range(20):
            await asyncio.sleep(1)
            messages = await c.get_messages(entity, limit=4)
            for msg in messages:
                if msg.id > sent_msg.id and msg.text:
                    lines = msg.text.split("\n")
                    phone = None
                    for line in lines:
                        match = re.search(r'(\+?\d{9,16})', line)
                        if match and not any(w in line.lower() for w in ['vaqt', 'qolgan', 'narxi', 'daqiqa']):
                            phone = match.group(1).replace("+", "").strip()
                            break

                    if phone:
                        return phone, msg.id, None

                    match_all = re.search(r'(?:number|raqam|your number)?[:\s]*(\+?\d{9,16})', msg.text, re.IGNORECASE)
                    if match_all:
                        phone = match_all.group(1).replace("+", "").strip()
                        return phone, msg.id, None

        return None, None, f"«{diller_username}» botidan raqam kelmadi yoki diller javob bermadi."
    except Exception as e:
        logger.error(f"Diller botdan raqam olishda xatolik: {e}")
        return None, None, f"Xatolik: {str(e)}"

def extract_code_and_password(text: str):
    """Diller botidan kelgan xabardan Code va Parolni aniq ajratib olish"""
    if not text:
        return None, None
        
    # Telegram markdown belgilardan tozalash (`code`, **bold**, va h.k.)
    clean_text = text.replace('`', '').replace('*', '')
    code, password = None, None
    lines = [line.strip() for line in clean_text.splitlines() if line.strip()]
    
    for line in lines:
        line_clean = line.lower()
        # Parol / Pass qidirish (masalan: 🔑 Pass: 3147067 yoki Parol: ...)
        if any(p in line_clean for p in ['pass', 'parol', '2fa']):
            pm = re.search(r'(?:pass(?:word)?|parol|2fa)\s*[:=]\s*([^\s\n\r]+)', line, re.IGNORECASE)
            if pm:
                password = re.sub(r'[^0-9a-zA-Z]', '', pm.group(1).strip())
                continue
                
        # Kod / Code qidirish (masalan: 🔒 Code: 92901 yoki Kod: 92901)
        if any(c in line_clean for c in ['code', 'kod']):
            if any(w in line_clean for w in ['received', 'again', 'olish', 'kuting', 'waiting']):
                continue
            cm = re.search(r'(?:code|kod)\s*[:=]?\s*([0-9a-zA-Z\s-]+)', line, re.IGNORECASE)
            if cm:
                raw_c = cm.group(1).strip()
                digits = re.sub(r'[^0-9a-zA-Z]', '', raw_c)
                if len(digits) >= 4:
                    code = digits
                    continue

    if not code:
        cm2 = re.search(r'(?:code|kod)\s*[:=]\s*([0-9]{4,8})', clean_text, re.IGNORECASE)
        if cm2:
            code = cm2.group(1).strip()

    if not password:
        pm2 = re.search(r'(?:pass(?:word)?|parol|2fa)\s*[:=]\s*([^\s\n\r]+)', clean_text, re.IGNORECASE)
        if pm2:
            password = re.sub(r'[^0-9a-zA-Z]', '', pm2.group(1).strip())

    return code, password

async def click_diller_button(diller_username: str, diller_msg_id: int, button_action: str):
    """Diller botidagi tugmani bosish (Get Code, Freeze, Cancel)"""
    c, _ = await get_working_client()
    if not c:
        return False, "Userbot ulanmagan!"

    try:
        entity = await c.get_input_entity(diller_username)
        msg = await c.get_messages(entity, ids=diller_msg_id)
        if not msg:
            return False, "Diller botdagi xabar topilmadi!"

        # Agar Get Code so'ralgan bo'lsa va xabarda allaqachon kod mavjud bo'lsa
        if "code" in button_action.lower():
            c_now, p_now = extract_code_and_password(msg.text)
            if c_now:
                return True, (c_now, p_now)

        clicked = False
        if msg.buttons:
            for row in msg.buttons:
                for btn in row:
                    if button_action.lower() in btn.text.lower():
                        await btn.click()
                        clicked = True
                        break
                if clicked:
                    break

        if not clicked:
            action_map = {
                "code": "code",
                "freeze": "freeze",
                "cancel": "cancel"
            }
            target_kw = action_map.get(button_action.lower(), button_action.lower())
            if msg.buttons:
                for row in msg.buttons:
                    for btn in row:
                        if target_kw in btn.text.lower():
                            await btn.click()
                            clicked = True
                            break
                    if clicked:
                        break

        if not clicked and "code" not in button_action.lower():
            return False, f"Diller botida '{button_action}' tugmasi topilmadi."

        if "code" in button_action.lower():
            for _ in range(25):
                await asyncio.sleep(1)
                updated_msg = await c.get_messages(entity, ids=diller_msg_id)
                new_msgs = await c.get_messages(entity, limit=4)
                all_msgs = ([updated_msg] if updated_msg else []) + [m for m in new_msgs if m]
                for m in all_msgs:
                    if not m or not m.text:
                        continue
                    code, password = extract_code_and_password(m.text)
                    if code:
                        return True, (code, password)

            return False, "Diller botidan kod kelmadi. Iltimos, «🔄 Qayta kod olish» tugmasini bosing."

        return True, "Bajarildi"
    except Exception as e:
        logger.error(f"Diller tugmasini bosishda xatolik: {e}")
        return False, str(e)

async def check_premium_from_diller(diller_username: str, diller_msg_id: int):
    """Diller botida 'Check premium' tugmasini bosib, premium haqiqatdan ham faollashganini tekshirish"""
    c, _ = await get_working_client()
    if not c:
        return False, "Userbot ulanmagan!"

    try:
        entity = await c.get_input_entity(diller_username)
        msg = await c.get_messages(entity, ids=diller_msg_id)
        if not msg:
            recent = await c.get_messages(entity, limit=3)
            for rm in recent:
                if rm.buttons:
                    msg = rm
                    break
            if not msg:
                return False, "Diller botdagi xabar topilmadi!"

        clicked = False
        if msg.buttons:
            for row in msg.buttons:
                for btn in row:
                    if "check" in btn.text.lower():
                        await btn.click()
                        clicked = True
                        break
                if clicked:
                    break

        if not clicked:
            return False, "Diller botida «Check premium» tugmasi topilmadi."

        # Diller boti javobini kutamiz (xabar matni o'zgarishi yoki yangi xabar)
        for _ in range(8):
            await asyncio.sleep(1)
            updated_msg = await c.get_messages(entity, ids=msg.id)
            new_msgs = await c.get_messages(entity, limit=3)
            all_msgs = ([updated_msg] if updated_msg else []) + [m for m in new_msgs if m]

            for m in all_msgs:
                if not m or not m.text:
                    continue
                txt = m.text.lower()
                # Agar hali premium emasligi aytilsa:
                if "not premium" in txt or "hali premium emas" in txt or "premium emas" in txt:
                    return False, "Ushbu raqamda hali Telegram Premium faollashtirilmagan!"
                # Agar muvaffaqiyatli bo'lsa:
                if "is premium" in txt or "premium active" in txt or "muvaffaqiyatli" in txt or ("✅" in m.text and "premium" in txt):
                    return True, "Premium muvaffaqiyatli tasdiqlandi!"

        if updated_msg and updated_msg.text:
            if "not premium" in updated_msg.text.lower():
                return False, "Ushbu raqamda hali Telegram Premium faollashtirilmagan!"

        return False, "Diller botidan tasdiq kelmadi. Iltimos, qaytadan tekshirib ko'ring."
    except Exception as e:
        logger.error(f"Check premium xatolik: {e}")
        return False, str(e)
