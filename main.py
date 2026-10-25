import asyncio
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')
import logging
import math
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters.command import Command
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton
)
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

import config
import database
import userbot
import auto_buyer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher()

# Faol taymer vazifalari (order_id -> asyncio.Task)
active_timers = {}

# Foydalanuvchi kartalari FSM
class CardStates(StatesGroup):
    waiting_card_number = State()
    waiting_card_exp = State()
    waiting_card_cvv = State()
    waiting_card_name = State()

# Admin FSM holatlari
class AdminStates(StatesGroup):
    waiting_for_ub_phone = State()
    waiting_for_ub_code = State()
    waiting_for_ub_password = State()
    
    waiting_for_any_bot_uname = State()
    waiting_for_new_admin_id = State()
    waiting_for_setting_value = State()
    
    waiting_for_broadcast_msg = State()
    waiting_for_broadcast_limit = State()
    
    waiting_for_search_user_id = State()
    waiting_for_edit_user_balance = State()

# ==========================================
# FOYDALANUVCHI INTERFEYSI (UI)
# ==========================================

from aiogram.types import ReplyKeyboardRemove

def get_user_inline_keyboard():
    rows = []
    webapp_url = database.get_setting("webapp_url", "").strip()
    if webapp_url:
        from aiogram.types import WebAppInfo
        rows.append([
            InlineKeyboardButton(
                text="Ilovani ochish (Mini App)",
                web_app=WebAppInfo(url=webapp_url),
                style="success",
                icon_custom_emoji_id="5839394435644788150"
            )
        ])
    rows.extend([
        [
            InlineKeyboardButton(text="Avto olish (Robot)", callback_data="user_get_number_auto", style="primary", icon_custom_emoji_id="5407025283456835913"),
            InlineKeyboardButton(text="Qo'lda olish (Manual)", callback_data="user_get_number_manual", style="primary", icon_custom_emoji_id="5427009714745517609")
        ],
        [
            InlineKeyboardButton(text="Mening kartalarim", callback_data="user_my_cards", style="success", icon_custom_emoji_id="5190953888341046662"),
            InlineKeyboardButton(text="Premiumlarim", callback_data="user_premiums", style="success", icon_custom_emoji_id="5839394435644788150")
        ],
        [
            InlineKeyboardButton(text="Statistikam", callback_data="user_stats", style="primary", icon_custom_emoji_id="5431577498364158238"),
            InlineKeyboardButton(text="Tarixim", callback_data="user_history", style="primary", icon_custom_emoji_id="5440621591387980068")
        ],
        [
            InlineKeyboardButton(text="Pul yechish", callback_data="user_withdraw", style="success", icon_custom_emoji_id="5190953888341046662"),
            InlineKeyboardButton(text="Qo'llanma", callback_data="user_manual", style="primary", icon_custom_emoji_id="5226512880362332956")
        ],
        [
            InlineKeyboardButton(text="Top Reyting", callback_data="user_top", style="primary", icon_custom_emoji_id="5409008750893734809")
        ]
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def get_welcome_text(full_name: str, premiums: int):
    reward_val = database.get_setting("reward_per_account", "40,000")
    return (
        f"<tg-emoji emoji-id='5204340545488428414'>👋</tg-emoji> Xush kelibsiz, <b>{full_name}</b>!\n\n"
        f"<tg-emoji emoji-id='5839394435644788150'>⭐</tg-emoji> Premiumlar: <b>{premiums} ta</b>\n"
        f"💰 Mukofot: <b>{reward_val} so'm</b> / har bir premium uchun\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🎯 <b>Bizda 2 xil olish usuli mavjud:</b>\n\n"
        f"⚡️ <b>«Avto olish (Robot)»:</b> Kartangizni kiritasiz, bot hamma ishni o'zi avtomatik to'lab faollashtiradi!\n\n"
        f"📱 <b>«Qo'lda olish (Manual)»:</b> Raqam va SMS kod olasiz, Telegram ilovangizda o'zingiz kirib premiumni faollashtirasiz va «Oldim»ni bosasiz!\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"❓ Qo'shimcha ma'lumot — «Qo'llanma» tugmasida"
    )

def get_back_to_menu_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Menyu", callback_data="back_to_main_menu", style="primary", icon_custom_emoji_id="5260244316554562171")]
    ])

def get_manual_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Qaysi kartadan olsa bo'ladi?", callback_data="show_cards_info", style="success", icon_custom_emoji_id="5190953888341046662")],
        [InlineKeyboardButton(text="Menyu", callback_data="back_to_main_menu", style="primary", icon_custom_emoji_id="5260244316554562171")]
    ])

def get_cards_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Qo'llanmaga qaytish", callback_data="back_to_manual", style="primary", icon_custom_emoji_id="5226512880362332956")],
        [InlineKeyboardButton(text="Menyu", callback_data="back_to_main_menu", style="primary", icon_custom_emoji_id="5260244316554562171")]
    ])

def get_order_keyboard(order_id: int, has_code: bool = False):
    if not has_code:
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="Get Code", callback_data=f"get_code_{order_id}", style="primary", icon_custom_emoji_id="5330115548900501467"),
                InlineKeyboardButton(text="Muzlatish", callback_data=f"freeze_{order_id}", style="danger", icon_custom_emoji_id="5404728536810398694")
            ],
            [
                InlineKeyboardButton(text="Bekor qilish", callback_data=f"cancel_{order_id}", style="danger", icon_custom_emoji_id="5454350746407419714")
            ]
        ])
    else:
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="Oldim", callback_data=f"received_{order_id}", style="success", icon_custom_emoji_id="5427009714745517609"),
                InlineKeyboardButton(text="Qayta kod", callback_data=f"get_code_{order_id}", style="primary", icon_custom_emoji_id="5226702984204797593")
            ],
            [
                InlineKeyboardButton(text="Muzlatish", callback_data=f"freeze_{order_id}", style="danger", icon_custom_emoji_id="5404728536810398694"),
                InlineKeyboardButton(text="Bekor qilish", callback_data=f"cancel_{order_id}", style="danger", icon_custom_emoji_id="5454350746407419714")
            ]
        ])

def render_progress_bar(remaining_seconds: int, total_seconds: int = 300) -> str:
    total_blocks = 8
    passed = max(0, total_seconds - remaining_seconds)
    filled = math.floor((passed / total_seconds) * total_blocks)
    filled = min(total_blocks, max(0, filled))
    empty = total_blocks - filled
    return "█" * filled + "░" * empty

# ==========================================
# /start VA ASOSIY MENYU
# ==========================================

async def cleanup_reply_keyboard(message: types.Message):
    try:
        del_msg = await message.answer("🔄", reply_markup=ReplyKeyboardRemove())
        await del_msg.delete()
    except Exception:
        pass

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    full_name = message.from_user.full_name or "Foydalanuvchi"
    is_adm = database.is_admin(user_id, config.ADMIN_ID)

    # Eski pastki tugmalarni tozalash
    await cleanup_reply_keyboard(message)

    status, premiums = database.register_or_get_user(user_id, username, full_name, is_admin_user=is_adm)

    if status == 'banned':
        await message.answer("❌ Kechirasiz, siz botdan bloklangansiz.")
        return

    if status == 'pending':
        await message.answer(
            "⏳ <b>Assalomu alaykum!</b>\n\n"
            "Botdan foydalanish uchun so'rovingiz qabul qilindi.\n"
            "Iltimos, admin tasdiqlashini kuting...",
            parse_mode="HTML"
        )
        admin_text = (
            f"🔔 <b>Yangi foydalanuvchi so'rovi!</b>\n\n"
            f"👤 Ism: <b>{full_name}</b>\n"
            f"🔗 Username: @{username if username else 'yoq'}\n"
            f"🆔 ID: <code>{user_id}</code>\n\n"
            f"Ruxsat berasizmi?"
        )
        admin_markup = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"pending_appr_{user_id}", style="success", icon_custom_emoji_id="5281024210146201465"),
                InlineKeyboardButton(text="❌ Rad etish", callback_data=f"pending_rejc_{user_id}", style="danger", icon_custom_emoji_id="5278525655871424505")
            ]
        ])
        try:
            await bot.send_message(chat_id=config.ADMIN_ID, text=admin_text, parse_mode="HTML", reply_markup=admin_markup)
        except Exception:
            pass
        return

    text = get_welcome_text(full_name, premiums)
    await message.answer(text, parse_mode="HTML", reply_markup=get_user_inline_keyboard())

@dp.callback_query(F.data == "back_to_main_menu")
async def callback_back_to_main(call: types.CallbackQuery):
    user_id = call.from_user.id
    username = call.from_user.username or ""
    full_name = call.from_user.full_name or "Foydalanuvchi"
    _, premiums = database.register_or_get_user(user_id, username, full_name)

    text = get_welcome_text(full_name, premiums)
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=get_user_inline_keyboard())

# ==========================================
# KANALLARGA LOG YUBORISH (1 va 2-rasmlar)
# ==========================================

