# bestbit_service.py
"""
BestBitBot avtomatlashtirish xizmati:
1. Yangi Telegram Premium olingan akkaunt nomidan:
   - Saved Messages ga 'https://t.me/BestBitBot?start=U6278841173' yuboradi
   - @BestBitBot ga referal kod bilan /start yuboradi
2. Bonus spin bo'limiga kirib slotni aylantiradi:
   - 'Бонус спин' -> 'Крутить' -> 'Забрать спин' -> 'Крутить'
3. Qaytadan /start yuborib chek yaratadi:
   - '/start' -> 'Чеки' -> 'Создать чек' -> 'Макс.' -> 'Макс. активаций'
4. Yaratilgan chek havolasini oladi:
   - 'Копировать' yoki xabar matnidan havola ajratib olinadi
5. Chekni https://t.me/meningtolovlarim kanaliga va admin lichkasiga yuboradi.
"""

import asyncio
import logging
import re
from telethon import TelegramClient
from aiogram import Bot

import config
import database

logger = logging.getLogger(__name__)

async def click_button_with_text(client: TelegramClient, entity, pattern_texts: list, max_wait: int = 7, sleep_between: float = 1.2):
    """
    Bot xabarlaridagi inline tugmalardan matn bo'yicha qidirib bosadi.
    """
    for _ in range(max_wait):
        await asyncio.sleep(sleep_between)
        try:
            msgs = await client.get_messages(entity, limit=4)
            for m in msgs:
                if m.buttons:
                    for row in m.buttons:
                        for btn in row:
                            text = getattr(btn, 'text', '') or ''
                            for pat in pattern_texts:
                                if pat.lower() in text.lower():
                                    logger.info(f"Tugma topildi: '{text}' (mos pattern: '{pat}'). Bosilmoqda...")
                                    try:
                                        await btn.click()
                                        return True, m
                                    except Exception as click_err:
                                        logger.warning(f"Tugma bosishda ogohlantirish: {click_err}")
                                        return True, m
        except Exception as e:
            logger.warning(f"Tugma qidirishda xatolik: {e}")
    return False, None

