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
import telethon_patch
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
import proxy_manager
import channel_logger

logger = logging.getLogger(__name__)

# Faol avto-buyurtmalar (order_id -> dict)
active_auto_orders = {}

async def cancel_auto_order(order_id: int) -> tuple[bool, str]:
    """Foydalanuvchi tomonidan avto-buyurtmani bekor qilish"""
    order_data = active_auto_orders.get(order_id)
    if not order_data:
        database.update_order_status(order_id, 'cancelled')
        return True, "Buyurtma bekor qilindi ❌"

    order_data["is_cancelled"] = True
    
    # 1. Diller botida raqamni bekor qilish
    diller_bot = order_data.get("diller_bot")
    diller_msg_id = order_data.get("diller_msg_id")
    if diller_bot and diller_msg_id:
        try:
            await userbot.click_diller_button(diller_bot, diller_msg_id, "Cancel")
        except Exception:
            pass

    # 2. Telethon mijozini uzish
    client = order_data.get("temp_client")
    if client:
        try:
            await client.disconnect()
        except Exception:
            pass

    # 3. Bazada holatni yangilash
    database.update_order_status(order_id, 'cancelled')

    # 4. Foydalanuvchi status xabarini yangilash
    cb = order_data.get("status_callback")
    if cb:
        try:
            await cb(
                0, 6, "Buyurtma bekor qilindi",
                "❌ <b>Buyurtma foydalanuvchi tomonidan bekor qilindi.</b>",
                {"error": "user_cancelled", "cancelled": True, "order_id": order_id}
            )
        except Exception:
            pass

    # 5. Taskni to'xtatish
    task = order_data.get("task")
    if task and not task.done():
        task.cancel()

    active_auto_orders.pop(order_id, None)
    return True, "Buyurtma bekor qilindi ❌"

async def resend_code_auto_order(order_id: int) -> tuple[bool, str]:
    """Diller botidan va Telegramdan qayta kod so'rash"""
    order_data = active_auto_orders.get(order_id)
    if not order_data:
        return False, "Buyurtma topilmadi yoki faol emas!"

    diller_bot = order_data.get("diller_bot")
    diller_msg_id = order_data.get("diller_msg_id")
    phone = order_data.get("phone")
    client = order_data.get("temp_client")
    phone_code_hash = order_data.get("phone_code_hash")

    # 1. Telegram orqali resend_code
    if client and phone and phone_code_hash:
        try:
            await asyncio.wait_for(client.resend_code(phone, phone_code_hash), timeout=5.0)
            logger.info(f"[{phone}] Telegram resend_code chaqirildi.")
        except Exception as e:
            logger.debug(f"Telegram resend_code ogohlantirish: {e}")

    # 2. Diller botida Get Code tugmasini bosish
    if diller_bot and diller_msg_id:
        try:
            await userbot.click_diller_button(diller_bot, diller_msg_id, "Get Code", expected_phone=phone)
            logger.info(f"[{phone}] Diller botida Get Code qayta bosildi.")
        except Exception as e:
            logger.warning(f"Diller Get Code bosishda xatolik: {e}")

    return True, "🔄 Kod diller botidan qayta so'ralmoqda, iltimos kuting..."

async def check_3ds_payment_auto_order(order_id: int) -> tuple[bool, str]:
    """Bank SMS to'lovi tasdiqlanganini darhol qo'lda tekshirish"""
    order_data = active_auto_orders.get(order_id)
    if not order_data:
        return False, "Buyurtma topilmadi yoki yakunlangan!"

    client = order_data.get("temp_client")
    if not client:
        return False, "Mijoz ulanmagan!"

    from telethon.tl.functions.users import GetUsersRequest
    from telethon.tl.types import InputUserSelf

    try:
        if not client.is_connected():
            await client.connect()
        fresh_users = await asyncio.wait_for(client(GetUsersRequest([InputUserSelf()])), timeout=5.0)
        if fresh_users and getattr(fresh_users[0], 'premium', False):
            order_data["payment_verified"] = True
            return True, "✅ To'lov muvaffaqiyatli tasdiqlandi!"
    except Exception as e:
        logger.debug(f"Qo'lda 3DS tekshirishda xatolik: {e}")

    return False, "⏳ Bank to'lovi hali tasdiqlanmadi. Iltimos, SMS kodni kiritib tasdiqlang."