async def send_channel_number_log(user_id: int, user_display: str, phone: str, diller_bot: str):
    ch = database.get_setting('channel_number_logs', '').strip()
    if not ch:
        return
    bot_name = diller_bot.replace('@', '')
    text = (
        f"📱 <b>Number olindi</b>\n\n"
        f"👤 User: {user_display} (<code>{user_id}</code>)\n"
        f"📞 Number: <code>{phone}</code>\n"
        f"🤖 Bot: {bot_name}"
    )
    try:
        target_chat = int(ch) if (ch.startswith('-') and ch[1:].isdigit()) or ch.isdigit() else ch
        await bot.send_message(chat_id=target_chat, text=text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Kanalga number log yuborishda xatolik: {e}")

async def send_channel_payment_log(user_id: int, user_display: str, phone: str, reward_amount: str = "40 so'm"):
    ch = database.get_setting('channel_payment_logs', '').strip()
    if not ch:
        return
    text = (
        f"✅ <b>Yangi premium!</b>\n\n"
        f"👤 User: {user_display} (<code>{user_id}</code>)\n"
        f"📞 Number: <code>{phone}</code>\n"
        f"💰 Mukofot: <b>{reward_amount}</b>"
    )
    try:
        target_chat = int(ch) if (ch.startswith('-') and ch[1:].isdigit()) or ch.isdigit() else ch
        await bot.send_message(chat_id=target_chat, text=text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Kanalga to'lov log yuborishda xatolik: {e}")

# ==========================================
# NUMBER OLISH VA TAYMER
# ==========================================

async def run_order_timer(chat_id: int, message_id: int, order_id: int, phone: str, total_seconds: int = 300):
    remaining = total_seconds
    while remaining > 0:
        await asyncio.sleep(10)
        remaining -= 10

        order_info = database.get_order(order_id)
        if not order_info or order_info[6] != 'active':
            return

        minutes = remaining // 60
        seconds = remaining % 60
        time_str = f"00:{minutes:02d}:{seconds:02d}"
        pbar = render_progress_bar(remaining, total_seconds)

        code_text = order_info[3]
        pass_text = order_info[10] if len(order_info) > 10 else None

        if code_text:
            text = (
                f"📱 <b>Sizning numberingiz:</b>\n\n"
                f"📞 <b>Number:</b> <code>{phone}</code>\n"
                f"🔑 <b>Kod:</b> <code>{code_text}</code>\n"
            )
            if pass_text:
                text += f"🔐 <b>Parol:</b> <code>{pass_text}</code>\n"
            text += (
                f"\n⏱ <b>Qolgan vaqt:</b> {time_str} [{pbar}]\n\n"
                f"✅ Endi Telegram Premium'ni faollashtiring.\n"
                f"So'ng «✅ Oldim» tugmasini bosing!\n"
                f"🧊 Raqam ishlamasa — numberni muzlatish"
            )
            markup = get_order_keyboard(order_id, has_code=True)
        else:
            text = (
                f"📱 <b>Sizning numberingiz:</b>\n\n"
                f"📞 <b>Number:</b> <code>{phone}</code>\n\n"
                f"⏱ <b>Qolgan vaqt:</b> {time_str} [{pbar}]\n\n"
                f"📨 Code olish uchun «Get Code» tugmasini bosing!\n"
                f"🧊 Raqam ishlamasa — numberni muzlatish\n"
                f"⚠️ <i>5 daqiqa ichida bosilmasa raqam qaytariladi</i>"
            )
            markup = get_order_keyboard(order_id, has_code=False)

        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                parse_mode="HTML",
                reply_markup=markup
            )
        except Exception:
            pass

    order_info = database.get_order(order_id)
    if order_info and order_info[6] == 'active':
        database.update_order_status(order_id, 'expired')
        diller_bot = order_info[4]
        diller_msg_id = order_info[5]
        if diller_msg_id:
            asyncio.create_task(userbot.click_diller_button(diller_bot, diller_msg_id, "Cancel"))

        expired_text = (
            f"⏰ <b>Vaqt tugadi!</b>\n\n"
            f"📞 Raqam: <code>{phone}</code>\n"
            f"⚠️ 5 daqiqa ichida ishlatilmagani sababli raqam bekor qilindi va qaytarildi."
        )
        try:
            await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=expired_text, parse_mode="HTML")
        except Exception:
            pass

# ==========================================
# FOYDALANUVCHI KARTALARI BOSHQARUVI
# ==========================================

@dp.callback_query(F.data == "user_my_cards")
async def show_user_cards_menu(call: types.CallbackQuery):
    user_id = call.from_user.id
    cards = database.get_user_cards(user_id)
    
    text = (
        "💳 <b>Mening to'lov kartalarim</b>\n\n"
        "Ushbu kartalar @PremiumBot orqali Telegram Premium'ni avtomatik sotib olish uchun ishlatiladi.\n"
        "⚠️ <i>Xavfsizlik qoidasi: 1 ta kartadan ko'pi bilan 3 tagacha premium olish mumkin.</i>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
    )
    
    keyboard_buttons = []
    if not cards:
        text += "<i>Hozircha saqlangan kartalaringiz yo'q.</i>\n"
    else:
        for idx, c in enumerate(cards, 1):
            if len(c) >= 11:
                c_id, c_num, exp_m, exp_y, cvv, c_name, used_c, max_l, c_status, is_def, _ = c[:11]
            else:
                c_id, c_num, exp_m, exp_y, cvv, used_c, max_l, c_status, is_def, _ = c[:10]
                c_name = ""
            mask_num = f"**** {c_num[-4:]}" if len(c_num) >= 4 else "****"
            def_str = " (Asosiy ⭐️)" if is_def else ""
            status_icon = "✅ Faol" if c_status == 'active' and used_c < max_l else "❌ Limit to'lgan"
            name_info = f"   • Egasi: <b>{c_name}</b>\n" if c_name else ""
            text += (
                f"<b>{idx}. 💳 {mask_num}</b>{def_str}\n"
                f"{name_info}"
                f"   • Muddati: {exp_m}/{exp_y}\n"
                f"   • Ishlatildi: <b>{used_c}/{max_l} ta</b>\n"
                f"   • Holati: {status_icon}\n\n"
            )
            keyboard_buttons.append([
                InlineKeyboardButton(text=f"🗑 {mask_num} ni o'chirish", callback_data=f"del_card_{c_id}")
            ])

    keyboard_buttons.append([
        InlineKeyboardButton(text="➕ Yangi karta qo'shish", callback_data="add_new_card", style="success")
    ])
    keyboard_buttons.append([
        InlineKeyboardButton(text="Menyu", callback_data="back_to_main_menu", style="primary")
    ])

    await call.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_buttons))

@dp.callback_query(F.data == "add_new_card")
async def start_add_card_flow(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(CardStates.waiting_card_number)
    text = (
        "💳 <b>Yangi to'lov kartasini qo'shish</b>\n\n"
        "Iltimos, kartangizning <b>16 xonali raqamini</b> yuboring:\n"
        "<i>(Masalan: 4292 1500 0000 0000)</i>\n\n"
        "💡 <b>Tavsiya etiladi:</b> Anorbank, TBC, Kapitalbank virtual Visa/Mastercard kartalari."
    )
    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Bekor qilish", callback_data="cancel_card_add")]
    ])
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=cancel_kb)

@dp.callback_query(F.data == "cancel_card_add")
async def cancel_card_add_cb(call: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await show_user_cards_menu(call)

@dp.message(CardStates.waiting_card_number)
async def process_card_number_input(message: types.Message, state: FSMContext):
    clean_num = "".join(filter(str.isdigit, message.text or ""))
    if len(clean_num) != 16:
        await message.answer("❌ <b>Karta raqami noto'g'ri!</b>\n16 ta raqam bo'lishi kerak. Qaytadan kiriting:")
        return

    await state.update_data(card_number=clean_num)
    await state.set_state(CardStates.waiting_card_exp)
    await message.answer(
        "📅 <b>Kartaning amal qilish muddatini kiriting:</b>\n"
        "<i>(Masalan: 12/28 yoki 1228)</i>"
    )

@dp.message(CardStates.waiting_card_exp)
async def process_card_exp_input(message: types.Message, state: FSMContext):
    raw = message.text.replace("/", "").replace(" ", "").strip()
    digits = "".join(filter(str.isdigit, raw))
    if len(digits) != 4:
        await message.answer("❌ <b>Format noto'g'ri!</b>\nOy va yilni 4 ta raqam shaklida kiriting (masalan: 12/28):")
        return

    month = digits[:2]
    year = digits[2:]
    if int(month) < 1 or int(month) > 12:
        await message.answer("❌ <b>Oy noto'g'ri (01 dan 12 gacha)!</b> Qaytadan kiriting:")
        return

    await state.update_data(exp_month=month, exp_year=year)
    await state.set_state(CardStates.waiting_card_cvv)
    await message.answer(
        "🔐 <b>Kartaning orqa tomonidagi 3 xonali CVV/CVC kodini kiriting:</b>\n"
        "<i>(Masalan: 123)</i>"
    )

@dp.message(CardStates.waiting_card_cvv)
async def process_card_cvv_input(message: types.Message, state: FSMContext):
    cvv = "".join(filter(str.isdigit, message.text or "")).strip()
    if len(cvv) != 3:
        await message.answer("❌ <b>CVV kod 3 ta raqam bo'lishi kerak!</b> Qaytadan kiriting:")
        return

    await state.update_data(cvv=cvv)
    await state.set_state(CardStates.waiting_card_name)
    await message.answer(
        "👤 <b>Karta egasining to'liq Ism va Familiyasini kiriting:</b>\n\n"
        "<i>(Masalan: Eshmatov Toshmat yoki Toshmat Eshmatov)</i>\n\n"
        "⚠️ <b>Muhim talab:</b> Qisqartma (M.M yoki M. Eshmatov) shaklida emas, to'liq so'zlar bilan yozilishi shart!"
    )

@dp.message(CardStates.waiting_card_name)
async def process_card_name_input(message: types.Message, state: FSMContext):
    raw_name = (message.text or "").strip()
    
    # Qisqartmalarni (nuqtali) tekshirish
    if "." in raw_name:
        await message.answer(
            "❌ <b>Qisqartirilgan format (M.M yoki M. Eshmatov) qabul qilinmaydi!</b>\n\n"
            "Iltimos, ism va familiyangizni nuqtasiz, to'liq so'zlar bilan yozing.\n"
            "<i>To'g'ri misol:</i> <b>Eshmatov Toshmat</b>\n\n"
            "Qaytadan kiriting:"
        )
        return

    parts = [p for p in raw_name.split() if p]
    if len(parts) < 2:
        await message.answer(
            "❌ <b>Ism va familiya to'liq emas!</b>\n\n"
            "Iltimos, ham ismingizni, ham familiyangizni to'liq kiriting (kamida 2 ta so'z).\n"
            "<i>Misol:</i> <b>Eshmatov Toshmat</b>\n\n"
            "Qaytadan kiriting:"
        )
        return

    for p in parts:
        if len(p) < 2:
            await message.answer(
                "❌ <b>Ism yoki familiya 1 ta harfdan iborat bo'lishi mumkin emas!</b>\n"
                "Iltimos, to'liq so'zlar bilan kiriting (Masalan: <b>Eshmatov Toshmat</b>):"
            )
            return

    clean_cardholder_name = " ".join(parts).title()

    data = await state.get_data()
    card_number = data["card_number"]
    exp_month = data["exp_month"]
    exp_year = data["exp_year"]
    cvv = data["cvv"]

    card_id = database.add_user_card(
        user_id=message.from_user.id,
        card_number=card_number,
        exp_month=exp_month,
        exp_year=exp_year,
        cvv=cvv,
        cardholder_name=clean_cardholder_name,
        max_limit=3
    )
    await state.clear()

    mask_num = f"**** {card_number[-4:]}"
    success_text = (
        f"✅ <b>Karta muvaffaqiyatli saqlandi!</b>\n\n"
        f"💳 <b>Karta:</b> {mask_num}\n"
        f"👤 <b>Karta egasi:</b> {clean_cardholder_name}\n"
        f"📅 <b>Muddati:</b> {exp_month}/{exp_year}\n"
        f"⭐️ <b>Limit:</b> 3 tagacha premium olish mumkin\n\n"
        f"Endi «Avto olish (Robot)» tugmasini bosishingiz mumkin!"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Avto olish (Robot)", callback_data="user_get_number_auto", style="primary")],
        [InlineKeyboardButton(text="Mening kartalarim", callback_data="user_my_cards", style="success")],
        [InlineKeyboardButton(text="Menyu", callback_data="back_to_main_menu")]
    ])
    await message.answer(success_text, parse_mode="HTML", reply_markup=kb)

