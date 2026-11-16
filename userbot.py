import asyncio
import re
import logging
import telethon_patch
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
        return TelegramClient(StringSession(session_string), config.API_ID, config.API_HASH, receive_updates=False, connection_retries=5, auto_reconnect=True)
    return TelegramClient(session_name, config.API_ID, config.API_HASH, receive_updates=False, connection_retries=5, auto_reconnect=True)

async def get_working_client():
    """Raqam olish uchun faol userbot clientini qaytaradi (Bazadagi userbotlar ustuvor)"""
    # 1. Bazadagi faol userbotlarni tekshirish (Ustuvor)
    ub_record = database.get_active_userbot()
    if ub_record and ub_record[4]: # session_string
        ub_id = ub_record[0]
        if ub_id in active_clients:
            c_cached = active_clients[ub_id]
            if not c_cached.is_connected():
                try:
                    await c_cached.connect()
                except Exception:
                    pass
            if c_cached.is_connected():
                return c_cached, ub_id
        
        try:
            c = TelegramClient(StringSession(ub_record[4]), config.API_ID, config.API_HASH, receive_updates=False, connection_retries=5, auto_reconnect=True)
            await c.connect()
            if await c.is_user_authorized():
                active_clients[ub_id] = c
                return c, ub_id
        except Exception as e:
            logger.error(f"Userbot #{ub_id} sessiyasi yaroqsiz: {e}")

    # Agar get_active_userbot ulanmasa, bazadagi boshqa barcha faol userbotlarni tekshirish
    try:
        all_ubs = database.get_all_userbots()
        for ub in all_ubs:
            ub_id, name, phone, tg_id, status, holat, active_nums, session_str = ub
            if status == 'active' and session_str:
                if ub_id in active_clients:
                    c_cached = active_clients[ub_id]
                    if not c_cached.is_connected():
                        try:
                            await c_cached.connect()
                        except Exception:
                            pass
                    if c_cached.is_connected():
                        return c_cached, ub_id
                try:
                    c = TelegramClient(StringSession(session_str), config.API_ID, config.API_HASH, receive_updates=False, connection_retries=5, auto_reconnect=True)
                    await c.connect()
                    if await c.is_user_authorized():
                        active_clients[ub_id] = c
                        return c, ub_id
                except Exception as e:
                    logger.warning(f"Userbot #{ub_id} ({name}) ulanmadi: {e}")
    except Exception as e:
        logger.error(f"Userbotlarni tekshirishda xatolik: {e}")

    # 2. Agar bazada birorta ham faol userbot bo'lmasa, faqat o'shanda diskdagi faylni tekshirish
    try:
        import os
        sess_file = f"{config.SESSION_NAME}.session"
        if os.path.exists(sess_file):
            if 'default' in active_clients and active_clients['default'].is_connected():
                return active_clients['default'], None
            c = TelegramClient(config.SESSION_NAME, config.API_ID, config.API_HASH, receive_updates=False, connection_retries=5, auto_reconnect=True)
            await c.connect()
            if await c.is_user_authorized():
                active_clients['default'] = c
                return c, None
    except Exception as e:
        logger.warning(f"Disk sessiya ulanmadi: {e}")

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
        if not c.is_connected():
            await c.connect()
        try:
            entity = await c.get_input_entity(diller_username)
        except (UsernameNotOccupiedError, UsernameInvalidError, ValueError):
            return None, None, "Raqam beruvchi xizmat topilmadi."

        sent_msg = await c.send_message(entity, command)

        for _ in range(35):
            await asyncio.sleep(0.4)
            messages = await c.get_messages(entity, limit=4)
            for msg in messages:
                if msg.id > sent_msg.id and msg.text:
                    m_txt_lower = msg.text.lower()

                    # 1. Eski buyurtma yopilgani yoki bekor qilingani haqidagi xabarlarni o'tkazib yuboramiz
                    if any(w in m_txt_lower for w in [
                        "order closed", "cancelled and returned", "number cancelled",
                        "frozen successfully", "number frozen", "bekor qilindi",
                        "muzlatildi", "notfound", "not found"
                    ]):
                        logger.info(f"Diller oldingi buyurtma statusi xabari o'tkazib yuborildi: {msg.text.strip()[:60]}")
                        continue

                    # 2. Diller bot ruxsat yo'q yoki boshqa sabab qaytarsa darhol xabar berish
                    if any(w in m_txt_lower for w in ["ruxsat yo'q", "ruxsat yo‘q", "admin:", "balans", "kelishuv"]):
                        logger.warning(f"Diller bot ({diller_username}) ogohlantirishi: {msg.text.strip()}")
                        return None, None, f"Diller bot ({diller_username}): {msg.text.strip()}"

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

        return None, None, "Hozirda bo'sh raqamlar mavjud emas."
    except Exception as e:
        logger.error(f"Diller botdan raqam olishda xatolik: {e}")
        return None, None, f"Xatolik: {str(e)}"

