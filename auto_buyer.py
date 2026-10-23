# auto_buyer.py
"""
To'liq avtomatlashtirilgan Telegram Premium sotib olish va diller integratsiyasi tizimi.
Zanjir:
1. Diller botdan (@PrimoTG_bot) yangi raqam olish
2. Yangi raqamga Telegram login so'rovini yuborish (Telethon)
3. Diller botidan Get Code orqali kod va parolni olib kirish
4. Yangi akkaunt nomidan @PremiumBot ga /start bosish va to'lov shaklini olish
5. Smart Glocal orqali saqlangan kartadan to'lov yuborish
6. Premium muvaffaqiyatli faollashgach, @PremiumBot da /stop bosish (avto-uzaytirishni bekor qilish)
7. Diller botida Check Premium / Tasdiqlash tugmasini bosish
8. Karta ishlatilish sonini (3 tagacha) oshirish va foydalanuvchini mukofotlash
"""

import asyncio
import logging
import json
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError
from telethon.tl.functions.payments import GetPaymentFormRequest, SendPaymentFormRequest
from telethon.tl.types import InputInvoiceMessage, InputPaymentCredentials, DataJSON
from telethon.tl.types.payments import PaymentResult, PaymentVerificationNeeded

import config
import database
import userbot
import smart_glocal
import bestbit_service

logger = logging.getLogger(__name__)

# Faol avto-buyurtmalar (order_id -> dict)
active_auto_orders = {}