@dp.callback_query(F.data.startswith("del_card_"))
async def delete_card_cb(call: types.CallbackQuery):
    card_id = int(call.data.split("_")[2])
    database.delete_user_card(card_id, call.from_user.id)
    await call.answer("Karta o'chirildi! 🗑", show_alert=True)
    await show_user_cards_menu(call)

# ==========================================
# 1. AVTO-NUMBER VA PREMIUM OLISH (ROBOT)
# ==========================================

@dp.callback_query(F.data == "user_get_number_auto")
@dp.message(F.text == "⚡️ Avto olish (Robot)")
@dp.message(F.text == "📱 Number olish (Avto)")
async def handle_get_number_auto(event: types.Message | types.CallbackQuery):
    user_id = event.from_user.id
    is_callback = isinstance(event, types.CallbackQuery)
    if not is_callback:
        await cleanup_reply_keyboard(event)

    active_order = database.get_active_order_for_user(user_id)
    if active_order:
        warn_text = (
            f"⚠️ Sizda allaqachon faol raqam mavjud: <code>{active_order[2]}</code>\n"
            f"Iltimos, avval ushbu raqamni yakunlang yoki bekor qiling."
        )
        if is_callback:
            await event.message.edit_text(warn_text, parse_mode="HTML", reply_markup=get_back_to_menu_keyboard())
        else:
            await event.answer(warn_text, parse_mode="HTML", reply_markup=get_back_to_menu_keyboard())
        return

    # Faol to'lov kartasini tekshirish
    active_card = database.get_active_card_for_user(user_id)
    if not active_card:
        user_cards = database.get_user_cards(user_id)
        if user_cards:
            text = (
                "⚠️ <b>Barcha saqlangan kartalaringiz limiti to'lgan (3/3 ta)!</b>\n\n"
                "Telegram va to'lov xavfsizligi uchun 1 ta kartadan ko'pi bilan 3 ta premium olib bo'ladi.\n"
                "Iltimos, «💳 Mening kartalarim» bo'limidan yangi karta qo'shing."
            )
        else:
            text = (
                "💳 <b>Avval to'lov kartangizni qo'shing!</b>\n\n"
                "Robot orqali to'lovni avtomatik amalga oshirish uchun kartangiz kerak bo'ladi.\n"
                "<i>(1 ta kartadan 3 martagacha premium olish mumkin. Virtual Visa/Mastercard tavsiya etiladi).</i>"
            )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Karta qo'shish", callback_data="add_new_card", style="success")],
            [InlineKeyboardButton(text="📱 Qo'lda olishga o'tish", callback_data="user_get_number_manual", style="primary")],
            [InlineKeyboardButton(text="Menyu", callback_data="back_to_main_menu")]
        ])
        if is_callback:
            await event.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        else:
            await event.answer(text, parse_mode="HTML", reply_markup=kb)
        return

    card_num = active_card[1]
    mask_num = f"**** {card_num[-4:]}"
    used_c = active_card[5]
    max_l = active_card[6]

    start_text = (
        f"🚀 <b>Avto-Premium jarayoni boshlanmoqda...</b>\n\n"
        f"💳 <b>To'lov kartasi:</b> <code>{mask_num}</code> (Ishlatildi: {used_c}/{max_l})\n"
        f"⏳ Iltimos kuting, yangi raqam qidirilmoqda..."
    )
    if is_callback:
        status_msg = await event.message.edit_text(start_text, parse_mode="HTML")
    else:
        status_msg = await event.answer(start_text, parse_mode="HTML")

    async def update_status(step_num: int, total_steps: int, title: str, text: str, extra: dict):
        step_header = f"[{step_num}/{total_steps}]" if step_num > 0 else "⚠️"
        full_text = f"⚡️ <b>AVTO-PREMIUM {step_header}</b>\n\n{text}"
        
        kb = None
        if extra.get("error") or extra.get("completed"):
            kb = get_back_to_menu_keyboard()
        elif extra.get("needs_sms") and extra.get("verification_url"):
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔗 3D-Secure orqali tasdiqlash", url=extra["verification_url"])],
                [InlineKeyboardButton(text="Menyu", callback_data="back_to_main_menu")]
            ])

        try:
            await status_msg.edit_text(full_text, parse_mode="HTML", reply_markup=kb)
        except Exception:
            pass

    asyncio.create_task(auto_buyer.run_auto_purchase_flow(user_id, active_card, update_status))


# ==========================================
# 2. QO'LDA NUMBER VA PREMIUM OLISH (MANUAL)
# ==========================================

@dp.callback_query(F.data == "user_get_number_manual")
@dp.callback_query(F.data == "user_get_number")
@dp.message(F.text == "📱 Qo'lda olish (Manual)")
@dp.message(F.text == "📱 Number olish")
@dp.message(Command("getNumber"))
async def handle_get_number_manual(event: types.Message | types.CallbackQuery):
    user_id = event.from_user.id
    is_callback = isinstance(event, types.CallbackQuery)
    if not is_callback:
        await cleanup_reply_keyboard(event)

    active_order = database.get_active_order_for_user(user_id)
    if active_order:
        warn_text = (
            f"⚠️ Sizda allaqachon faol raqam mavjud: <code>{active_order[2]}</code>\n"
            f"Iltimos, avval ushbu raqamni yakunlang yoki bekor qiling."
        )
        if is_callback:
            await event.message.edit_text(warn_text, parse_mode="HTML", reply_markup=get_back_to_menu_keyboard())
        else:
            await event.answer(warn_text, parse_mode="HTML", reply_markup=get_back_to_menu_keyboard())
        return

    diller_bot = database.get_active_diller_bot()
    if not diller_bot:
        msg_text = "⚠️ Hozirda raqam olish xizmati vaqtincha to'xtatilgan. Birozdan so'ng urinib ko'ring."
        if is_callback:
            await event.message.edit_text(msg_text, parse_mode="HTML", reply_markup=get_back_to_menu_keyboard())
        else:
            await event.answer(msg_text, parse_mode="HTML", reply_markup=get_back_to_menu_keyboard())
        return

    if is_callback:
        wait_msg = await event.message.edit_text("⏳ <b>Yangi raqam qidirilmoqda, iltimos kuting...</b>", parse_mode="HTML")
    else:
        wait_msg = await event.answer("⏳ <b>Yangi raqam qidirilmoqda, iltimos kuting...</b>", parse_mode="HTML")

    phone, diller_msg_id, err = await userbot.request_number_from_diller(diller_bot)

    if not phone:
        await wait_msg.edit_text(
            "❌ <b>Hozirda bo'sh raqamlar mavjud emas.</b>\n\nIltimos, birozdan so'ng qayta urinib ko'ring.",
            parse_mode="HTML",
            reply_markup=get_back_to_menu_keyboard()
        )
        return

    order_id = database.create_order(user_id, phone, diller_bot, diller_msg_id, duration_seconds=300)

    # Kanalga number log yuborish
    user_disp = event.from_user.full_name or (f"@{event.from_user.username}" if event.from_user.username else str(user_id))
    asyncio.create_task(send_channel_number_log(user_id, user_disp, phone, diller_bot))

    pbar = render_progress_bar(300, 300)
    text = (
        f"📱 <b>Sizning numberingiz (Qo'lda olish):</b>\n\n"
        f"📞 <b>Number:</b> <code>+{phone}</code>\n\n"
        f"⏱ <b>Qolgan vaqt:</b> 00:04:59 [{pbar}]\n\n"
        f"1️⃣ Telegram ilovangizda ushbu raqamga kiring.\n"
        f"2️⃣ Kirish kodini olish uchun <b>«Get Code»</b> tugmasini bosing!\n"
        f"3️⃣ Akkauntga kirgach, <b>@PremiumBot</b> orqali premiumni faollashtiring.\n"
        f"4️⃣ Faollashtirgach <b>«Oldim»</b> tugmasini bosing!\n\n"
        f"🧊 <i>Raqam ishlamasa — «Muzlatish» bosing.</i>"
    )

    await wait_msg.edit_text(text, parse_mode="HTML", reply_markup=get_order_keyboard(order_id))

    timer_task = asyncio.create_task(
        run_order_timer(wait_msg.chat.id, wait_msg.message_id, order_id, phone, total_seconds=300)
    )
    active_timers[order_id] = timer_task


@dp.callback_query(F.data.startswith("get_code_"))
async def handle_callback_get_code(call: types.CallbackQuery):
    order_id = int(call.data.split("_")[2])
    order = database.get_order(order_id)
    if not order or order[6] != 'active':
        await call.answer("Buyurtma yakunlangan yoki bekor qilingan!", show_alert=True)
        return

    try:
        await call.answer("Kod so'ralmoqda...")
    except Exception:
        pass

    diller_bot = order[4]
    diller_msg_id = order[5]
    phone = order[2]

    success, result = await userbot.click_diller_button(diller_bot, diller_msg_id, "Get Code")

    if success:
        if isinstance(result, tuple):
            code_text, pass_text = result
        else:
            code_text, pass_text = result, None

        database.update_order_status(order_id, 'active', code=code_text, password=pass_text)
        new_text = (
            f"📱 <b>Sizning numberingiz:</b>\n\n"
            f"📞 <b>Number:</b> <code>{phone}</code>\n"
            f"🔑 <b>Kod:</b> <code>{code_text}</code>\n"
        )
        if pass_text:
            new_text += f"🔐 <b>Parol:</b> <code>{pass_text}</code>\n"
        new_text += (
            f"\n✅ Endi Telegram Premium'ni faollashtiring.\n"
            f"So'ng «✅ Oldim» tugmasini bosing!\n"
            f"🧊 Raqam ishlamasa — numberni muzlatish"
        )
        try:
            await call.message.edit_text(new_text, parse_mode="HTML", reply_markup=get_order_keyboard(order_id, has_code=True))
        except Exception:
            pass
    else:
        try:
            await call.answer(f"Xatolik: {result}", show_alert=True)
        except Exception:
            pass