def extract_code_and_password(text: str, expected_phone: str = None):
    """Diller botidan kelgan xabardan Code va Parolni aniq ajratib olish"""
    if not text:
        return None, None
        
    # Telegram markdown belgilardan tozalash (`code`, **bold**, va h.k.)
    clean_text = text.replace('`', '').replace('*', '')

    # Agar expected_phone berilgan bo'lsa va xabarda boshqa raqam bo'lsa, bu xabarni olmaymiz!
    if expected_phone:
        clean_exp = re.sub(r'\D', '', str(expected_phone))
        # Masalan: "Number: 905538768937"
        pm = re.search(r'(?:number|raqam)\s*[:=]?\s*(\+?\d{9,16})', clean_text, re.IGNORECASE)
        if pm:
            msg_phone = re.sub(r'\D', '', pm.group(1))
            if msg_phone and clean_exp not in msg_phone and msg_phone not in clean_exp:
                logger.warning(f"Xabar boshqa raqamga tegishli ({msg_phone} != {clean_exp}), o'tkazib yuborildi.")
                return None, None

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
            if any(w in line_clean for w in ['received', 'again', 'olish', 'kuting', 'waiting', 'not found', 'yo\'q', 'topilmadi']):
                continue
            # Telegram kodlari 5 xonali raqam bo'ladi (kamdan-kam 6 xonali)
            cm = re.search(r'(?:code|kod)\s*[:=]?\s*([0-9]{5,6})\b', line, re.IGNORECASE)
            if cm:
                val = cm.group(1).strip()
                if val not in ("2024", "2025", "2026", "2027", "2028"):
                    code = val
                    continue

    if not code:
        # Xabar matnidan raqamli kod qidirish (5-6 xonali)
        cm2 = re.search(r'(?:code|kod)\s*[:=]\s*([0-9]{5,6})\b', clean_text, re.IGNORECASE)
        if cm2:
            val2 = cm2.group(1).strip()
            if val2 not in ("2024", "2025", "2026", "2027", "2028"):
                code = val2

    if not password:
        pm2 = re.search(r'(?:pass(?:word)?|parol|2fa)\s*[:=]\s*([^\s\n\r]+)', clean_text, re.IGNORECASE)
        if pm2:
            password = re.sub(r'[^0-9a-zA-Z]', '', pm2.group(1).strip())

    # Qo'shimcha tekshiruv: Telegram kodi faqat 5 yoki 6 xonali raqam bo'lishi shart (yil sonlari emas)
    if code and (not code.isdigit() or len(code) not in (5, 6) or code in ("2024", "2025", "2026", "2027", "2028")):
        code = None

    return code, password

