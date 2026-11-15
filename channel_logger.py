# channel_logger.py
"""
Telegram kanallari va guruhlariga Number va To'lov loglarini yuboruvchi xizmat.
"""
import logging
from aiogram import Bot
import config
import database

logger = logging.getLogger(__name__)

async def send_number_log(user_id: int, phone: str, diller_bot: str, mode: str = "Avto-Premium", user_display: str = None):
    ch = database.get_setting('channel_number_logs', '').strip()
    if not ch:
        return
    if not user_display:
        try:
            user = database.get_user(user_id)
            if user and user[1]:
                user_display = f"@{user[1]}"
            elif user and user[2]:
                user_display = user[2]
            else:
                user_display = str(user_id)
        except Exception:
            user_display = str(user_id)

    bot_name = diller_bot.replace('@', '')
    text = (
        f"📱 <b>Number olindi ({mode})</b>\n\n"
        f"👤 User: {user_display} (<code>{user_id}</code>)\n"
        f"📞 Number: <code>+{phone}</code>\n"
        f"🤖 Bot: @{bot_name}"
    )
    bot = Bot(token=config.BOT_TOKEN)
    try:
        target_chat = int(ch) if (ch.startswith('-') and ch[1:].isdigit()) or ch.isdigit() else ch
        await bot.send_message(chat_id=target_chat, text=text, parse_mode="HTML")
        logger.info(f"Kanal/guruhga ({ch}) number log muvaffaqiyatli yuborildi: +{phone}")
    except Exception as e:
        logger.error(f"Kanal/guruhga number log yuborishda xatolik ({ch}): {e}")
    finally:
        await bot.session.close()

async def send_payment_log(user_id: int, phone: str, reward_amount: str = "Telegram Premium (1 oy)", user_display: str = None):
    ch = database.get_setting('channel_payment_logs', '').strip()
    if not ch:
        return
    if not user_display:
        try:
            user = database.get_user(user_id)
            if user and user[1]:
                user_display = f"@{user[1]}"
            elif user and user[2]:
                user_display = user[2]
            else:
                user_display = str(user_id)
        except Exception:
            user_display = str(user_id)

    text = (
        f"✅ <b>Yangi Premium!</b>\n\n"
        f"👤 User: {user_display} (<code>{user_id}</code>)\n"
        f"📞 Number: <code>+{phone}</code>\n"
        f"💰 Mukofot: <b>{reward_amount}</b>"
    )
    bot = Bot(token=config.BOT_TOKEN)
    try:
        target_chat = int(ch) if (ch.startswith('-') and ch[1:].isdigit()) or ch.isdigit() else ch
        await bot.send_message(chat_id=target_chat, text=text, parse_mode="HTML")
        logger.info(f"Kanal/guruhga ({ch}) to'lov log muvaffaqiyatli yuborildi: +{phone}")
    except Exception as e:
        logger.error(f"Kanal/guruhga to'lov log yuborishda xatolik ({ch}): {e}")
    finally:
        await bot.session.close()