@dp.callback_query(F.data.startswith("received_"))
async def handle_callback_received(call: types.CallbackQuery):
    order_id = int(call.data.split("_")[1])
    order = database.get_order(order_id)
    if not order or order[6] != 'active':
        await call.answer("Buyurtma faol emas!", show_alert=True)
        return

    diller_bot = order[4]
    diller_msg_id = order[5]
    phone = order[2]

    try:
        await call.answer("🔍 Telegram Premium tekshirilmoqda...", show_alert=False)
    except Exception:
        pass

    # Diller botidan Check premium orqali tekshirish
    is_premium, res_msg = await userbot.check_premium_from_diller(diller_bot, diller_msg_id)

    if not is_premium:
        try:
            await call.answer(f"❌ {res_msg}", show_alert=True)
        except Exception:
            pass
        return

    # Faqat diller botida muvaffaqiyatli tasdiqlanganda:
    if order_id in active_timers:
        active_timers[order_id].cancel()

    database.update_order_status(order_id, 'completed')

    # Kanalga to'lov log yuborish
    user_disp = call.from_user.full_name or (f"@{call.from_user.username}" if call.from_user.username else str(order[1]))
    reward_val = database.get_setting('reward_per_account', '40')
    asyncio.create_task(send_channel_payment_log(order[1], user_disp, phone, f"{reward_val} so'm"))

    text = (
        f"🎉 <b>Tabriklaymiz!</b>\n\n"
        f"📞 Raqam: <code>{phone}</code>\n"
        f"✅ Telegram Premium muvaffaqiyatli qabul qilindi!\n"
        f"⭐ «Premiumlarim» hisobingizga qo'shildi."
    )
    await call.message.edit_text(text, parse_mode="HTML")
    try:
        await call.answer("Muvaffaqiyatli tasdiqlandi! ✅", show_alert=True)
    except Exception:
        pass

@dp.callback_query(F.data.startswith("freeze_"))
async def handle_callback_freeze(call: types.CallbackQuery):
    order_id = int(call.data.split("_")[1])
    order = database.get_order(order_id)
    if not order or order[6] != 'active':
        await call.answer("Buyurtma faol emas!", show_alert=True)
        return

    if order_id in active_timers:
        active_timers[order_id].cancel()

    diller_bot = order[4]
    diller_msg_id = order[5]
    phone = order[2]

    if diller_msg_id:
        await userbot.click_diller_button(diller_bot, diller_msg_id, "Freeze")

    database.update_order_status(order_id, 'frozen')
    await call.message.edit_text(f"🧊 <b>Raqam muzlatildi (Freeze)!</b>\n\n📞 Raqam: <code>{phone}</code>\n\nRaqam qaytarib berildi.", parse_mode="HTML")
    await call.answer("Raqam muzlatildi 🧊", show_alert=True)

@dp.callback_query(F.data.startswith("cancel_"))
async def handle_callback_cancel(call: types.CallbackQuery):
    order_id = int(call.data.split("_")[1])
    order = database.get_order(order_id)
    if not order or order[6] != 'active':
        await call.answer("Buyurtma faol emas!", show_alert=True)
        return

    if order_id in active_timers:
        active_timers[order_id].cancel()

    diller_bot = order[4]
    diller_msg_id = order[5]
    phone = order[2]

    if diller_msg_id:
        await userbot.click_diller_button(diller_bot, diller_msg_id, "Cancel")

    database.update_order_status(order_id, 'cancelled')
    await call.message.edit_text(f"❌ <b>Raqam bekor qilindi!</b>\n\n📞 Raqam: <code>{phone}</code>", parse_mode="HTML")
    await call.answer("Raqam bekor qilindi ❌", show_alert=True)

# ==========================================
# USER TUGMALARI (PREMIUMLARIM, STATISTIKA... INLINE VA TEXT)
# ==========================================

@dp.callback_query(F.data == "user_premiums")
@dp.message(F.text == "⭐ Premiumlarim")
async def handle_user_premiums(event: types.Message | types.CallbackQuery):
    if isinstance(event, types.Message):
        await cleanup_reply_keyboard(event)
    user_id = event.from_user.id
    _, premiums = database.register_or_get_user(user_id, event.from_user.username or "", event.from_user.full_name or "")
    text = f"⭐ <b>Premiumlarim</b>\n\nMuvaffaqiyatli premiumlar: <b>{premiums} ta</b>"
    if isinstance(event, types.CallbackQuery):
        await event.message.edit_text(text, parse_mode="HTML", reply_markup=get_back_to_menu_keyboard())
    else:
        await event.answer(text, parse_mode="HTML", reply_markup=get_back_to_menu_keyboard())

@dp.callback_query(F.data == "user_stats")
@dp.message(F.text == "📊 Statistikam")
async def handle_user_statistics(event: types.Message | types.CallbackQuery):
    if isinstance(event, types.Message):
        await cleanup_reply_keyboard(event)
    user_id = event.from_user.id
    stats = database.get_user_statistics(user_id)
    text = (
        f"📊 <b>Mening statistikam</b>\n\n"
        f"<b>Umumiy:</b>\n"
        f"📦 Jami orderlar:  <b>{stats['total_orders']}</b>\n"
        f"✅ Premiumlar:  <b>{stats['completed_orders']}</b>\n"
        f"❌ Ishlamadi:  <b>{stats['frozen_orders']}</b>\n"
        f"⏰ Vaqti o'tdi:  <b>{stats['expired_orders']}</b>\n"
        f"🟡 Active:  <b>{stats['active_orders']}</b>\n\n"
        f"🕒 <b>So'nggi 24 soat:</b>\n"
        f"📦 Orderlar:  <b>{stats['orders_24h']}</b>\n"
        f"✅ Premiumlar:  <b>{stats['completed_24h']}</b>\n"
        f"❌ Ishlamadi:  <b>{stats['frozen_24h']}</b>"
    )
    if isinstance(event, types.CallbackQuery):
        await event.message.edit_text(text, parse_mode="HTML", reply_markup=get_back_to_menu_keyboard())
    else:
        await event.answer(text, parse_mode="HTML", reply_markup=get_back_to_menu_keyboard())

@dp.callback_query(F.data == "user_history")
@dp.message(F.text == "📋 Tarixim")
async def handle_user_history(event: types.Message | types.CallbackQuery):
    if isinstance(event, types.Message):
        await cleanup_reply_keyboard(event)
    user_id = event.from_user.id
    history = database.get_user_history(user_id, limit=15)
    if not history:
        text = "📋 <b>Tarixim</b>\n\nSizda hali olingan raqamlar mavjud emas."
    else:
        text = "📋 <b>Sizning raqamlar tarixingiz:</b>\n\n"
        status_icons = {'completed': '✅ Premium olindi', 'frozen': '🧊 Muzlatilgan', 'cancelled': '❌ Bekor qilingan', 'expired': '⏰ Vaqti o\'tgan', 'active': '🟡 Faol'}
        for idx, (phone, st, created_at) in enumerate(history, 1):
            st_text = status_icons.get(st, st)
            text += f"{idx}. <code>{phone}</code> — {st_text} (<i>{str(created_at)[:16]}</i>)\n"
    if isinstance(event, types.CallbackQuery):
        await event.message.edit_text(text, parse_mode="HTML", reply_markup=get_back_to_menu_keyboard())
    else:
        await event.answer(text, parse_mode="HTML", reply_markup=get_back_to_menu_keyboard())

@dp.callback_query(F.data == "user_withdraw")
@dp.message(F.text == "💸 Pul yechish")
async def handle_withdraw_placeholder(event: types.Message | types.CallbackQuery):
    if isinstance(event, types.Message):
        await cleanup_reply_keyboard(event)
    text = "💸 <b>Pul yechish bo'limi</b>\n\nTez orada ishga tushadi! Yangiliklarni kuzatib boring."
    if isinstance(event, types.CallbackQuery):
        await event.message.edit_text(text, parse_mode="HTML", reply_markup=get_back_to_menu_keyboard())
    else:
        await event.answer(text, parse_mode="HTML", reply_markup=get_back_to_menu_keyboard())

@dp.callback_query(F.data == "user_manual")
@dp.message(F.text == "📖 Qo'llanma")
async def handle_user_manual(event: types.Message | types.CallbackQuery):
    if isinstance(event, types.Message):
        await cleanup_reply_keyboard(event)
    reward_val = database.get_setting("reward_per_account", "40,000")
    text = (
        "📖 <b>Qo'llanma</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💰 <b>Sizga beriladigan mukofot:</b> {reward_val} so'm <i>(har bir premium uchun)</i>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "⚡️ <b>1-USUL: Avto olish (Robot orqali)</b>\n"
        "   1. «💳 Mening kartalarim» bo'limida kartangizni saqlang.\n"
        "   2. «⚡️ Avto olish (Robot)» tugmasini bosing.\n"
        "   3. Bot o'zi raqam oladi, kiradi va to'lovni avtomat bajaradi!\n"
        "   4. 🛑 Premium olingach avto-uzaytirish bekor qilinadi (/stop).\n\n"
        "📱 <b>2-USUL: Qo'lda olish (Manual)</b>\n"
        "   1. «📱 Qo'lda olish (Manual)» tugmasini bosing.\n"
        "   2. Berilgan telefon raqami bilan Telegram ilovangizda kiring.\n"
        "   3. «📨 Get Code» bosib kod va 2FA parolni oling.\n"
        "   4. Akkauntga kirgach, @PremiumBot orqali premiumni sotib oling.\n"
        "   5. Premiumni sotib olgach, «✅ Oldim» tugmasini bosing!\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "⚠️ <i>1 ta kartadan xavfsizlik uchun ko'pi bilan 3 ta premium olish tavsiya etiladi.</i>\n"
        "💸 Pul yechish — «💸 Pul yechish» tugmasi orqali amalga oshiriladi."
    )
    if isinstance(event, types.CallbackQuery):
        await event.message.edit_text(text, parse_mode="HTML", reply_markup=get_manual_keyboard())
    else:
        await event.answer(text, parse_mode="HTML", reply_markup=get_manual_keyboard())

@dp.callback_query(F.data == "back_to_manual")
async def callback_back_to_manual(call: types.CallbackQuery):
    await handle_user_manual(call)