async def run_auto_purchase_flow(user_id: int, card_row: tuple, status_callback):
    """
    To'liq avtomatik jarayonni boshqaradi va bekor qilish (cancellation) ni ushlaydi.
    """
    ctx = {}
    try:
        return await _inner_auto_purchase_flow(user_id, card_row, status_callback, ctx)
    except asyncio.CancelledError:
        order_id = ctx.get("order_id")
        temp_client = ctx.get("temp_client")
        diller_bot = ctx.get("diller_bot")
        diller_msg_id = ctx.get("diller_msg_id")
        phone = ctx.get("phone")
        logger.info(f"[{phone}] Buyurtma #{order_id} foydalanuvchi tomonidan bekor qilindi.")
        if temp_client:
            try:
                await temp_client.disconnect()
            except Exception:
                pass
        if order_id:
            database.update_order_status(order_id, 'cancelled')
        if diller_bot and diller_msg_id:
            try:
                await userbot.click_diller_button(diller_bot, diller_msg_id, "Cancel")
            except Exception:
                pass
        await status_callback(
            0, 6, "Buyurtma bekor qilindi",
            "❌ <b>Buyurtma foydalanuvchi tomonidan bekor qilindi.</b>",
            {"error": "user_cancelled", "cancelled": True, "order_id": order_id}
        )
        return False, "Foydalanuvchi tomonidan bekor qilindi"
    finally:
        order_id = ctx.get("order_id")
        if order_id:
            active_auto_orders.pop(order_id, None)