async def click_diller_button(diller_username: str, diller_msg_id: int, button_action: str, expected_phone: str = None):
    """Diller botidagi tugmani bosish (Get Code, Freeze, Cancel)"""
    c, _ = await get_working_client()
    if not c:
        return False, "Userbot ulanmagan!"

    try:
        if not c.is_connected():
            await c.connect()
        entity = await c.get_input_entity(diller_username)
        msg = await c.get_messages(entity, ids=diller_msg_id)
        if not msg:
            # Agar id bo'yicha topilmasa, oxirgi xabarlardan qidiramiz
            recent = await c.get_messages(entity, limit=3)
            for rm in recent:
                if rm.buttons:
                    msg = rm
                    break
            if not msg:
                return False, "Diller botdagi xabar topilmadi!"

        # Agar Get Code so'ralgan bo'lsa va xabarda allaqachon kod mavjud bo'lsa
        if "code" in button_action.lower():
            c_now, p_now = extract_code_and_password(msg.text, expected_phone=expected_phone)
            if c_now:
                return True, (c_now, p_now)

        clicked = False
        action_map = {
            "code": ["code", "kod", "получить", "again", "qayta"],
            "freeze": ["freeze", "muzlat"],
            "cancel": ["cancel", "bekor", "отмен"]
        }
        target_kws = action_map.get(button_action.lower(), [button_action.lower()])

        # Tugmani bosish (msg yoki oxirgi xabarlar ichidan)
        candidate_msgs = [msg]
        try:
            more_msgs = await c.get_messages(entity, limit=3)
            for mm in more_msgs:
                if mm.id != msg.id and mm.buttons:
                    candidate_msgs.append(mm)
        except Exception:
            pass

        target_btn_msg = msg
        for cmsg in candidate_msgs:
            if cmsg.buttons:
                for row in cmsg.buttons:
                    for btn in row:
                        btn_text = btn.text.lower()
                        if any(kw in btn_text for kw in target_kws):
                            logger.info(f"Diller botida '{btn.text}' tugmasi bosilmoqda (msg #{cmsg.id})...")
                            await btn.click()
                            clicked = True
                            target_btn_msg = cmsg
                            break
                    if clicked:
                        break
            if clicked:
                break

        if not clicked and "code" not in button_action.lower():
            return False, f"Diller botida '{button_action}' tugmasi topilmadi."

        # Agar bu "Get Code" bo'lsa: kod kelguniga qadar kutamiz va "Get code again" tugmasini bosib turamiz
        if "code" in button_action.lower():
            target_msg_id = target_btn_msg.id
            for attempt in range(25):  # 25 * 1.5s = ~37 soniya kutamiz (FloodWait bo'lmaydi)
                await asyncio.sleep(1.5)
                if not c.is_connected():
                    try:
                        await c.connect()
                    except Exception:
                        pass

                # 1. Asosiy diller xabarini tekshirish
                updated_msg = await c.get_messages(entity, ids=target_msg_id)
                if updated_msg and updated_msg.text:
                    code, password = extract_code_and_password(updated_msg.text, expected_phone=expected_phone)
                    if code:
                        logger.info(f"Diller xabaridan (#{target_msg_id}) kod olindi: {code}")
                        return True, (code, password)

                # 2. Yangi kelgan xabarlarni tekshirish (diller_msg_id dan keyingi xabarlar)
                new_msgs = await c.get_messages(entity, limit=3)
                for m in new_msgs:
                    if not m or not m.text:
                        continue
                    code, password = extract_code_and_password(m.text, expected_phone=expected_phone)
                    if code:
                        logger.info(f"Diller yangi xabaridan (#{m.id}) kod olindi: {code}")
                        return True, (code, password)

                # 3. Agar kod hali chiqmagan bo'lsa, "Get code again" / "Qayta kod olish" tugmasini qayta bosamiz!
                poll_msg = updated_msg or (new_msgs[0] if new_msgs else None)
                if poll_msg and poll_msg.buttons:
                    for row in poll_msg.buttons:
                        btn_clicked = False
                        for btn in row:
                            b_text = btn.text.lower()
                            if any(k in b_text for k in ["again", "qayta", "code", "kod"]):
                                try:
                                    logger.info(f"Diller botida kodni qayta so'rash tugmasi bosilmoqda: '{btn.text}' (attempt {attempt+1})")
                                    await btn.click()
                                    target_msg_id = poll_msg.id
                                    btn_clicked = True
                                    break
                                except Exception as e_click:
                                    logger.warning(f"Qayta kod tugmasini bosishda ogohlantirish: {e_click}")
                        if btn_clicked:
                            break

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
        for _ in range(16):
            await asyncio.sleep(0.4)
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