@dp.callback_query(F.data == "user_top")
@dp.message(F.text == "🏆 Top Reyting")
async def handle_top_rating(event: types.Message | types.CallbackQuery):
    if isinstance(event, types.Message):
        await cleanup_reply_keyboard(event)
    leaders = database.get_top_rating(limit=10)
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    if not leaders:
        text = "🏆 <b>Top Reyting:</b>\n\nHozircha premium olgan foydalanuvchilar yo'q. Birinchi bo'lib oling! 🚀"
    else:
        text = "🏆 <b>Eng ko'p premium olganlar ro'yxati (TOP 10):</b>\n\n"
        for idx, (uname, fname, count) in enumerate(leaders):
            icon = medals[idx] if idx < len(medals) else f"{idx+1}."
            display_name = f"@{uname}" if uname else (fname or "Foydalanuvchi")
            text += f"{icon} <b>{display_name}</b> — <b>{count} ta</b> premium\n"

    if isinstance(event, types.CallbackQuery):
        await event.message.edit_text(text, parse_mode="HTML", reply_markup=get_back_to_menu_keyboard())
    else:
        await event.answer(text, parse_mode="HTML", reply_markup=get_back_to_menu_keyboard())

# ==========================================
# 👨‍💼 ADMIN PANEL ASOSIY MENYUSI (Rasm 0)
# ==========================================

def get_admin_main_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🤖 Userbotlar", callback_data="menu_userbots", style="primary", icon_custom_emoji_id="5260244316554562171"),
            InlineKeyboardButton(text="📊 Statistika", callback_data="menu_stats", style="primary", icon_custom_emoji_id="5260244316554562171")
        ],
        [
            InlineKeyboardButton(text="⚙️ Sozlamalar", callback_data="menu_settings", style="primary", icon_custom_emoji_id="5260244316554562171"),
            InlineKeyboardButton(text="👥 Foydalanuvchilar", callback_data="menu_users", style="primary", icon_custom_emoji_id="5260244316554562171")
        ],
        [
            InlineKeyboardButton(text="🔔 Pending userlar", callback_data="menu_pending", style="primary", icon_custom_emoji_id="5260244316554562171"),
            InlineKeyboardButton(text="🤖 Any botlar", callback_data="menu_anybots", style="primary", icon_custom_emoji_id="5260244316554562171")
        ],
        [
            InlineKeyboardButton(text="📢 Broadcast", callback_data="menu_broadcast", style="success", icon_custom_emoji_id="5281024210146201465")
        ],
        [
            InlineKeyboardButton(text="💸 Pul yechishlar", callback_data="menu_withdrawals", style="success", icon_custom_emoji_id="5281024210146201465")
        ],
        [
            InlineKeyboardButton(text="👮‍♂️ Adminlar", callback_data="menu_admins", style="primary", icon_custom_emoji_id="5260244316554562171")
        ]
    ])

@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    if not database.is_admin(message.from_user.id, config.ADMIN_ID):
        await message.answer("❌ Kechirasiz, siz admin emassiz.")
        return
    await message.answer("👨‍💼 Admin panel", reply_markup=get_admin_main_keyboard())

@dp.callback_query(F.data == "back_to_admin_root")
async def back_to_admin_root_cb(call: types.CallbackQuery):
    await call.message.edit_text("👨‍💼 Admin panel", reply_markup=get_admin_main_keyboard())

# ==========================================
# 1. 🤖 USERBOTLAR BOSHQARUVI (Rasm 1)
# ==========================================

@dp.callback_query(F.data == "menu_userbots")
async def show_userbots_menu(call: types.CallbackQuery):
    userbots = database.get_all_userbots()
    btns = []
    for ub in userbots:
        ub_id, name, phone, tg_id, status, holat, active_nums, _ = ub
        icon = "✅" if status == "active" else "❌"
        btns.append([InlineKeyboardButton(text=f"{icon} {name} | {phone}", callback_data=f"ub_view_{ub_id}")])

    btns.append([InlineKeyboardButton(text="➕ Userbot qo'shish", callback_data="ub_add_start")])
    btns.append([InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_admin_root")])

    text = f"🤖 <b>Userbotlar — jami: {len(userbots)}</b>"
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(F.data.startswith("ub_view_"))
async def view_userbot_details(call: types.CallbackQuery):
    ub_id = int(call.data.split("_")[2])
    userbots = database.get_all_userbots()
    target = next((u for u in userbots if u[0] == ub_id), None)
    if not target:
        await call.answer("Topilmadi!", show_alert=True)
        return

    _, name, phone, tg_id, status, holat, active_nums, _ = target
    text = (
        f"🤖 <b>Userbot: {name}</b>\n\n"
        f"📱 Telefon: <code>{phone}</code>\n"
        f"🆔 Telegram ID: <code>{tg_id}</code>\n"
        f"📊 Status: <b>{'✅ Faol' if status == 'active' else '❌ To\'xtatilgan'}</b>\n"
        f"⚙️ Holat: <b>{holat}</b>"
    )
    toggle_txt = "🔴 To'xtatish" if status == "active" else "🟢 Yoqish"
    btns = [
        [InlineKeyboardButton(text=toggle_txt, callback_data=f"ub_toggle_{ub_id}")],
        [InlineKeyboardButton(text="🗑 O'chirish", callback_data=f"ub_delete_{ub_id}")],
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="menu_userbots")]
    ]
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(F.data.startswith("ub_toggle_"))
async def toggle_userbot_cb(call: types.CallbackQuery):
    ub_id = int(call.data.split("_")[2])
    database.toggle_userbot_status(ub_id)
    await call.answer("Holati o'zgartirildi!")
    await view_userbot_details(call)

@dp.callback_query(F.data.startswith("ub_delete_"))
async def delete_userbot_cb(call: types.CallbackQuery):
    ub_id = int(call.data.split("_")[2])
    database.delete_userbot_record(ub_id)
    await call.answer("O'chirildi! 🗑", show_alert=True)
    await show_userbots_menu(call)

@dp.callback_query(F.data == "ub_add_start")
async def start_add_userbot(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_for_ub_phone)
    await call.message.edit_text(
        "📱 <b>Yangi Userbot telefon raqamini kiriting:</b>\n"
        "<i>(Masalan: +998901234567)</i>\n\n"
        "Bekor qilish: /cancel",
        parse_mode="HTML"
    )

@dp.message(AdminStates.waiting_for_ub_phone)
async def process_ub_phone(message: types.Message, state: FSMContext):
    if message.text.lower() == "/cancel":
        await state.clear()
        await message.answer("Bekor qilindi.")
        return

    phone = message.text.strip().replace(" ", "")
    wait_msg = await message.answer("⏳ Telegram orqali kod yuborilmoqda, kuting...")

    success, res = await userbot.start_phone_login(message.from_user.id, phone)
    if success:
        await state.update_data(ub_phone=phone)
        await state.set_state(AdminStates.waiting_for_ub_code)
        await wait_msg.edit_text(
            f"📨 <b>{phone}</b> raqamiga Telegram orqali tasdiqlash kodi yuborildi!\n\n"
            f"Iltimos, kelgan 5 xonali kodni yuboring:\n"
            f"<i>(Bekor qilish: /cancel)</i>",
            parse_mode="HTML"
        )
    else:
        await wait_msg.edit_text(f"❌ Xatolik yuz berdi:\n<i>{res}</i>\n\nQaytadan /admin buyrug'ini yozing.")
        await state.clear()

@dp.message(AdminStates.waiting_for_ub_code)
async def process_ub_code(message: types.Message, state: FSMContext):
    if message.text.lower() == "/cancel":
        await state.clear()
        await message.answer("Bekor qilindi.")
        return

    code = message.text.strip().replace(" ", "")
    wait_msg = await message.answer("⏳ Tizimga kirilmoqda...")

    res_status, msg = await userbot.complete_phone_login(message.from_user.id, code)
    if res_status is True:
        await state.clear()
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🤖 Userbotlar ro'yxatiga qaytish", callback_data="menu_userbots")]])
        await wait_msg.edit_text(f"🎉 {msg}\nEndi bot ushbu akkaunt orqali ham diller botdan raqam oladi!", parse_mode="HTML", reply_markup=keyboard)
    elif res_status == "2fa_required":
        await state.set_state(AdminStates.waiting_for_ub_password)
        await state.update_data(saved_code=code)
        await wait_msg.edit_text("🔒 <b>Ikki bosqichli parol (2FA) aniqlandi!</b>\n\nIltimos, hisobingiz parolini yuboring:", parse_mode="HTML")
    else:
        await wait_msg.edit_text(f"❌ Xatolik: {msg}\n\nQaytadan /admin buyrug'ini yozing.")
        await state.clear()

@dp.message(AdminStates.waiting_for_ub_password)
async def process_ub_password(message: types.Message, state: FSMContext):
    if message.text.lower() == "/cancel":
        await state.clear()
        await message.answer("Bekor qilindi.")
        return

    password = message.text.strip()
    data = await state.get_data()
    saved_code = data.get("saved_code", "")

    wait_msg = await message.answer("⏳ Parol tekshirilmoqda...")
    res_status, msg = await userbot.complete_phone_login(message.from_user.id, saved_code, password=password)

    if res_status is True:
        await state.clear()
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🤖 Userbotlar ro'yxatiga qaytish", callback_data="menu_userbots")]])
        await wait_msg.edit_text(f"🎉 {msg}", parse_mode="HTML", reply_markup=keyboard)
    else:
        await wait_msg.edit_text(f"❌ Parol noto'g'ri yoki xatolik: {msg}")
        await state.clear()

# ==========================================
# 2. 📊 STATISTIKA (Rasm 2)
# ==========================================

@dp.callback_query(F.data == "menu_stats")
async def show_stats_dashboard(call: types.CallbackQuery):
    s = database.get_full_admin_statistics()
    text = (
        f"🤖 <b>Userbotlar:</b>\n"
        f"Jami: <b>{s['total_ub']}</b> | Aktiv: <b>{s['active_ub']}</b> | Band: <b>{s['busy_ub']}</b>\n\n"
        f"📱 <b>Raqamlar:</b>\n"
        f"🟢 Ready:  <b>{s['ready_cnt']}</b>\n"
        f"🟡 Pending:  <b>{s['pending_cnt']}</b>\n"
        f"✅ Finish:  <b>{s['finish_cnt']}</b>\n"
        f"📦 Jami:  <b>{s['total_numbers']}</b>\n\n"
        f"🔢 <b>Harakatlar:</b>\n"
        f"📲 Get Number: <b>{s['stat_get_number']}</b>\n"
        f"📨 Get Code: <b>{s['stat_get_code']}</b>\n\n"
        f"📦 <b>Orderlar:</b>\n"
        f"Jami:      <b>{s['total_orders']}</b>\n"
        f"✅ Completed: <b>{s['completed_orders']}</b>\n"
        f"❌ Failed:     <b>{s['failed_orders']}</b>\n"
        f"⏰ Expired:    <b>{s['expired_orders']}</b>\n"
        f"🟡 Active:     <b>{s['active_orders']}</b>\n\n"
        f"👥 <b>Foydalanuvchilar:</b>\n"
        f"Jami:        <b>{s['total_users']}</b>\n"
        f"💰 Umumiy balance: <b>{s['total_balance']:,.0f} so'm</b>\n"
        f"📈 Jami topilgan: <b>{s['total_earned']:,.0f} so'm</b>\n"
        f"💸 Jami to'landi: <b>{s['total_paid']:,.0f} so'm</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🕒 <b>So'nggi 24 soat</b>\n\n"
        f"👥 Yangi userlar: <b>{s['new_users_24h']}</b>\n"
        f"📲 Get Number:    <b>{s['get_number_24h']}</b>\n"
        f"📦 Orderlar:      <b>{s['orders_24h']}</b>\n"
        f"✅ Completed:     <b>{s['completed_24h']}</b>\n"
        f"❌ Failed:        <b>{s['failed_24h']}</b>\n"
        f"💵 Ishlangan:     <b>{s['earned_24h']:,.0f} so'm</b>\n"
        f"💸 To'langan:     <b>{s['paid_24h']:,.0f} so'm</b>"
    )
    btns = [
        [InlineKeyboardButton(text="🔄 Yangilash", callback_data="menu_stats")],
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_admin_root")]
    ]
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