async def _inner_auto_purchase_flow(user_id: int, card_row: tuple, status_callback, ctx: dict):
    """
    Asosiy avtomatik xarid mantig'i.
    """
    if len(card_row) >= 10:
        card_id, card_number, exp_month, exp_year, cvv, cardholder_name, used_count, max_limit, card_status, is_def = card_row[:10]
    else:
        card_id, card_number, exp_month, exp_year, cvv, used_count, max_limit, card_status, is_def = card_row[:9]
        cardholder_name = ""
    
    # 0. Karta limitini tekshirish
    if used_count >= max_limit:
        await status_callback(
            0, 6, "Karta limiti to'lgan",
            f"❌ Ushbu kartangizdan allaqachon {max_limit} ta premium olingan (limit to'ldi).\nIltimos, «💳 Mening kartalarim» bo'limidan yangi karta qo'shing!",
            {"error": "card_limit_reached"}
        )
        return False, "Karta limiti to'lgan"

    # 1. Diller botini aniqlash (Foydalanuvchi marshrutiga asosan)
    diller_bot = database.get_active_diller_bot(user_id=user_id)
    if not diller_bot:
        await status_callback(0, 6, "Xizmat vaqtincha to'xtatilgan", "⚠️ Hozirda raqam olish xizmati vaqtincha to'xtatilgan. Birozdan so'ng urinib ko'ring.", {"error": "service_unavailable"})
        return False, "Diller boti topilmadi"

    await status_callback(1, 6, "Raqam qidirilmoqda", "⏳ <b>Yangi raqam qidirilmoqda...</b>\nIltimos, biroz kuting...", {})

    # Proksi IP manzilini yangilash (agar sozlangan bo'lsa)
    await proxy_manager.trigger_rotation_before_purchase()

    # Raqam so'rash
    phone, diller_msg_id, err = await userbot.request_number_from_diller(diller_bot)
    if not phone:
        await status_callback(0, 6, "Bo'sh raqamlar yo'q", "❌ <b>Hozirda bo'sh raqamlar mavjud emas.</b>\n\nIltimos, birozdan so'ng qayta urinib ko'ring.", {"error": "no_number"})
        return False, "Bo'sh raqamlar mavjud emas"

    order_id = database.create_order(user_id, phone, diller_bot, diller_msg_id, duration_seconds=300)
    ctx["order_id"] = order_id
    ctx["phone"] = phone
    ctx["diller_bot"] = diller_bot
    ctx["diller_msg_id"] = diller_msg_id

    # Guruh/kanalga Number logini yuborish
    asyncio.create_task(channel_logger.send_number_log(user_id, phone, diller_bot, mode="Avto-Premium"))

    order_data = {
        "user_id": user_id,
        "phone": phone,
        "diller_bot": diller_bot,
        "diller_msg_id": diller_msg_id,
        "temp_client": None,
        "phone_code_hash": None,
        "is_cancelled": False,
        "payment_verified": False,
        "task": asyncio.current_task(),
        "status_callback": status_callback
    }
    active_auto_orders[order_id] = order_data

    # 2. Yangi raqamga Telegram login so'rovini yuborish
    await status_callback(
        2, 6, "Telegram kod so'ralmoqda",
        f"📱 <b>Raqam olindi:</b> <code>+{phone}</code>\n⏳ Telegram login kodi so'ralmoqda...",
        {"phone": phone, "order_id": order_id}
    )

    proxy_conf = proxy_manager.get_telethon_proxy()
    temp_client = None

    async def _init_and_request_code(use_proxy: bool):
        p_c = proxy_conf if use_proxy else None
        if p_c:
            logger.info(f"Yangi akkaunt uchun Proksi ulanmoqda: {p_c[1]}:{p_c[2]}")
        else:
            logger.info("Yangi akkaunt uchun to'g'ridan-to'g'ri (proxy-siz) ulanmoqda...")

        tc = TelegramClient(
            StringSession(),
            config.API_ID,
            config.API_HASH,
            proxy=p_c,
            receive_updates=False,
            connection_retries=3,
            retry_delay=1,
            timeout=10.0,
            auto_reconnect=True
        )
        await asyncio.wait_for(tc.connect(), timeout=12.0)
        c_req = await asyncio.wait_for(tc.send_code_request(phone), timeout=15.0)
        return tc, c_req.phone_code_hash

    try:
        if proxy_conf:
            try:
                temp_client, phone_code_hash = await _init_and_request_code(use_proxy=True)
            except Exception as proxy_err:
                logger.warning(f"Proksi orqali Telegram kod so'rashda xatolik ({proxy_err}). To'g'ridan-to'g'ri ulanishga o'tilmoqda...")
                if temp_client:
                    try:
                        await temp_client.disconnect()
                    except Exception:
                        pass
                temp_client, phone_code_hash = await _init_and_request_code(use_proxy=False)
        else:
            temp_client, phone_code_hash = await _init_and_request_code(use_proxy=False)

        order_data["temp_client"] = temp_client
        ctx["temp_client"] = temp_client
        order_data["phone_code_hash"] = phone_code_hash
    except Exception as e:
        logger.error(f"Telegram kod so'rashda xatolik: {e}")
        if temp_client:
            try:
                await temp_client.disconnect()
            except Exception:
                pass
        database.update_order_status(order_id, 'cancelled')
        await userbot.click_diller_button(diller_bot, diller_msg_id, "Cancel")
        await status_callback(0, 6, "Kod so'rashda xatolik", f"❌ Telegramga kod so'rovini yuborib bo'lmadi: {e}", {"error": str(e), "order_id": order_id})
        return False, str(e)

    if order_data.get("is_cancelled"):
        raise asyncio.CancelledError()

    # 3. Diller botidan Get Code orqali kodni olish
    await status_callback(
        3, 6, "Tasdiqlash kodi kutilmoqda",
        f"📱 <b>Raqam:</b> <code>+{phone}</code>\n⏳ Telegram tasdiqlash kodi kutilmoqda...",
        {"phone": phone, "order_id": order_id}
    )

    # Dillerdan kodni kutish (expected_phone bilan aniq tekshirish)
    auth_code = None
    auth_password = None
    for _ in range(2):
        if order_data.get("is_cancelled"):
            raise asyncio.CancelledError()
        success, result = await userbot.click_diller_button(diller_bot, diller_msg_id, "Get Code", expected_phone=phone)
        if success:
            if isinstance(result, tuple):
                auth_code, auth_password = result
            else:
                auth_code = result
            if auth_code and auth_code.isdigit():
                break
        await asyncio.sleep(0.5)

    if not auth_code:
        try:
            await temp_client.disconnect()
        except Exception:
            pass
        # Raqamni muzlatish yoki bekor qilish
        await userbot.click_diller_button(diller_bot, diller_msg_id, "Freeze")
        database.update_order_status(order_id, 'frozen')
        await status_callback(0, 6, "Kod kelmadi", f"❌ <b>+{phone}</b> raqamiga tasdiqlash kodi kelmadi. Raqam bekor qilindi.", {"error": "no_code", "order_id": order_id})
        return False, "Kod kelmadi"

    if order_data.get("is_cancelled"):
        raise asyncio.CancelledError()

    database.update_order_status(order_id, 'active', code=auth_code, password=auth_password)

    await status_callback(
        3, 6, "Kod olindi, akkauntga kirilmoqda",
        f"📱 Raqam: <code>+{phone}</code>\n🔑 <b>Kod:</b> <code>{auth_code}</code>" + (f"\n🔐 <b>Parol:</b> <code>{auth_password}</code>" if auth_password else "") + "\n\n🚀 Akkauntga kirilmoqda...",
        {"phone": phone, "code": auth_code, "order_id": order_id}
    )

    # 4. Yangi akkauntga kirish
    try:
        if not temp_client.is_connected():
            await asyncio.wait_for(temp_client.connect(), timeout=10.0)

        if auth_password:
            try:
                await asyncio.wait_for(temp_client.sign_in(phone, auth_code, phone_code_hash=phone_code_hash), timeout=15.0)
            except SessionPasswordNeededError:
                await asyncio.wait_for(temp_client.sign_in(password=auth_password), timeout=15.0)
        else:
            try:
                await asyncio.wait_for(temp_client.sign_in(phone, auth_code, phone_code_hash=phone_code_hash), timeout=15.0)
            except SessionPasswordNeededError:
                if auth_password:
                    await asyncio.wait_for(temp_client.sign_in(password=auth_password), timeout=15.0)
                else:
                    raise Exception("2FA Parol talab qilindi, lekin parol mavjud emas!")
    except Exception as e:
        logger.error(f"Akkauntga login xatosi: {e}")
        try:
            await temp_client.disconnect()
        except Exception:
            pass
        database.update_order_status(order_id, 'cancelled')
        await userbot.click_diller_button(diller_bot, diller_msg_id, "Freeze")
        await status_callback(0, 6, "Kirishda xatolik", f"❌ Akkauntga kirib bo'lmadi: {e}", {"error": str(e)})
        return False, str(e)

    # 5. @PremiumBot ga kirib /start bosish va invoice olish
    await status_callback(
        4, 6, "@PremiumBot ga kirilmoqda",
        f"✅ <b>+{phone}</b> akkauntiga muvaffaqiyatli kirildi!\n\n⭐️ <b>@PremiumBot</b> ga ulanilmoqda...",
        {"phone": phone}
    )

    try:
        # DC migration yoki qayta ulanish zarur bo'lsa
        prem_bot_entity = None
        for attempt in range(3):
            try:
                if not temp_client.is_connected():
                    await asyncio.wait_for(temp_client.connect(), timeout=10.0)
                prem_bot_entity = await asyncio.wait_for(temp_client.get_input_entity('@PremiumBot'), timeout=15.0)
                await asyncio.wait_for(temp_client.send_message(prem_bot_entity, '/start'), timeout=15.0)
                break
            except Exception as conn_err:
                logger.warning(f"@PremiumBot ga ulanishda urinish {attempt+1}/3: {conn_err}")
                if attempt == 2:
                    raise conn_err
                await asyncio.sleep(2)
        
        # Javoblar va to'lov chekini (Invoice) qidirish (Aynan 1 oylik: 35 990 UZS / ~$3.99)
        invoice_msg = None
        inv_title = "Telegram Premium (1 oy)"
        amount_fmt = "1 oylik"
        
        for poll_idx in range(16):
            await asyncio.sleep(0.5)
            if not temp_client.is_connected():
                try:
                    await asyncio.wait_for(temp_client.connect(), timeout=8.0)
                except Exception:
                    pass

            try:
                msgs = await asyncio.wait_for(temp_client.get_messages(prem_bot_entity, limit=5), timeout=10.0)
            except Exception as get_err:
                logger.warning(f"@PremiumBot xabarlarini olishda ogohlantirish: {get_err}")
                continue

            # 1. Mavjud xabarlar orasidan Invoice (to'lov cheki) qidirish
            for m in msgs:
                if m.media and hasattr(m.media, 'title'):
                    invoice_msg = m
                    break

            if invoice_msg:
                inv_amount = getattr(invoice_msg.media, 'total_amount', 0)
                inv_curr = getattr(invoice_msg.media, 'currency', 'USD')
                inv_title = getattr(invoice_msg.media, 'title', '') or 'Telegram Premium'

                # Yillik tarifni aniqlash:
                # 1. Tugmalarda "Перейти на месячную" (Switch to monthly) borligi (chunki oylikda bo'lsa "Перейти на годовую" deb turadi)
                # 2. Title da "year", "annual", "годов", "12 мес" so'zlari
                # 3. Yoki summa bo'yicha (UZS > 100,000, USD > 15, INR > 1,000, RUB > 1,500)
                has_switch_to_monthly_btn = False
                for m in msgs:
                    if m.buttons:
                        for row in m.buttons:
                            for btn in row:
                                b_txt = (btn.text or "").lower()
                                if any(w in b_txt for w in ["перейти на месячную", "месячн", "switch to monthly", "monthly"]):
                                    has_switch_to_monthly_btn = True
                                    break
                            if has_switch_to_monthly_btn:
                                break
                    if has_switch_to_monthly_btn:
                        break

                is_annual = (
                    has_switch_to_monthly_btn or
                    any(w in inv_title.lower() for w in ["year", "annual", "годов", "12 мес", "12-month"]) or
                    (inv_curr == "UZS" and inv_amount > 10000000) or
                    (inv_curr == "USD" and inv_amount > 1500) or
                    (inv_curr == "INR" and inv_amount > 100000) or
                    (inv_curr == "RUB" and inv_amount > 150000)
                )

                if is_annual and poll_idx < 3:
                    logger.warning(f"Invoice yillik tarifda chiqdi ({inv_amount} {inv_curr}). Oylikka o'tkazish qidirilmoqda...")
                    monthly_btn_clicked = False
                    for m in msgs:
                        if m.buttons:
                            for row in m.buttons:
                                for btn in row:
                                    b_txt = (btn.text or "").lower()
                                    # Yillik emas, aynan oylikka o'tish tugmasi
                                    if not any(w in b_txt for w in ["годов", "annual", "yearly", "yillik"]) and any(w in b_txt for w in ["перейти на месячную", "месячн", "monthly", "oylik"]):
                                        logger.info(f"Oylik tarifga o'tish tugmasi bosilmoqda: '{btn.text}'")
                                        try:
                                            await asyncio.wait_for(btn.click(), timeout=8.0)
                                            monthly_btn_clicked = True
                                            await asyncio.sleep(2.5)
                                            break
                                        except Exception as click_e:
                                            logger.warning(f"Oylik tugmasini bosishda xato: {click_e}")
                                if monthly_btn_clicked:
                                    break
                        if monthly_btn_clicked:
                            break
                    if monthly_btn_clicked:
                        invoice_msg = None
                        continue

                # 1 oylik invoice (masalan 35 990 UZS / 259.90 INR / $3.99) tayyor!
                break

        if not invoice_msg:
            raise Exception("@PremiumBot dan to'lov cheki (Invoice) olinmadi!")

        inv_title = getattr(invoice_msg.media, 'title', 'Telegram Premium 1 oy')
        inv_amount = getattr(invoice_msg.media, 'total_amount', 0)
        inv_curr = getattr(invoice_msg.media, 'currency', 'USD')
        amount_fmt = f"{inv_amount / 100:,.2f} {inv_curr}" if inv_amount else "1 oylik"
        logger.info(f"✅ Tanlangan Invoice: title='{inv_title}', amount={amount_fmt}")

        # To'lov formasini olish
        if not temp_client.is_connected():
            await asyncio.wait_for(temp_client.connect(), timeout=8.0)
        input_inv = InputInvoiceMessage(peer=prem_bot_entity, msg_id=invoice_msg.id)
        payment_form = await asyncio.wait_for(temp_client(GetPaymentFormRequest(invoice=input_inv)), timeout=20.0)
        payment_url = getattr(payment_form, 'url', None)
        form_id = getattr(payment_form, 'form_id', None)

        if not payment_url:
            raise Exception("Smart Glocal to'lov havolasi topilmadi!")

    except Exception as e:
        logger.error(f"@PremiumBot bilan ishlashda xatolik: {e}")
        try:
            await temp_client.disconnect()
        except Exception:
            pass
        database.update_order_status(order_id, 'cancelled')
        await userbot.click_diller_button(diller_bot, diller_msg_id, "Freeze")
        await status_callback(0, 6, "@PremiumBot xatosi", f"❌ @PremiumBot bilan ishlashda xatolik: {e}", {"error": str(e)})
        return False, str(e)

    # 6. Smart Glocal orqali kartani tokenizatsiya qilish
    mask_card = f"**** {card_number[-4:]}"
    await status_callback(
        5, 6, "Kartadan to'lov yuborilmoqda",
        f"⭐️ <b>{inv_title} ({amount_fmt})</b> tayyorlandi.\n💳 Karta (<code>{mask_card}</code>) orqali to'lov yuborilmoqda...",
        {"payment_url": payment_url}
    )

    # Karta egasining ism-familiyasi (foydalanuvchi kiritgan to'liq ism)
    final_acc_name = str(cardholder_name).strip() if cardholder_name else ""
    if not final_acc_name:
        try:
            me_acc = await temp_client.get_me()
            first_n = getattr(me_acc, 'first_name', '') or ''
            last_n = getattr(me_acc, 'last_name', '') or ''
            comb_name = f"{first_n} {last_n}".strip()
            if comb_name:
                final_acc_name = comb_name
        except Exception:
            pass
    if not final_acc_name:
        final_acc_name = "Telegram User"

    tok_res = smart_glocal.tokenize_card(
        payment_url=payment_url,
        card_number=card_number,
        exp_month=exp_month,
        exp_year=exp_year,
        cvv=cvv,
        cardholder_name=final_acc_name
    )

    if not tok_res.get("success"):
        err_msg = tok_res.get("error", "Karta rad etildi")
        await temp_client.disconnect()
        database.update_order_status(order_id, 'cancelled')
        await userbot.click_diller_button(diller_bot, diller_msg_id, "Freeze")
        
        # Limit tekshiruvi
        if any(w in err_msg.lower() for w in ['limit', 'rad etildi', 'exceeded']):
            database.increment_card_usage(card_id) # limit to'ldi deb hisoblaymiz
            err_msg += "\n\n⚠️ Eslatma: Ushbu kartaning limiti to'lgan bo'lishi mumkin. Yangi karta qo'shing."

        await status_callback(0, 6, "To'lovda xatolik", f"❌ {err_msg}", {"error": err_msg})
        return False, err_msg

    token = tok_res["token"]
    token_type = tok_res.get("type", "card")

    # 7. Telegram Payment Formani tasdiqlash
    # Agar Telegram to'lov formasi Customer Info (Full name) talab qilsa:
    requested_info_id = None
    try:
        inv_obj = getattr(payment_form, 'invoice', None)
        if inv_obj and getattr(inv_obj, 'name_requested', False):
            from telethon.tl.functions.payments import ValidateRequestedInfoRequest
            from telethon.tl.types import PaymentRequestedInfo
            logger.info(f"Telegram to'lovi uchun ism-familiya kiritilmoqda: '{final_acc_name}'")
            val_res = await temp_client(ValidateRequestedInfoRequest(
                invoice=input_inv,
                info=PaymentRequestedInfo(name=final_acc_name),
                save=True
            ))
            requested_info_id = getattr(val_res, 'id', None)
    except Exception as name_err:
        logger.warning(f"Ism-familiyani tasdiqlashda ogohlantirish: {name_err}")

    cred_data = json.dumps({"token": token, "type": token_type})
    credentials = InputPaymentCredentials(data=DataJSON(data=cred_data), save=True)

    try:
        if not temp_client.is_connected():
            await asyncio.wait_for(temp_client.connect(), timeout=8.0)
        pay_result = await asyncio.wait_for(temp_client(SendPaymentFormRequest(
            form_id=form_id,
            invoice=input_inv,
            credentials=credentials,
            requested_info_id=requested_info_id
        )), timeout=25.0)
        
        if isinstance(pay_result, PaymentVerificationNeeded):
            # 3D Secure / Bank SMS tasdiqlash talab qilindi
            v_url = pay_result.url
            logger.info(f"3D-Secure talab qilindi: {v_url}")
            await status_callback(
                5, 6, "Bankdan SMS kod kutilmoqda",
                (
                    f"📩 <b>Bankdan SMS kod yuborildi!</b>\n\n"
                    f"💳 To'lovni yakunlash uchun pastdagi <b>«🔐 3D-Secure orqali tasdiqlash»</b> tugmasini bosing va bankdan kelgan SMS kodni kiriting.\n\n"
                    f"⏳ <i>Kutilmoqda (5 daqiqa)...</i>"
                ),
                {"needs_sms": True, "verification_url": v_url, "order_id": order_id}
            )

            # Foydalanuvchi havola orqali SMS kodni kiritishini kutamiz (300 soniya / 5 daqiqa)
            verified = False
            from telethon.tl.functions.users import GetUsersRequest
            from telethon.tl.types import InputUserSelf

            for _ in range(600):
                if order_data.get("is_cancelled"):
                    raise asyncio.CancelledError()
                if order_data.get("payment_verified"):
                    verified = True
                    break

                await asyncio.sleep(0.5)
                try:
                    if not temp_client.is_connected():
                        await asyncio.wait_for(temp_client.connect(), timeout=8.0)
                    
                    # 1. Telegram serveridan to'g'ridan-to'g'ri yangilangan Premium holatini so'rash
                    try:
                        fresh_users = await asyncio.wait_for(temp_client(GetUsersRequest([InputUserSelf()])), timeout=5.0)
                        if fresh_users and getattr(fresh_users[0], 'premium', False):
                            logger.info("✅ 3D-Secure muvaffaqiyatli yakunlandi! fresh_users[0].premium == True")
                            verified = True
                            break
                    except Exception:
                        pass

                    # 2. Shuningdek @PremiumBot xabarlarini tekshirish
                    p_msgs = await asyncio.wait_for(temp_client.get_messages(prem_bot_entity, limit=2), timeout=5.0)
                    for pm in p_msgs:
                        p_txt = getattr(pm, 'text', '') or ''
                        if any(w in p_txt.lower() for w in [
                            'rahmat', 'thank', 'faollashtirildi', 'activated', 'receipt', 
                            'чек', 'спасибо', 'оплат', 'получили', 'действует', 'подписка'
                        ]):
                            logger.info(f"✅ @PremiumBot to'lovni tasdiqladi: {p_txt[:50]}")
                            verified = True
                            break
                    if verified:
                        break
                except Exception as chk_err:
                    logger.debug(f"3DS tekshiruvida ogohlantirish: {chk_err}")

            if not verified:
                try:
                    await temp_client.disconnect()
                except Exception:
                    pass
                database.update_order_status(order_id, 'cancelled')
                await userbot.click_diller_button(diller_bot, diller_msg_id, "Freeze")
                await status_callback(0, 6, "SMS tasdiqlanmadi", "❌ <b>Bank SMS kodi kiritilmadi yoki to'lov tasdiqlanmadi (vaqt tugadi).</b>\n\nBuyurtma bekor qilindi.", {"error": "3ds_timeout", "order_id": order_id})
                return False, "3D-Secure SMS tasdiqlanmadi"

        elif isinstance(pay_result, PaymentResult):
            logger.info("Telegram to'lovi to'g'ridan-to'g'ri muvaffaqiyatli o'tdi!")

    except Exception as e:
        logger.error(f"SendPaymentFormRequest xatosi: {e}")
        try:
            await temp_client.disconnect()
        except Exception:
            pass
        database.update_order_status(order_id, 'cancelled')
        await userbot.click_diller_button(diller_bot, diller_msg_id, "Freeze")
        
        err_str = str(e)
        if "PAYMENT_FAILED" in err_str:
            user_msg = (
                "❌ <b>Bank tomonidan to'lov rad etildi (PAYMENT_FAILED)!</b>\n\n"
                "💡 <b>Kuzatilishi mumkin bo'lgan sabablar:</b>\n"
                "1️⃣ <b>Mablag' yetarli emas:</b> Karta hisobida yetarli mablag' (kamida 12$ yoki unga teng summa) mavjudligini tekshiring;\n"
                "2️⃣ <b>Internet to'lovlari o'chirilgan:</b> Bank mobil ilovasida (Alliance Mobile) internet xaridlari yoqilganligini tekshiring;\n"
                "3️⃣ <b>Kunlik limit:</b> Kartaning internet operatsiyalari uchun limiti kam bo'lishi mumkin.\n\n"
                "Iltimos, kartangizni tekshirib qayta urinib ko'ring yoki boshqa karta qo'shing."
            )
        else:
            user_msg = f"❌ To'lovni amalga oshirib bo'lmadi: {err_str}"

        await status_callback(0, 6, "To'lovda xatolik", user_msg, {"error": str(e), "order_id": order_id})
        return False, str(e)

    # 8. Muvaffaqiyat! @PremiumBot da /stop bosish (Avto-uzaytirishni bekor qilish)
    await status_callback(
        6, 6, "Premium olindi, yakunlanmoqda",
        f"🎉 <b>Telegram Premium muvaffaqiyatli sotib olindi!</b>\n\n🛑 @PremiumBot da avto-uzaytirish bekor qilinmoqda (/stop)...",
        {"phone": phone, "order_id": order_id}
    )

    try:
        if not temp_client.is_connected():
            await asyncio.wait_for(temp_client.connect(), timeout=8.0)
        
        sent_stop = await asyncio.wait_for(temp_client.send_message(prem_bot_entity, '/stop'), timeout=10.0)
        stop_msg_id = getattr(sent_stop, 'id', 0)
        logger.info(f"🛑 @PremiumBot ga /stop yuborildi (msg_id={stop_msg_id}).")

        # 1-bosqich: @PremiumBot dan javob kutish va "Да, отменить продление" tugmasini bosish
        step1_clicked = False
        last_resp_id = stop_msg_id
        for _ in range(25):  # 25 * 0.4s = 10 soniyagacha kutamiz
            await asyncio.sleep(0.4)
            try:
                msgs = await asyncio.wait_for(temp_client.get_messages(prem_bot_entity, limit=4), timeout=5.0)
                target_msg = None
                for m in msgs:
                    if not getattr(m, 'out', False):
                        target_msg = m
                        break
                
                if target_msg:
                    t_text = (getattr(target_msg, 'text', '') or '').lower()
                    # Agar obuna allaqachon bekor qilingan bo'lsa:
                    if any(w in t_text for w in ["нет активной", "no active", "активной подписки", "faol obuna yo'q"]):
                        logger.info("ℹ️ @PremiumBot: Faol avto-uzaytirish obunasi yo'q.")
                        step1_clicked = True
                        break

                    # Tugmalarni tekshirish (ReplyKeyboardMarkup yoki Inline)
                    if target_msg.buttons:
                        for row in target_msg.buttons:
                            for btn in row:
                                b_txt = (getattr(btn, 'text', '') or '').lower()
                                if any(w in b_txt for w in ["отменить продление", "отменить", "stop renewal", "cancel renewal", "bekor qilish"]):
                                    logger.info(f"🛑 @PremiumBot 1-bosqich: '{btn.text}' tugmasi bosilmoqda...")
                                    try:
                                        await asyncio.wait_for(btn.click(), timeout=4.0)
                                    except Exception:
                                        await temp_client.send_message(prem_bot_entity, btn.text)
                                    last_resp_id = target_msg.id
                                    step1_clicked = True
                                    break
                            if step1_clicked:
                                break
                    
                    # Agar tugma topilmasa lekin xabarda "отказаться от автоматического продления" bo'lsa
                    if not step1_clicked and any(w in t_text for w in ["отказаться от", "действующая подписка", "автопродлен"]):
                        logger.info("🛑 @PremiumBot ga 'Да, отменить продление' matni yuborilmoqda...")
                        await temp_client.send_message(prem_bot_entity, "Да, отменить продление")
                        last_resp_id = target_msg.id
                        step1_clicked = True
                        break

                if step1_clicked:
                    break
            except Exception as e_p1:
                logger.debug(f"Stop 1-bosqich kutilmoqda: {e_p1}")

        # 2-bosqich: Sababni tanlash ("Слишком дорого")
        step2_clicked = False
        if step1_clicked:
            for _ in range(25):  # 25 * 0.4s = 10 soniyagacha kutamiz
                await asyncio.sleep(0.4)
                try:
                    msgs = await asyncio.wait_for(temp_client.get_messages(prem_bot_entity, limit=4), timeout=5.0)
                    target_msg2 = None
                    for m in msgs:
                        if not getattr(m, 'out', False) and m.id > last_resp_id:
                            target_msg2 = m
                            break
                        elif not getattr(m, 'out', False):
                            m_txt = (getattr(m, 'text', '') or '').lower()
                            if any(w in m_txt for w in ["причину", "отказа", "улучшить", "дорого", "reason"]):
                                target_msg2 = m
                                break
                    
                    if target_msg2:
                        t2_text = (getattr(target_msg2, 'text', '') or '').lower()
                        # Tugmalarni tekshirish
                        if target_msg2.buttons:
                            for row in target_msg2.buttons:
                                for btn in row:
                                    b_txt = (getattr(btn, 'text', '') or '').lower()
                                    if any(w in b_txt for w in ["слишком дорого", "дорого", "too expensive", "expensive", "qimmat"]):
                                        logger.info(f"🛑 @PremiumBot 2-bosqich: '{btn.text}' tugmasi bosilmoqda...")
                                        try:
                                            await asyncio.wait_for(btn.click(), timeout=4.0)
                                        except Exception:
                                            await temp_client.send_message(prem_bot_entity, btn.text)
                                        step2_clicked = True
                                        break
                                if step2_clicked:
                                    break

                        if not step2_clicked and any(w in t2_text for w in ["причину", "отказа", "улучшить", "дорого"]):
                            logger.info("🛑 @PremiumBot ga 'Слишком дорого' matni yuborilmoqda...")
                            await temp_client.send_message(prem_bot_entity, "Слишком дорого")
                            step2_clicked = True
                            break

                    if step2_clicked:
                        break
                except Exception as e_p2:
                    logger.debug(f"Stop 2-bosqich kutilmoqda: {e_p2}")

        await asyncio.sleep(0.5)
        logger.info("✅ @PremiumBot da avto-uzaytirish to'liq bekor qilindi (/stop -> Да, отменить продление -> Слишком дорого).")
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
                {"phone": phone, "order_id": order_id}
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

    # Guruh/kanalga to'lov logini yuborish
    asyncio.create_task(channel_logger.send_payment_log(user_id, phone, reward_amount="Telegram Premium (1 oy)"))

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