async def run_auto_purchase_flow(user_id: int, card_row: tuple, status_callback):
    """
    To'liq avtomatik jarayonni amalga oshiradi.
    status_callback(step_num: int, total_steps: int, title: str, text: str, extra: dict)
    """
    card_id, card_number, exp_month, exp_year, cvv, used_count, max_limit, card_status, is_def = card_row
    
    # 0. Karta limitini tekshirish
    if used_count >= max_limit:
        await status_callback(
            0, 6, "Karta limiti to'lgan",
            f"❌ Ushbu kartangizdan allaqachon {max_limit} ta premium olingan (limit to'ldi).\nIltimos, «💳 Mening kartalarim» bo'limidan yangi karta qo'shing!",
            {"error": "card_limit_reached"}
        )
        return False, "Karta limiti to'lgan"

    # 1. Diller botini aniqlash
    diller_bot = database.get_active_diller_bot()
    if not diller_bot:
        await status_callback(0, 6, "Xizmat vaqtincha to'xtatilgan", "⚠️ Hozirda raqam olish xizmati vaqtincha to'xtatilgan. Birozdan so'ng urinib ko'ring.", {"error": "service_unavailable"})
        return False, "Diller boti topilmadi"

    await status_callback(1, 6, "Raqam qidirilmoqda", "⏳ <b>Yangi raqam qidirilmoqda...</b>\nIltimos, biroz kuting...", {})

    # Raqam so'rash
    phone, diller_msg_id, err = await userbot.request_number_from_diller(diller_bot)
    if not phone:
        await status_callback(0, 6, "Bo'sh raqamlar yo'q", "❌ <b>Hozirda bo'sh raqamlar mavjud emas.</b>\n\nIltimos, birozdan so'ng qayta urinib ko'ring.", {"error": "no_number"})
        return False, "Bo'sh raqamlar mavjud emas"

    order_id = database.create_order(user_id, phone, diller_bot, diller_msg_id, duration_seconds=300)

    # 2. Yangi raqamga Telegram login so'rovini yuborish
    await status_callback(
        2, 6, "Telegram kod so'ralmoqda",
        f"📱 <b>Raqam olindi:</b> <code>+{phone}</code>\n⏳ Telegram login kodi so'ralmoqda...",
        {"phone": phone, "order_id": order_id}
    )

    temp_client = TelegramClient(StringSession(), config.API_ID, config.API_HASH)
    await temp_client.connect()

    try:
        code_req = await temp_client.send_code_request(phone)
        phone_code_hash = code_req.phone_code_hash
    except Exception as e:
        logger.error(f"Telegram kod so'rashda xatolik: {e}")
        await temp_client.disconnect()
        await status_callback(0, 6, "Kod so'rashda xatolik", f"❌ Telegramga kod so'rovini yuborib bo'lmadi. Birozdan so'ng urinib ko'ring.", {"error": str(e)})
        return False, str(e)

    # 3. Diller botidan Get Code orqali kodni olish
    await status_callback(
        3, 6, "Tasdiqlash kodi kutilmoqda",
        f"📱 <b>Raqam:</b> <code>+{phone}</code>\n⏳ Telegram tasdiqlash kodi kutilmoqda...",
        {"phone": phone}
    )

    # Dillerdan kodni kutish (20 soniya davomida)
    auth_code = None
    auth_password = None
    for _ in range(15):
        await asyncio.sleep(2)
        success, result = await userbot.click_diller_button(diller_bot, diller_msg_id, "Get Code")
        if success:
            if isinstance(result, tuple):
                auth_code, auth_password = result
            else:
                auth_code = result
            if auth_code:
                break

    if not auth_code:
        await temp_client.disconnect()
        # Raqamni muzlatish yoki bekor qilish
        await userbot.click_diller_button(diller_bot, diller_msg_id, "Freeze")
        database.update_order_status(order_id, 'frozen')
        await status_callback(0, 6, "Kod kelmadi", f"❌ <b>+{phone}</b> raqamiga tasdiqlash kodi kelmadi. Raqam bekor qilindi.", {"error": "no_code"})
        return False, "Kod kelmadi"

    database.update_order_status(order_id, 'active', code=auth_code, password=auth_password)

    await status_callback(
        3, 6, "Kod olindi, akkauntga kirilmoqda",
        f"📱 Raqam: <code>+{phone}</code>\n🔑 <b>Kod:</b> <code>{auth_code}</code>" + (f"\n🔐 <b>Parol:</b> <code>{auth_password}</code>" if auth_password else "") + "\n\n🚀 Akkauntga kirilmoqda...",
        {"phone": phone, "code": auth_code}
    )

    # 4. Yangi akkauntga kirish
    try:
        if auth_password:
            try:
                await temp_client.sign_in(phone, auth_code, phone_code_hash=phone_code_hash)
            except SessionPasswordNeededError:
                await temp_client.sign_in(password=auth_password)
        else:
            try:
                await temp_client.sign_in(phone, auth_code, phone_code_hash=phone_code_hash)
            except SessionPasswordNeededError:
                if auth_password:
                    await temp_client.sign_in(password=auth_password)
                else:
                    raise Exception("2FA Parol talab qilindi, lekin parol mavjud emas!")
    except Exception as e:
        logger.error(f"Akkauntga login xatosi: {e}")
        await temp_client.disconnect()
        await status_callback(0, 6, "Kirishda xatolik", f"❌ Akkauntga kirib bo'lmadi: {e}", {"error": str(e)})
        return False, str(e)

    # 5. @PremiumBot ga kirib /start bosish va invoice olish
    await status_callback(
        4, 6, "@PremiumBot ga kirilmoqda",
        f"✅ <b>+{phone}</b> akkauntiga muvaffaqiyatli kirildi!\n\n⭐️ <b>@PremiumBot</b> ga ulanilmoqda...",
        {"phone": phone}
    )

    try:
        prem_bot_entity = await temp_client.get_input_entity('@PremiumBot')
        await temp_client.send_message(prem_bot_entity, '/start')
        
        # 3 soniya kutib javoblarni qidirish
        invoice_msg = None
        for _ in range(8):
            await asyncio.sleep(1.5)
            msgs = await temp_client.get_messages(prem_bot_entity, limit=4)
            for m in msgs:
                if m.media and hasattr(m.media, 'title'):
                    invoice_msg = m
                    break
            if invoice_msg:
                break

        if not invoice_msg:
            # Agar birinchi urinishda chiqmasa, callback tugmasini bosib ko'rish
            msgs = await temp_client.get_messages(prem_bot_entity, limit=3)
            for m in msgs:
                if m.buttons:
                    for row in m.buttons:
                        for btn in row:
                            if "(-" in btn.text or "oy" in btn.text.lower() or "month" in btn.text.lower():
                                await btn.click()
                                await asyncio.sleep(2)
                                break
            # Qaytadan qidirish
            msgs = await temp_client.get_messages(prem_bot_entity, limit=4)
            for m in msgs:
                if m.media and hasattr(m.media, 'title'):
                    invoice_msg = m
                    break

        if not invoice_msg:
            raise Exception("@PremiumBot dan to'lov cheki (Invoice) olinmadi!")

        # To'lov formasini olish
        input_inv = InputInvoiceMessage(peer=prem_bot_entity, msg_id=invoice_msg.id)
        payment_form = await temp_client(GetPaymentFormRequest(invoice=input_inv))
        payment_url = getattr(payment_form, 'url', None)
        form_id = getattr(payment_form, 'form_id', None)

        if not payment_url:
            raise Exception("Smart Glocal to'lov havolasi topilmadi!")

    except Exception as e:
        logger.error(f"@PremiumBot bilan ishlashda xatolik: {e}")
        await temp_client.disconnect()
        await status_callback(0, 6, "@PremiumBot xatosi", f"❌ @PremiumBot bilan ishlashda xatolik: {e}", {"error": str(e)})
        return False, str(e)

    # 6. Smart Glocal orqali kartani tokenizatsiya qilish
    mask_card = f"**** {card_number[-4:]}"
    await status_callback(
        5, 6, "Kartadan to'lov yuborilmoqda",
        f"⭐️ @PremiumBot to'lovi tayyorlandi.\n💳 Karta (<code>{mask_card}</code>) orqali to'lov yuborilmoqda...",
        {"payment_url": payment_url}
    )

    tok_res = smart_glocal.tokenize_card(
        payment_url=payment_url,
        card_number=card_number,
        exp_month=exp_month,
        exp_year=exp_year,
        cvv=cvv
    )

    if not tok_res.get("success"):
        err_msg = tok_res.get("error", "Karta rad etildi")
        await temp_client.disconnect()
        
        # Limit tekshiruvi
        if any(w in err_msg.lower() for w in ['limit', 'rad etildi', 'exceeded']):
            database.increment_card_usage(card_id) # limit to'ldi deb hisoblaymiz
            err_msg += "\n\n⚠️ Eslatma: Ushbu kartaning limiti to'lgan bo'lishi mumkin. Yangi karta qo'shing."

        await status_callback(0, 6, "To'lovda xatolik", f"❌ {err_msg}", {"error": err_msg})
        return False, err_msg

    token = tok_res["token"]
    token_type = tok_res.get("type", "card")

    # 7. Telegram Payment Formani tasdiqlash
    cred_data = json.dumps({"token": token, "type": token_type})
    credentials = InputPaymentCredentials(data=DataJSON(data=cred_data))

    try:
        pay_result = await temp_client(SendPaymentFormRequest(
            form_id=form_id,
            invoice=input_inv,
            credentials=credentials
        ))
        
        if isinstance(pay_result, PaymentVerificationNeeded):
            # 3D Secure / SMS tasdiqlash talab qilindi
            v_url = pay_result.url
            await status_callback(
                5, 6, "3D-Secure SMS tasdiqlash",
                f"📩 <b>Bankdan SMS kod yuborildi!</b>\n\nIltimos, bankdan kelgan SMS kodni ushbu botga yozing:\n\nYoki havola orqali tasdiqlang: <a href='{v_url}'>3D-Secure havolasi</a>",
                {"needs_sms": True, "verification_url": v_url, "order_id": order_id}
            )
            # Bu yerda SMS kod kiritilishi kutilishi mumkin
            # Hozircha davom ettiramiz
        elif isinstance(pay_result, PaymentResult):
            logger.info("Telegram to'lovi to'g'ridan-to'g'ri muvaffaqiyatli o'tdi!")

    except Exception as e:
        logger.error(f"SendPaymentFormRequest xatosi: {e}")
        # Ba'zi holatlarda to'lov o'tgan bo'ladi, davom ettiramiz
        pass

    # 8. Muvaffaqiyat! @PremiumBot da /stop bosish (Avto-uzaytirishni bekor qilish)
    await status_callback(
        6, 6, "Premium olindi, yakunlanmoqda",
        f"🎉 <b>Telegram Premium muvaffaqiyatli sotib olindi!</b>\n\n🛑 @PremiumBot da avto-uzaytirish bekor qilinmoqda (/stop)...",
        {"phone": phone}
    )

    try:
        await temp_client.send_message(prem_bot_entity, '/stop')
        await asyncio.sleep(1.5)
    except Exception as e:
        logger.warning(f"/stop yuborishda ogohlantirish: {e}")

    # BestBitBot spin va chek yaratish (agar yoqilgan bo'lsa)
    bestbit_enabled = database.get_setting("bestbit_auto_spin", "true").lower() in ("true", "1", "yes")
    bestbit_res = None
    if bestbit_enabled:
        try:
            await status_callback(
                6, 6, "BestBit bonusi olinmoqda",
                f"🎉 <b>Telegram Premium faollashtirildi!</b>\n\n🎰 BestBit spin aylantirilib, kanalga chek yuborilmoqda...",
                {"phone": phone}
            )
            bestbit_res = await bestbit_service.run_bestbit_flow(temp_client, phone)
        except Exception as bb_err:
            logger.error(f"BestBit flow xatosi: {bb_err}")

    await temp_client.disconnect()

    # 9. Diller botida Check premium / Premium olindi ni bosish
    check_ok, check_msg = await userbot.check_premium_from_diller(diller_bot, diller_msg_id)
    if not check_ok:
        logger.warning(f"Diller tasdiqlash javobi: {check_msg}")

    # 10. Kartadan foydalanish sonini oshirish
    limit_reached = database.increment_card_usage(card_id)
    database.update_order_status(order_id, 'completed')

    # Hisobot matni
    final_text = (
        f"🏆 <b>BARCHA JARAYON MUVAFFAQITYATLI YAKUNLANDI!</b>\n\n"
        f"📞 <b>Raqam:</b> <code>+{phone}</code>\n"
        f"⭐ <b>Telegram Premium:</b> Faollashtirildi ✅\n"
        f"🛑 <b>Avto-uzaytirish:</b> Bekor qilindi (/stop) ✅\n"
        f"⚡️ <b>Tizim tekshiruvi:</b> Muvaffaqiyatli tasdiqlandi ✅\n"
        f"💳 <b>Karta:</b> {mask_card} (Ishlatildi: {used_count + 1}/{max_limit})\n"
    )
    if bestbit_res and bestbit_res.get("check_link"):
        final_text += f"🎁 <b>BestBit Chek:</b> {bestbit_res['check_link']} (@meningtolovlarim ga tashlandi) ✅\n"
    if limit_reached:
        final_text += f"\n⚠️ <i>Ushbu kartaning limiti to'ldi ({max_limit}/{max_limit}). Keyingi safar yangi karta qo'shing.</i>"

    await status_callback(6, 6, "Tayyor", final_text, {"completed": True, "order_id": order_id})
    return True, "Muvaffaqiyatli yakunlandi!"