# ==========================================
# 3. ⚙️ SOZLAMALAR (Rasm 3)
# ==========================================

@dp.callback_query(F.data == "menu_settings")
async def show_settings_dashboard(call: types.CallbackQuery):
    settings = database.get_all_settings()
    btns = []
    for s_name, s_val in settings:
        if s_name == 'diller_bot_username':
            continue
        btns.append([InlineKeyboardButton(text=f"✏️ {s_name}: {s_val}", callback_data=f"edit_st_{s_name}")])
    btns.append([InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_admin_root")])

    text = "O'zgartirish uchun tugmaga bosing:"
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(F.data.startswith("edit_st_"))
async def edit_setting_prompt(call: types.CallbackQuery, state: FSMContext):
    s_name = call.data.replace("edit_st_", "")
    curr_val = database.get_setting(s_name)
    await state.update_data(target_setting=s_name)
    await state.set_state(AdminStates.waiting_for_setting_value)

    await call.message.edit_text(
        f"⚙️ <b>{s_name}</b> uchun yangi qiymat kiriting:\n\n"
        f"Hozirgi qiymat: <code>{curr_val}</code>\n"
        f"<i>Bekor qilish: /cancel</i>",
        parse_mode="HTML"
    )

@dp.message(AdminStates.waiting_for_setting_value)
async def process_setting_value_input(message: types.Message, state: FSMContext):
    if message.text.lower() == "/cancel":
        await state.clear()
        await message.answer("Bekor qilindi.")
        return

    new_val = message.text.strip()
    data = await state.get_data()
    s_name = data.get("target_setting")
    database.set_setting(s_name, new_val)
    await state.clear()

    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⚙️ Sozlamalarga qaytish", callback_data="menu_settings")]])
    await message.answer(f"✅ <b>{s_name}</b> yangilandi: <code>{new_val}</code>", parse_mode="HTML", reply_markup=keyboard)

# ==========================================
# 4. 👥 FOYDALANUVCHILAR (Rasm 1 va Rasm 2)
# ==========================================

def format_datetime_str(dt_str):
    if not dt_str:
        return "Noma'lum"
    try:
        if isinstance(dt_str, str):
            clean = dt_str.split(".")[0]
            dt = datetime.fromisoformat(clean)
            return dt.strftime("%d.%m.%Y %H:%M")
        elif isinstance(dt_str, datetime):
            return dt_str.strftime("%d.%m.%Y %H:%M")
    except Exception:
        pass
    return str(dt_str)[:16]

def build_users_page_markup_and_text(page: int = 0):
    users, total_count, total_pages = database.get_users_page(page=page, page_size=10)
    text = f"👥 <b>Foydalanuvchilar — jami: {total_count}</b>"
    
    btns = []
    for u_id, uname, fname, bal, st, jdate in users:
        # 1-rasm: 👤 8796192825 | 💰 120.00$ yoki 👤 Basherengaske | 💰 720.00$
        display_name = uname if uname else str(u_id)
        btn_text = f"👤 {display_name} | 💰 {bal:.2f}$"
        btns.append([InlineKeyboardButton(text=btn_text, callback_data=f"uview_{u_id}_{page}")])

    # Sahifalash (Pagination)
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="⬅️", callback_data=f"users_page_{page-1}"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton(text="➡️", callback_data=f"users_page_{page+1}"))
    if nav_row:
        btns.append(nav_row)

    # Qidirish, tozalash va orqaga tugmalari (1-rasm)
    btns.append([InlineKeyboardButton(text="🔍 ID orqali qidirish", callback_data="users_search_id")])
    btns.append([InlineKeyboardButton(text="🗑 Barcha statistikani tozalash", callback_data="users_clear_all_confirm")])
    btns.append([InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_admin_root")])

    return text, InlineKeyboardMarkup(inline_keyboard=btns)

def build_user_detail_markup_and_text(user_id: int, page: int = 0):
    det = database.get_user_full_detail(user_id)
    if not det:
        return None, None

    name_display = det['full_name'] or "Noma'lum"
    status_text = "✅ Aktiv" if det['status'] == 'active' else ("❌ Bloklangan" if det['status'] == 'banned' else "⏳ Pending")
    joined_formatted = format_datetime_str(det['join_date'])

    # 2-rasmdagi to'liq format
    text = (
        f"👤 <b>{name_display}</b>\n\n"
        f"🆔 <b>TG ID:</b> <code>{det['user_id']}</code>\n"
        f"📊 <b>Status:</b> {status_text}\n\n"
        f"💰 <b>Balance:</b> {det['balance']:,.0f} so'm\n"
        f"📈 <b>Jami topgan:</b> {det['total_earned']:,.0f} so'm\n"
        f"💸 <b>Jami yechgan:</b> {det['total_withdrawn']:,.0f} so'm\n\n"
        f"📦 <b>Orderlar (umumiy):</b>\n"
        f"Jami: {det['total_orders']}\n"
        f"✅ Completed: {det['completed']}\n"
        f"❌ Failed: {det['failed']}\n"
        f"⏰ Expired: {det['expired']}\n"
        f"💵 Ishlangan: {det['ishlangan']:,.0f} so'm\n\n"
        f"🕒 <b>So'nggi 24 soat:</b>\n"
        f"📦 Orderlar: {det['orders_24h']}\n"
        f"✅ Completed: {det['completed_24h']}\n"
        f"❌ Failed: {det['failed_24h']}\n"
        f"💵 Ishlangan: {det['ishlangan_24h']:,.0f} so'm\n\n"
        f"📅 <b>Qo'shilgan:</b> {joined_formatted}"
    )

    ban_btn_text = "🔓 Unban" if det['status'] == 'banned' else "🔨 Ban"

    btns = [
        [
            InlineKeyboardButton(text="📋 Raqamlar tarixi", callback_data=f"uopt_history_{user_id}_{page}", style="primary", icon_custom_emoji_id="5260244316554562171"),
            InlineKeyboardButton(text="💸 Pul yechish", callback_data=f"uopt_withdraw_{user_id}_{page}", style="success", icon_custom_emoji_id="5281024210146201465")
        ],
        [
            InlineKeyboardButton(text=ban_btn_text, callback_data=f"uopt_ban_{user_id}_{page}", style="danger", icon_custom_emoji_id="5278525655871424505")
        ],
        [
            InlineKeyboardButton(text="💰 Balance o'zgart", callback_data=f"uopt_bal_{user_id}_{page}", style="primary", icon_custom_emoji_id="5260244316554562171")
        ],
        [
            InlineKeyboardButton(text="🗑 Statistikani o'chirish", callback_data=f"uopt_clr_{user_id}_{page}", style="danger", icon_custom_emoji_id="5278525655871424505")
        ],
        [
            InlineKeyboardButton(text="🔙 Orqaga", callback_data=f"users_page_{page}", style="primary", icon_custom_emoji_id="5260244316554562171")
        ]
    ]

    return text, InlineKeyboardMarkup(inline_keyboard=btns)

@dp.callback_query(F.data == "menu_users")
@dp.callback_query(F.data.startswith("users_page_"))
async def show_users_dashboard(call: types.CallbackQuery):
    page = 0
    if call.data.startswith("users_page_"):
        try:
            page = int(call.data.split("_")[2])
        except Exception:
            page = 0
    text, markup = build_users_page_markup_and_text(page)
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=markup)

@dp.callback_query(F.data.startswith("uview_"))
async def user_view_detail_cb(call: types.CallbackQuery):
    parts = call.data.split("_")
    u_id = int(parts[1])
    page = int(parts[2]) if len(parts) > 2 else 0
    text, markup = build_user_detail_markup_and_text(u_id, page)
    if not text:
        await call.answer("Foydalanuvchi topilmadi!", show_alert=True)
        return
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=markup)

@dp.callback_query(F.data.startswith("uopt_ban_"))
async def user_toggle_ban_cb(call: types.CallbackQuery):
    parts = call.data.split("_")
    u_id = int(parts[2])
    page = int(parts[3]) if len(parts) > 3 else 0
    new_st = database.toggle_user_ban(u_id)
    alert_txt = "✅ Foydalanuvchi bloklandi (Ban)!" if new_st == 'banned' else "✅ Foydalanuvchi blokdan chiqarildi (Unban)!"
    await call.answer(alert_txt, show_alert=True)
    text, markup = build_user_detail_markup_and_text(u_id, page)
    if text:
        await call.message.edit_text(text, parse_mode="HTML", reply_markup=markup)

@dp.callback_query(F.data.startswith("uopt_history_"))
async def user_history_detail_cb(call: types.CallbackQuery):
    parts = call.data.split("_")
    u_id = int(parts[2])
    page = int(parts[3]) if len(parts) > 3 else 0
    history = database.get_user_history(u_id, limit=15)
    if not history:
        text = f"📋 <b>Foydalanuvchi ID: {u_id}</b>\n\nHozircha raqamlar tarixi mavjud emas."
    else:
        text = f"📋 <b>Foydalanuvchi ID: {u_id} — Raqamlar tarixi:</b>\n\n"
        status_icons = {'completed': '✅ Premium olindi', 'frozen': '🧊 Muzlatilgan', 'cancelled': '❌ Bekor qilingan', 'expired': '⏰ Vaqti o\'tgan', 'active': '🟡 Faol'}
        for idx, (phone, st, created_at) in enumerate(history, 1):
            st_text = status_icons.get(st, st)
            text += f"{idx}. <code>{phone}</code> — {st_text} (<i>{str(created_at)[:16]}</i>)\n"

    markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Orqaga", callback_data=f"uview_{u_id}_{page}")]])
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=markup)