async def run_bestbit_flow(client: TelegramClient, phone: str) -> dict:
    """
    BestBitBot to'liq siklini bajaradi.
    Qaytaradi: {"success": bool, "check_link": str | None, "error": str | None}
    """
    ref_link = database.get_setting("bestbit_ref_link", "https://t.me/BestBitBot?start=U6278841173").strip()
    if not ref_link:
        ref_link = "https://t.me/BestBitBot?start=U6278841173"

    target_channel = database.get_setting("bestbit_target_channel", "@meningtolovlarim").strip()
    if not target_channel:
        target_channel = "@meningtolovlarim"

    # Referal kod va bot username ni ajratib olish
    ref_code = "U6278841173"
    if "start=" in ref_link:
        ref_code = ref_link.split("start=")[-1].split("&")[0].strip()

    bot_username = "BestBitBot"
    if "t.me/" in ref_link:
        bot_username = ref_link.split("t.me/")[-1].split("?")[0].strip()

    logger.info(f"[{phone}] BestBit sikli boshlandi: bot=@{bot_username}, ref_code={ref_code}")

    try:
        # 1. Saved Messages ga referal havola yuborish
        try:
            await client.send_message('me', ref_link)
            logger.info(f"[{phone}] Saved Messages ga referal havola tashlandi: {ref_link}")
        except Exception as e:
            logger.warning(f"[{phone}] Saved Messages ga tashlashda ogohlantirish: {e}")

        # 2. @BestBitBot ga referal kod bilan /start yuborish
        bot_entity = await client.get_input_entity(bot_username)
        await client.send_message(bot_entity, f"/start {ref_code}")
        logger.info(f"[{phone}] @{bot_username} ga /start {ref_code} yuborildi.")
        await asyncio.sleep(2.5)

        # 3. 'Бонус спин' tugmasini bosish
        spin_btn_clicked, _ = await click_button_with_text(client, bot_entity, ["Бонус спин", "бонус"])
        if not spin_btn_clicked:
            logger.warning(f"[{phone}] 'Бонус спин' tugmasi topilmadi yoki bosilmadi!")

        await asyncio.sleep(2.5)

        # 4. 'Крутить' tugmasini bosish
        krutit_clicked, _ = await click_button_with_text(client, bot_entity, ["Крутить"])
        if krutit_clicked:
            logger.info(f"[{phone}] 1-marta slot aylantirilmoqda, 4 soniya kutilmoqda...")
            await asyncio.sleep(4.5)
        else:
            logger.warning(f"[{phone}] 'Крутить' tugmasi topilmadi!")

        # 5. 'Забрать спин' tugmasini bosish
        zabrat_clicked, _ = await click_button_with_text(client, bot_entity, ["Забрать спин", "Забрать"])
        if zabrat_clicked:
            logger.info(f"[{phone}] 'Забрать спин' bosildi.")
            await asyncio.sleep(2.0)

        # 6. Yana 'Крутить' tugmasini bosish
        krutit2_clicked, _ = await click_button_with_text(client, bot_entity, ["Крутить"])
        if krutit2_clicked:
            logger.info(f"[{phone}] 2-marta slot aylantirilmoqda, 4 soniya kutilmoqda...")
            await asyncio.sleep(4.5)

        # 7. Qaytadan /start yuborish
        await client.send_message(bot_entity, "/start")
        logger.info(f"[{phone}] Menyuga qaytish uchun /start yuborildi.")
        await asyncio.sleep(2.5)

        # 8. 'Чеки' tugmasini bosish
        cheki_clicked, _ = await click_button_with_text(client, bot_entity, ["Чеки"])
        if not cheki_clicked:
            logger.warning(f"[{phone}] 'Чеки' tugmasi topilmadi!")
        await asyncio.sleep(2.0)

        # 9. 'Создать чек' tugmasini bosish
        create_chk_clicked, _ = await click_button_with_text(client, bot_entity, ["Создать чек"])
        if not create_chk_clicked:
            logger.warning(f"[{phone}] 'Создать чек' tugmasi topilmadi!")
        await asyncio.sleep(2.0)

        # 10. Summa tanlashda 'Макс.' tugmasini bosish
        max_sum_clicked, _ = await click_button_with_text(client, bot_entity, ["Макс.", "Макс"])
        if not max_sum_clicked:
            logger.warning(f"[{phone}] 'Макс.' summa tugmasi topilmadi!")
        await asyncio.sleep(2.0)

        # 11. Aktivatsiyalar sonida 'Макс. активаций' tugmasini bosish
        max_act_clicked, _ = await click_button_with_text(client, bot_entity, ["Макс. активаций", "Макс"])
        if not max_act_clicked:
            logger.warning(f"[{phone}] 'Макс. активаций' tugmasi topilmadi!")
        await asyncio.sleep(3.0)

        # 12. 'Копировать' tugmasini bosib ko'rish va chek havolasini qidirish
        await click_button_with_text(client, bot_entity, ["Копировать", "копировать"], max_wait=2)

        check_link = None
        msgs = await client.get_messages(bot_entity, limit=4)
        for m in msgs:
            full_txt = m.text or ""
            # Xabar matnidagi havolalarni qidirish
            found_links = re.findall(r'(https?://t\.me/(?:' + re.escape(bot_username) + r')[^\s\n]+)', full_txt, re.IGNORECASE)
            for lk in found_links:
                # Referal havolasidan boshqa yangi chek havolasini olish
                if ref_code not in lk:
                    check_link = lk
                    break
            if check_link:
                break

            # Tugmalardan qidirish
            if m.buttons:
                for row in m.buttons:
                    for btn in row:
                        if hasattr(btn, 'copy_text') and getattr(btn.copy_text, 'text', None):
                            cp_t = btn.copy_text.text
                            if "t.me/" in cp_t and ref_code not in cp_t:
                                check_link = cp_t
                                break
                        if getattr(btn, 'url', None) and "t.me/" in btn.url and ref_code not in btn.url:
                            check_link = btn.url
                            break
            if check_link:
                break

            # Entities dan qidirish
            if getattr(m, 'entities', None):
                for ent in m.entities:
                    if hasattr(ent, 'url') and ent.url and 't.me/' in ent.url and ref_code not in ent.url:
                        check_link = ent.url
                        break
            if check_link:
                break

        if not check_link:
            logger.warning(f"[{phone}] Chek havolasi topilmadi. Oxirgi xabar: {[m.text for m in msgs if m.text]}")
            return {"success": False, "check_link": None, "error": "Chek havolasi topilmadi"}

        logger.info(f"[{phone}] 🎉 BestBit chek havolasi muvaffaqiyatli olingan: {check_link}")

        # 13. Kanalga va Adminga yuborish
        channel_text = (
            f"🎁 <b>Yangi BestBit cheki!</b>\n\n"
            f"🔗 {check_link}"
        )

        # Telegram Bot API orqali kanalga yuborish (ishonchli)
        bot_inst = Bot(token=config.BOT_TOKEN)
        try:
            target_chat = target_channel
            if (target_channel.startswith('-') and target_channel[1:].isdigit()) or target_channel.isdigit():
                target_chat = int(target_channel)
            await bot_inst.send_message(chat_id=target_chat, text=channel_text, parse_mode="HTML")
            logger.info(f"[{phone}] Chek {target_channel} kanaliga bot orqali muvaffaqiyatli tashlandi!")
        except Exception as bot_err:
            logger.error(f"[{phone}] Bot orqali {target_channel} kanaliga tashlashda xatolik: {bot_err}")

        # temp_client orqali ham kanalga yuborishga urinish
        try:
            await client.send_message(target_channel, channel_text, parse_mode='html')
            logger.info(f"[{phone}] Chek {target_channel} kanaliga temp_client orqali ham tashlandi!")
        except Exception as cl_err:
            logger.debug(f"[{phone}] temp_client kanalga yuborolmadi (ruxsat yo'q bo'lishi normal): {cl_err}")

        # Adminga hisobot
        if config.ADMIN_ID:
            try:
                admin_text = (
                    f"🎁 <b>Yangi BestBit cheki olindi!</b>\n\n"
                    f"📞 <b>Akkaunt:</b> <code>+{phone}</code>\n"
                    f"🔗 <b>Chek:</b> {check_link}\n"
                    f"📢 <b>Kanal:</b> {target_channel} ✅"
                )
                await bot_inst.send_message(chat_id=config.ADMIN_ID, text=admin_text, parse_mode="HTML")
            except Exception as adm_err:
                logger.warning(f"Adminga chek xabari yuborishda xatolik: {adm_err}")

        await bot_inst.session.close()
        return {"success": True, "check_link": check_link, "error": None}

    except Exception as e:
        logger.error(f"[{phone}] BestBit jarayonida kutilmagan xatolik: {e}", exc_info=True)
        return {"success": False, "check_link": None, "error": str(e)}