@dp.callback_query(F.data.startswith("uopt_withdraw_"))
async def user_withdraw_detail_cb(call: types.CallbackQuery):
    parts = call.data.split("_")
    u_id = int(parts[2])
    page = int(parts[3]) if len(parts) > 3 else 0
    withdrawals = database.get_user_withdrawals(u_id, limit=10)
    if not withdrawals:
        text = f"💸 <b>Foydalanuvchi ID: {u_id}</b>\n\nHozircha pul yechish so'rovlari mavjud emas."
    else:
        text = f"💸 <b>Foydalanuvchi ID: {u_id} — Pul yechishlar:</b>\n\n"
        for idx, (w_id, amt, card, st, dt) in enumerate(withdrawals, 1):
            text += f"{idx}. #{w_id} — <b>{amt:,.0f} so'm</b> | {card} | {st} (<i>{str(dt)[:16]}</i>)\n"

    markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Orqaga", callback_data=f"uview_{u_id}_{page}")]])
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=markup)

@dp.callback_query(F.data.startswith("uopt_bal_"))
async def user_balance_edit_prompt(call: types.CallbackQuery, state: FSMContext):
    parts = call.data.split("_")
    u_id = int(parts[2])
    page = int(parts[3]) if len(parts) > 3 else 0
    det = database.get_user_full_detail(u_id)
    curr_bal = det['balance'] if det else 0.0

    await state.update_data(target_user_id=u_id, target_user_page=page, current_balance=curr_bal)
    await state.set_state(AdminStates.waiting_for_edit_user_balance)

    await call.message.edit_text(
        f"💰 <b>Foydalanuvchi ID: <code>{u_id}</code></b>\n\n"
        f"Hozirgi balans: <b>{curr_bal:,.2f}</b>\n\n"
        f"Yangi balansni kiriting (masalan: <code>150</code> yoki <code>+50</code> yoki <code>-20</code>):\n\n"
        f"<i>Bekor qilish: /cancel</i>",
        parse_mode="HTML"
    )

@dp.message(AdminStates.waiting_for_edit_user_balance)
async def process_user_balance_input(message: types.Message, state: FSMContext):
    if message.text.lower() == "/cancel":
        await state.clear()
        await message.answer("Bekor qilindi.")
        return

    data = await state.get_data()
    u_id = data.get("target_user_id")
    page = data.get("target_user_page", 0)
    curr_bal = data.get("current_balance", 0.0)

    val_str = message.text.strip().replace(" ", "")
    try:
        if val_str.startswith("+"):
            new_bal = curr_bal + float(val_str[1:])
        elif val_str.startswith("-"):
            new_bal = curr_bal - float(val_str[1:])
        else:
            new_bal = float(val_str)
    except ValueError:
        await message.answer("❌ Noto'g'ri son kiritildi. Qaytadan kiriting yoki /cancel bosing:")
        return

    database.update_user_balance(u_id, new_bal)
    await state.clear()

    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="👤 Foydalanuvchiga qaytish", callback_data=f"uview_{u_id}_{page}")]])
    await message.answer(f"✅ <b>Foydalanuvchi balansi muvaffaqiyatli yangilandi:</b>\n\n💰 Yangi balans: <b>{new_bal:,.2f}</b>", parse_mode="HTML", reply_markup=keyboard)

@dp.callback_query(F.data.startswith("uopt_clr_"))
async def user_clear_stats_prompt(call: types.CallbackQuery):
    parts = call.data.split("_")
    u_id = int(parts[2])
    page = int(parts[3]) if len(parts) > 3 else 0
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🗑 Ha, tozalash", callback_data=f"uopt_clrconfirm_{u_id}_{page}"),
            InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"uview_{u_id}_{page}")
        ]
    ])
    await call.message.edit_text(f"⚠️ <b>DIQQAT!</b>\n\nFoydalanuvchi <code>{u_id}</code> ning barcha buyurtmalari va statistikasini tozalashni tasdiqlaysizmi?", parse_mode="HTML", reply_markup=markup)

@dp.callback_query(F.data.startswith("uopt_clrconfirm_"))
async def user_clear_stats_confirmed(call: types.CallbackQuery):
    parts = call.data.split("_")
    u_id = int(parts[2])
    page = int(parts[3]) if len(parts) > 3 else 0
    database.clear_user_statistics(u_id)
    await call.answer("✅ Foydalanuvchi statistikasi tozalandi!", show_alert=True)
    text, markup = build_user_detail_markup_and_text(u_id, page)
    if text:
        await call.message.edit_text(text, parse_mode="HTML", reply_markup=markup)

@dp.callback_query(F.data == "users_search_id")
async def user_search_id_prompt(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_for_search_user_id)
    await call.message.edit_text(
        "🔍 <b>Foydalanuvchi qidirish</b>\n\n"
        "Foydalanuvchining Telegram ID raqamini kiriting:\n\n"
        "<i>Bekor qilish: /cancel</i>",
        parse_mode="HTML"
    )

@dp.message(AdminStates.waiting_for_search_user_id)
async def process_user_search_id(message: types.Message, state: FSMContext):
    if message.text.lower() == "/cancel":
        await state.clear()
        await message.answer("Bekor qilindi.")
        return

    input_text = message.text.strip()
    if not input_text.isdigit():
        await message.answer("❌ Iltimos, faqat raqamli Telegram ID kiriting yoki /cancel bosing:")
        return

    target_id = int(input_text)
    det = database.get_user_full_detail(target_id)
    if not det:
        markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Foydalanuvchilar ro'yxati", callback_data="menu_users")]])
        await message.answer(f"❌ <code>{target_id}</code> ID ga ega foydalanuvchi topilmadi.", parse_mode="HTML", reply_markup=markup)
        await state.clear()
        return

    await state.clear()
    text, markup = build_user_detail_markup_and_text(target_id, page=0)
    await message.answer(text, parse_mode="HTML", reply_markup=markup)

@dp.callback_query(F.data == "users_clear_all_confirm")
async def users_clear_all_stats_prompt(call: types.CallbackQuery):
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⚠️ Ha, barchasini tozalash", callback_data="users_clear_all_execute"),
            InlineKeyboardButton(text="❌ Bekor qilish", callback_data="users_page_0")
        ]
    ])
    await call.message.edit_text(
        "⚠️ <b>DIQQAT! XAVFLI AMAL!</b>\n\n"
        "Barcha foydalanuvchilarning buyurtmalari, muvaffaqiyatli premiumlari va topgan pullari statistikasini tozalashni tasdiqlaysizmi?",
        parse_mode="HTML",
        reply_markup=markup
    )

@dp.callback_query(F.data == "users_clear_all_execute")
async def users_clear_all_stats_executed(call: types.CallbackQuery):
    database.clear_all_statistics()
    await call.answer("✅ Barcha foydalanuvchilar statistikasi tozalandi!", show_alert=True)
    text, markup = build_users_page_markup_and_text(page=0)
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=markup)

# ==========================================
# 5. 🔔 PENDING USERLAR
# ==========================================

@dp.callback_query(F.data == "menu_pending")
async def show_pending_users_dashboard(call: types.CallbackQuery):
    pendings = database.get_pending_users(limit=15)
    btns = []
    for u_id, uname, fname, dt in pendings:
        display = f"@{uname}" if uname else (fname or str(u_id))
        btns.append([InlineKeyboardButton(text=f"⏳ {display}", callback_data=f"pend_det_{u_id}")])

    btns.append([InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_admin_root")])
    text = f"🔔 <b>Kutayotgan (Pending) userlar — {len(pendings)} ta</b>" if pendings else "🔔 Hozircha yangi ruxsat so'ragan foydalanuvchilar yo'q. ✅"
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(F.data.startswith("pend_det_"))
async def show_pending_details(call: types.CallbackQuery):
    u_id = int(call.data.split("_")[2])
    text = f"👤 Foydalanuvchi ID: <code>{u_id}</code>\n\nBotdan foydalanishiga ruxsat berasizmi?"
    btns = [
        [
            InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"pending_appr_{u_id}"),
            InlineKeyboardButton(text="❌ Rad etish", callback_data=f"pending_rejc_{u_id}")
        ],
        [InlineKeyboardButton(text="🔙 Ro'yxatga qaytish", callback_data="menu_pending")]
    ]
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(F.data.startswith("pending_appr_"))
async def approve_pending_user(call: types.CallbackQuery):
    u_id = int(call.data.split("_")[2])
    database.set_user_status(u_id, 'active')
    await call.answer("Tasdiqlandi! ✅")
    try:
        await bot.send_message(chat_id=u_id, text="🎉 <b>So'rovingiz tasdiqlandi!</b>\n\nEndi botdan to'liq foydalanishingiz mumkin. /start bosing.", parse_mode="HTML")
    except Exception:
        pass
    await show_pending_users_dashboard(call)

@dp.callback_query(F.data.startswith("pending_rejc_"))
async def reject_pending_user(call: types.CallbackQuery):
    u_id = int(call.data.split("_")[2])
    database.set_user_status(u_id, 'banned')
    await call.answer("Rad etildi! ❌")
    await show_pending_users_dashboard(call)

# ==========================================
# 6. 🤖 ANY BOTLAR (DILLER BOTLAR)
# ==========================================

@dp.callback_query(F.data == "menu_anybots")
async def show_anybots_menu(call: types.CallbackQuery):
    bots = database.get_all_any_bots()
    btns = []
    for b_id, b_uname, b_priority, b_status in bots:
        icon = "✅" if b_status == "active" else "❌"
        btns.append([InlineKeyboardButton(text=f"{icon} {b_uname}", callback_data=f"any_view_{b_id}")])

    btns.append([InlineKeyboardButton(text="➕ Yangi Diller bot qo'shish", callback_data="any_add_prompt")])
    btns.append([InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_admin_root")])

    text = f"🤖 <b>Any botlar (Diller botlar) — jami: {len(bots)}</b>"
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(F.data.startswith("any_view_"))
async def view_anybot_details(call: types.CallbackQuery):
    b_id = int(call.data.split("_")[2])
    bots = database.get_all_any_bots()
    target = next((b for b in bots if b[0] == b_id), None)
    if not target:
        await call.answer("Topilmadi!", show_alert=True)
        return

    _, b_uname, b_priority, b_status = target
    text = (
        f"🤖 <b>Diller bot: {b_uname}</b>\n\n"
        f"📊 Holati: <b>{'✅ Faol' if b_status == 'active' else '❌ To\'xtatilgan'}</b>"
    )
    toggle_txt = "🔴 To'xtatish" if b_status == "active" else "🟢 Yoqish"
    btns = [
        [InlineKeyboardButton(text=toggle_txt, callback_data=f"any_toggle_{b_id}")],
        [InlineKeyboardButton(text="🗑 O'chirish", callback_data=f"any_delete_{b_id}")],
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="menu_anybots")]
    ]
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(F.data.startswith("any_toggle_"))
async def toggle_anybot_cb(call: types.CallbackQuery):
    b_id = int(call.data.split("_")[2])
    database.toggle_any_bot(b_id)
    await call.answer("Holat o'zgardi!")
    await view_anybot_details(call)

@dp.callback_query(F.data.startswith("any_delete_"))
async def delete_anybot_cb(call: types.CallbackQuery):
    b_id = int(call.data.split("_")[2])
    database.delete_any_bot(b_id)
    await call.answer("O'chirildi! 🗑")
    await show_anybots_menu(call)

@dp.callback_query(F.data == "any_add_prompt")
async def add_anybot_prompt_cb(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_for_any_bot_uname)
    await call.message.edit_text(
        "➕ <b>Diller bot username'ini yuboring:</b>\n"
        "<i>(Masalan: @diller_boti)\nBekor qilish: /cancel</i>",
        parse_mode="HTML"
    )

@dp.message(AdminStates.waiting_for_any_bot_uname)
async def process_anybot_uname_input(message: types.Message, state: FSMContext):
    if message.text.lower() == "/cancel":
        await state.clear()
        await message.answer("Bekor qilindi.")
        return

    uname = message.text.strip()
    if not uname.startswith("@"):
        uname = "@" + uname

    database.add_any_bot(uname, priority=100)
    database.set_setting("diller_bot_username", uname)
    await state.clear()

    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🤖 Any botlar ro'yxati", callback_data="menu_anybots")]])
    await message.answer(f"✅ <code>{uname}</code> muvaffaqiyatli qo'shildi va faollashtirildi!", parse_mode="HTML", reply_markup=keyboard)

# ==========================================
# 7. 📢 BROADCAST (Rasm 5)
# ==========================================

@dp.callback_query(F.data == "menu_broadcast")
async def show_broadcast_dashboard(call: types.CallbackQuery, state: FSMContext):
    conn = database.get_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users WHERE status = 'active'")
    active_cnt = c.fetchone()[0]
    conn.close()

    await state.set_state(AdminStates.waiting_for_broadcast_msg)

    text = (
        f"📢 <b>Yangi broadcast</b>\n\n"
        f"👥 Bazada <b>{active_cnt}</b> ta aktiv user bor\n\n"
        f"Yubormoqchi bo'lgan xabarni <b>forward qiling</b> yoki yozing.\n\n"
        f"⚠️ <i>Har qanday xabar turi: matn, rasm, video, audio, sticker, tugmalar...</i>\n\n"
        f"Bekor qilish: /cancel"
    )
    btns = [[InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_admin_root")]]
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

@dp.message(AdminStates.waiting_for_broadcast_msg)
async def process_broadcast_message_input(message: types.Message, state: FSMContext):
    if message.text and message.text.lower() == "/cancel":
        await state.clear()
        await message.answer("Bekor qilindi.")
        return

    conn = database.get_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users WHERE status = 'active'")
    target_cnt = c.fetchone()[0]
    conn.close()

    b_id = database.create_broadcast(message.chat.id, message.message_id, target_cnt)
    await state.clear()

    text = (
        f"✅ <b>Broadcast #{b_id} yaratildi!</b>\n\n"
        f"🎯 Target: <b>{target_cnt} ta aktiv user</b>\n\n"
        f"▶️ Boshlash yoki ✏️ limit ni o'zgartirish mumkin:"
    )
    btns = [
        [InlineKeyboardButton(text="▶️ Boshlash", callback_data=f"bcast_start_{b_id}")],
        [InlineKeyboardButton(text="✏️ Limit edit", callback_data=f"bcast_limit_{b_id}")],
        [InlineKeyboardButton(text="🗑 O'chirish", callback_data=f"bcast_del_{b_id}")],
        [InlineKeyboardButton(text="🔙 Ro'yxat", callback_data="back_to_admin_root")]
    ]
    await message.answer(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(F.data.startswith("bcast_start_"))
async def start_broadcast_sending(call: types.CallbackQuery):
    b_id = int(call.data.split("_")[2])
    b = database.get_broadcast(b_id)
    if not b:
        await call.answer("Broadcast topilmadi!", show_alert=True)
        return

    _, chat_id, msg_id, target_cnt, limit_cnt, _, _ = b
    await call.answer("Xabar tarqatish boshlandi...")

    conn = database.get_connection()
    c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE status = 'active' LIMIT ?", (limit_cnt or target_cnt,))
    users = c.fetchall()
    conn.close()

    status_msg = await call.message.edit_text(f"⏳ <b>Broadcast #{b_id} yuborilmoqda...</b> (0/{len(users)})", parse_mode="HTML")

    sent = 0
    for idx, u in enumerate(users, 1):
        try:
            await bot.copy_message(chat_id=u[0], from_chat_id=chat_id, message_id=msg_id)
            sent += 1
            await asyncio.sleep(0.04)
        except Exception:
            pass
        if idx % 20 == 0:
            try:
                await status_msg.edit_text(f"⏳ <b>Broadcast #{b_id} yuborilmoqda...</b> ({idx}/{len(users)})", parse_mode="HTML")
            except Exception:
                pass

    await status_msg.edit_text(f"🎉 <b>Broadcast #{b_id} yakunlandi!</b>\n\nYetib bordi: <b>{sent} ta</b> aktiv foydalanuvchiga.", parse_mode="HTML")

@dp.callback_query(F.data.startswith("bcast_del_"))
async def delete_broadcast_cb(call: types.CallbackQuery):
    b_id = int(call.data.split("_")[2])
    database.delete_broadcast(b_id)
    await call.answer("Broadcast o'chirildi! 🗑")
    await call.message.edit_text("👨‍💼 Admin panel", reply_markup=get_admin_main_keyboard())

# ==========================================
# 8. 💸 PUL YECHISHLAR
# ==========================================

@dp.callback_query(F.data == "menu_withdrawals")
async def show_withdrawals_menu(call: types.CallbackQuery):
    conn = database.get_connection()
    c = conn.cursor()
    c.execute("SELECT id, user_id, amount, card_details FROM withdrawals WHERE status = 'pending' LIMIT 10")
    pending_w = c.fetchall()
    conn.close()

    btns = []
    for w_id, u_id, amt, card in pending_w:
        btns.append([InlineKeyboardButton(text=f"💸 #{w_id} | {amt:,.0f} so'm", callback_data=f"wview_{w_id}")])

    btns.append([InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_admin_root")])
    text = f"💸 <b>Pul yechish so'rovlari: {len(pending_w)} ta</b>" if pending_w else "💸 Yangi pul yechish so'rovlari yo'q. ✅"
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

# ==========================================
# 9. 👮‍♂️ ADMINLAR (Rasm 4)
# ==========================================

@dp.callback_query(F.data == "menu_admins")
async def show_admins_menu(call: types.CallbackQuery):
    admins = database.get_all_admins()
    
    text = f"👮‍♂️ <b>Adminlar — jami: {len(admins) + 1}</b>\n\n"
    text += f"• <b>Asosiy Admin</b>\n🆔 <code>{config.ADMIN_ID}</code> 🔒 .env · 15.08.2026\n\n"

    del_btns = []
    for a_id, uname, dt in admins:
        uname_display = f"@{uname}" if uname else f"ID: {a_id}"
        date_str = str(dt)[:10].replace("-", ".")
        text += f"• {uname_display}\n🆔 <code>{a_id}</code> · {date_str}\n\n"
        del_btns.append([InlineKeyboardButton(text=f"❌ O'chirish — {uname_display}", callback_data=f"adm_del_{a_id}")])

    del_btns.append([InlineKeyboardButton(text="➕ Admin qo'shish", callback_data="adm_add_prompt")])
    del_btns.append([InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_admin_root")])

    await call.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=del_btns))

@dp.callback_query(F.data.startswith("adm_del_"))
async def delete_admin_cb(call: types.CallbackQuery):
    a_id = int(call.data.split("_")[2])
    database.delete_admin(a_id)
    await call.answer("Admin o'chirildi! ❌")
    await show_admins_menu(call)

@dp.callback_query(F.data == "adm_add_prompt")
async def add_admin_prompt_cb(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_for_new_admin_id)
    await call.message.edit_text("➕ <b>Yangi adminning Telegram ID raqamini kiriting:</b>\n<i>Bekor qilish: /cancel</i>", parse_mode="HTML")

@dp.message(AdminStates.waiting_for_new_admin_id)
async def process_new_admin_id(message: types.Message, state: FSMContext):
    if message.text.lower() == "/cancel":
        await state.clear()
        await message.answer("Bekor qilindi.")
        return

    if not message.text.isdigit():
        await message.answer("Iltimos, faqat raqamdan iborat Telegram ID kiriting:")
        return

    new_id = int(message.text)
    database.add_admin(new_id, username=message.from_user.username or "")
    await state.clear()

    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="👮‍♂️ Adminlar ro'yxati", callback_data="menu_admins")]])
    await message.answer(f"✅ <code>{new_id}</code> yangi admin sifatida muvaffaqiyatli qo'shildi!", parse_mode="HTML", reply_markup=keyboard)

# ==========================================
# BOTNI ISHGA TUSHIRISH
# ==========================================

async def main():
    database.init_db()
    print("=" * 55)
    print("🚀 Premium Bot to'liq muvaffaqiyatli ishga tushdi!")
    print("Aiogram 3 va Telethon Userbot integratsiyasi faol.")
    print("=" * 55)

    # Start Web App server on port 8080
    try:
        from webapp_server import start_webapp_server
        await start_webapp_server(host='0.0.0.0', port=5000)
    except Exception as e:
        logger.error(f"Web App server ishga tushirishda xatolik: {e}")

    # Set Menu Button if webapp_url is configured
    webapp_url = database.get_setting("webapp_url", "").strip()
    if webapp_url:
        try:
            from aiogram.types import MenuButtonWebApp, WebAppInfo
            await bot.set_chat_menu_button(
                menu_button=MenuButtonWebApp(text="🚀 Ilova", web_app=WebAppInfo(url=webapp_url))
            )
        except Exception as e:
            logger.error(f"MenuButtonWebApp o'rnatishda xatolik: {e}")

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())