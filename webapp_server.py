import os
import json
import math
import asyncio
import logging
import hmac
import hashlib
import urllib.parse
from datetime import datetime, timezone
from aiohttp import web

import database
import userbot
import config

logger = logging.getLogger(__name__)

# Web app directory
WEBAPP_DIR = os.path.join(os.path.dirname(__file__), 'webapp')

def validate_telegram_init_data(init_data: str, bot_token: str) -> dict | None:
    """Telegram WebApp initData HMAC-SHA256 xavfsizlik tekshiruvi"""
    if not init_data or not bot_token:
        return None
    try:
        parsed = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
        hash_val = parsed.pop('hash', None)
        if not hash_val:
            return None

        data_check_list = [f"{k}={v}" for k, v in sorted(parsed.items())]
        data_check_string = "\n".join(data_check_list)

        secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
        calc_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()

        if hmac.compare_digest(calc_hash, hash_val):
            user_json = parsed.get("user")
            if user_json:
                return json.loads(user_json)
        return None
    except Exception as e:
        logger.warning(f"initData validation xatosi: {e}")
        return None

def get_auth_user_id(request, json_data: dict = None) -> int | None:
    """
    So'rov yuboruvchining haqiqiy ID raqamini xavfsiz aniqlaydi.
    1. Telegram WebApp initData HMAC tekshiruvi
    2. Fallback: Faqat agar initData berilmagan bo'lsa, X-User-Id yoki query param user_id
    Hech qachon o'zboshimchalik bilan ADMIN_ID ga tushib qolmaydi!
    """
    init_data = request.headers.get("X-Telegram-Init-Data") or request.query.get("initData")
    if init_data:
        user_info = validate_telegram_init_data(init_data, config.BOT_TOKEN)
        if user_info and "id" in user_info:
            return int(user_info["id"])

    # Fallback tekshiruv
    hdr_uid = request.headers.get("X-User-Id")
    if hdr_uid and str(hdr_uid).isdigit():
        return int(hdr_uid)

    q_uid = request.query.get("user_id")
    if q_uid and str(q_uid).isdigit():
        return int(q_uid)

    if json_data and json_data.get("user_id") and str(json_data.get("user_id")).isdigit():
        return int(json_data.get("user_id"))

    return None

def get_seconds_left(expires_at_str, created_at_str=None, total_duration=300):
    if not expires_at_str:
        return total_duration
    try:
        clean = str(expires_at_str).split('.')[0]
        exp = datetime.fromisoformat(clean)
        now = datetime.now()
        diff = (exp - now).total_seconds()
        return max(0, int(diff))
    except Exception:
        return total_duration

def cors_headers():
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, X-Telegram-Init-Data, X-User-Id"
    }

def json_response(data, status=200):
    return web.json_response(data, status=status, headers=cors_headers())

async def handle_options(request):
    return web.Response(headers=cors_headers())

# Static files handlers
async def handle_index(request):
    index_file = os.path.join(WEBAPP_DIR, 'index.html')
    if os.path.exists(index_file):
        return web.FileResponse(index_file)
    return web.Response(text="Web App index.html not found", status=404)

async def handle_app_js(request):
    js_file = os.path.join(WEBAPP_DIR, 'app.js')
    if os.path.exists(js_file):
        return web.FileResponse(js_file)
    return web.Response(text="app.js not found", status=404)

# API Handlers
async def api_user_me(request):
    user_id = get_auth_user_id(request)
    if not user_id:
        return json_response({"error": "Avtorizatsiya talab qilinadi!"}, status=401)

    detail = database.get_user_full_detail(user_id)
    if not detail:
        # Ro'yxatdan o'tkazish
        database.register_or_get_user(user_id, "", "Foydalanuvchi")
        detail = database.get_user_full_detail(user_id)

    # Faol buyurtmani tekshirish
    active_order_row = database.get_active_order_for_user(user_id)
    active_order_dict = None
    if active_order_row:
        # id, user_id, phone_number, code, diller_bot_username, diller_msg_id, status, created_at, expires_at, userbot_id, password
        sec_left = get_seconds_left(active_order_row[8])
        active_order_dict = {
            "id": active_order_row[0],
            "phone_number": active_order_row[2],
            "code": active_order_row[3],
            "password": active_order_row[10] if len(active_order_row) > 10 else None,
            "status": active_order_row[6],
            "seconds_left": sec_left
        }

    return json_response({
        "user_id": user_id,
        "username": detail.get('username', '') if detail else '',
        "full_name": detail.get('full_name', '') if detail else 'Foydalanuvchi',
        "balance": detail.get('balance', 0) if detail else 0,
        "total_earned": detail.get('total_earned', 0) if detail else 0,
        "successful_premiums": detail.get('successful_premiums', 0) if detail else 0,
        "status": detail.get('status', 'active') if detail else 'active',
        "active_order": active_order_dict
    })

async def api_get_number(request):
    data = await request.json()
    user_id = get_auth_user_id(request, data)
    if not user_id:
        return json_response({"success": False, "error": "Avtorizatsiya talab qilinadi!"}, status=401)

    active_order = database.get_active_order_for_user(user_id)
    if active_order:
        sec_left = get_seconds_left(active_order[8])
        return json_response({
            "success": True,
            "order": {
                "id": active_order[0],
                "phone_number": active_order[2],
                "code": active_order[3],
                "password": active_order[10] if len(active_order) > 10 else None,
                "seconds_left": sec_left
            }
        })

    diller_bot = database.get_active_diller_bot()
    if not diller_bot:
        return json_response({"success": False, "error": "Hozirda raqam olish xizmati vaqtincha to'xtatilgan."})

    phone, diller_msg_id, err = await userbot.request_number_from_diller(diller_bot)
    if not phone:
        return json_response({"success": False, "error": "Hozirda bo'sh raqamlar mavjud emas!"})

    order_id = database.create_order(user_id, phone, diller_bot, diller_msg_id, duration_seconds=300)

    # Kanalga log yuborish
    try:
        from main import send_channel_number_log
        asyncio.create_task(send_channel_number_log(user_id, str(user_id), phone, diller_bot))
    except Exception:
        pass

    return json_response({
        "success": True,
        "order": {
            "id": order_id,
            "phone_number": phone,
            "code": None,
            "password": None,
            "seconds_left": 300
        }
    })

async def api_get_code(request):
    data = await request.json()
    user_id = get_auth_user_id(request, data)
    if not user_id:
        return json_response({"success": False, "error": "Avtorizatsiya talab qilinadi!"}, status=401)

    order_id = int(data.get('order_id', 0))
    order = database.get_order(order_id)
    if not order or order[6] != 'active':
        return json_response({"success": False, "error": "Buyurtma topilmadi yoki faol emas!"})
    if order[1] != user_id and not database.is_admin(user_id, config.ADMIN_ID):
        return json_response({"success": False, "error": "Ushbu buyurtma sizga tegishli emas!"}, status=403)

    diller_bot = order[4]
    diller_msg_id = order[5]

    success, result = await userbot.click_diller_button(diller_bot, diller_msg_id, "Get Code")
    if success:
        if isinstance(result, tuple):
            code_text, pass_text = result
        else:
            code_text, pass_text = result, None

        database.update_order_status(order_id, 'active', code=code_text, password=pass_text)
        return json_response({
            "success": True,
            "code": code_text,
            "password": pass_text
        })
    return json_response({"success": False, "error": str(result) or "Kod hali berilmadi!"})

async def api_order_received(request):
    data = await request.json()
    user_id = get_auth_user_id(request, data)
    if not user_id:
        return json_response({"success": False, "error": "Avtorizatsiya talab qilinadi!"}, status=401)

    order_id = int(data.get('order_id', 0))
    order = database.get_order(order_id)
    if not order or order[6] != 'active':
        return json_response({"success": False, "error": "Buyurtma faol emas!"})
    if order[1] != user_id and not database.is_admin(user_id, config.ADMIN_ID):
        return json_response({"success": False, "error": "Ushbu buyurtma sizga tegishli emas!"}, status=403)

    diller_bot = order[4]
    diller_msg_id = order[5]
    phone = order[2]

    is_premium, res_msg = await userbot.check_premium_from_diller(diller_bot, diller_msg_id)
    if not is_premium:
        return json_response({"success": False, "error": res_msg})

    database.update_order_status(order_id, 'completed')

    # Kanalga to'lov log yuborish
    try:
        from main import send_channel_payment_log
        reward_val = database.get_setting('reward_per_account', '40')
        asyncio.create_task(send_channel_payment_log(user_id, str(user_id), phone, f"{reward_val} so'm"))
    except Exception:
        pass

    return json_response({"success": True})

async def api_order_freeze(request):
    data = await request.json()
    user_id = get_auth_user_id(request, data)
    if not user_id:
        return json_response({"success": False, "error": "Avtorizatsiya talab qilinadi!"}, status=401)

    order_id = int(data.get('order_id', 0))
    order = database.get_order(order_id)
    if not order or order[6] != 'active':
        return json_response({"success": False, "error": "Buyurtma faol emas!"})
    if order[1] != user_id and not database.is_admin(user_id, config.ADMIN_ID):
        return json_response({"success": False, "error": "Ushbu buyurtma sizga tegishli emas!"}, status=403)

    diller_bot = order[4]
    diller_msg_id = order[5]
    if diller_msg_id:
        await userbot.click_diller_button(diller_bot, diller_msg_id, "Freeze")

    database.update_order_status(order_id, 'frozen')
    return json_response({"success": True})

async def api_order_cancel(request):
    data = await request.json()
    user_id = get_auth_user_id(request, data)
    if not user_id:
        return json_response({"success": False, "error": "Avtorizatsiya talab qilinadi!"}, status=401)

    order_id = int(data.get('order_id', 0))
    order = database.get_order(order_id)
    if not order or order[6] != 'active':
        return json_response({"success": False, "error": "Buyurtma faol emas!"})
    if order[1] != user_id and not database.is_admin(user_id, config.ADMIN_ID):
        return json_response({"success": False, "error": "Ushbu buyurtma sizga tegishli emas!"}, status=403)

    diller_bot = order[4]
    diller_msg_id = order[5]
    if diller_msg_id:
        await userbot.click_diller_button(diller_bot, diller_msg_id, "Cancel")

    database.update_order_status(order_id, 'cancelled')
    return json_response({"success": True})

async def api_rating(request):
    leaders_raw = database.get_top_rating(limit=10)
    leaders = []
    for row in leaders_raw:
        uname, fname, count = row
        display_name = f"@{uname}" if uname else (fname or "Foydalanuvchi")
        leaders.append({
            "display_name": display_name,
            "count": count
        })
    return json_response({"leaders": leaders})

async def api_history(request):
    user_id = get_auth_user_id(request)
    if not user_id:
        return json_response({"history": []})

    history_raw = database.get_user_history(user_id, limit=20)
    history = []
    for row in history_raw:
        phone, st, created_at = row
        history.append({
            "phone": phone,
            "status": st,
            "created_at": str(created_at)
        })
    return json_response({"history": history})

async def api_withdraw(request):
    data = await request.json()
    user_id = get_auth_user_id(request, data)
    if not user_id:
        return json_response({"success": False, "error": "Avtorizatsiya talab qilinadi!"}, status=401)

    amount = float(data.get('amount', 0))
    card = str(data.get('card_details', '')).strip()

    if amount < 100000:
        return json_response({"success": False, "error": "Minimal yechish summasi: 100,000 so'm"})
    if len(card) < 16:
        return json_response({"success": False, "error": "Karta raqami xato!"})

    ok, res = database.create_withdrawal(user_id, amount, card)
    if not ok:
        return json_response({"success": False, "error": res})

    return json_response({"success": True, "withdrawal_id": res})

async def api_withdrawals(request):
    user_id = get_auth_user_id(request)
    if not user_id:
        return json_response({"withdrawals": []})

    rows = database.get_user_withdrawals(user_id)
    withdrawals = []
    for r in rows:
        w_id, amt, card, st, dt = r
        withdrawals.append({
            "id": w_id,
            "amount": amt,
            "card_details": card,
            "status": st,
            "date": str(dt)
        })
    return json_response({"withdrawals": withdrawals})

# ==========================================
# WEB APP: KARTALAR VA AVTO-PREMIUM API
# ==========================================

auto_buy_statuses = {}

async def api_get_cards(request):
    user_id = get_auth_user_id(request)
    if not user_id:
        return json_response({"cards": []})
    
    rows = database.get_user_cards(user_id)
    cards = []
    for r in rows:
        if len(r) >= 11:
            c_id, c_num, exp_m, exp_y, cvv, c_name, used_c, max_l, st, is_def, dt = r[:11]
        else:
            c_id, c_num, exp_m, exp_y, cvv, used_c, max_l, st, is_def, dt = r[:10]
            c_name = ""
        mask_num = f"**** {c_num[-4:]}" if len(c_num) >= 4 else "****"
        cards.append({
            "id": c_id,
            "masked_number": mask_num,
            "cardholder_name": c_name,
            "exp_month": exp_m,
            "exp_year": exp_y,
            "used_count": used_c,
            "max_limit": max_l,
            "status": st,
            "is_default": bool(is_def)
        })
    return json_response({"cards": cards})

async def api_add_card(request):
    data = await request.json()
    user_id = get_auth_user_id(request, data)
    if not user_id:
        return json_response({"success": False, "error": "Avtorizatsiya talab qilinadi!"}, status=401)

    card_number = str(data.get('card_number', ''))
    exp_month = str(data.get('exp_month', ''))
    exp_year = str(data.get('exp_year', ''))
    cvv = str(data.get('cvv', ''))
    cardholder_name = str(data.get('cardholder_name', '')).strip()

    clean_num = "".join(filter(str.isdigit, card_number))
    if len(clean_num) != 16:
        return json_response({"success": False, "error": "Karta raqami 16 ta raqam bo'lishi kerak!"})
    if not exp_month or not exp_year or len(cvv) != 3:
        return json_response({"success": False, "error": "Amal qilish muddati yoki CVV xato!"})

    # Ism-familiya tekshiruvi (M.M yoki M. Eshmatov emas, to'liq Eshmatov Toshmat)
    if "." in cardholder_name:
        return json_response({"success": False, "error": "Qisqartirilgan format (M.M yoki M. Eshmatov) qabul qilinmaydi! To'liq yozing."})
    parts = [p for p in cardholder_name.split() if p]
    if len(parts) < 2 or any(len(p) < 2 for p in parts):
        return json_response({"success": False, "error": "Ism va familiyani to'liq yozing (Masalan: Eshmatov Toshmat)!"})

    clean_name = " ".join(parts).title()
    card_id = database.add_user_card(user_id, clean_num, exp_month, exp_year, cvv, cardholder_name=clean_name, max_limit=3)
    return json_response({"success": True, "card_id": card_id, "cardholder_name": clean_name})

async def api_delete_card(request):
    data = await request.json()
    user_id = get_auth_user_id(request, data)
    if not user_id:
        return json_response({"success": False, "error": "Avtorizatsiya talab qilinadi!"}, status=401)

    card_id = int(data.get('card_id', 0))
    database.delete_user_card(card_id, user_id)
    return json_response({"success": True})

async def api_auto_buy(request):
    data = await request.json()
    user_id = get_auth_user_id(request, data)
    if not user_id:
        return json_response({"success": False, "error": "Avtorizatsiya talab qilinadi!"}, status=401)

    active_card = database.get_active_card_for_user(user_id)
    if not active_card:
        user_cards = database.get_user_cards(user_id)
        if user_cards:
            return json_response({"success": False, "needs_card": True, "error": "Barcha kartalaringiz limiti to'lgan (3/3 ta). Yangi karta qo'shing!"})
        return json_response({"success": False, "needs_card": True, "error": "Avval to'lov kartangizni qo'shing!"})

    import auto_buyer

    auto_buy_statuses[user_id] = {
        "step": 1,
        "total_steps": 6,
        "title": "Boshlanmoqda",
        "text": "Dillerdan yangi raqam so'ralmoqda...",
        "extra": {},
        "completed": False,
        "error": None
    }

    async def web_status_callback(step_num, total_steps, title, text, extra):
        auto_buy_statuses[user_id] = {
            "step": step_num,
            "total_steps": total_steps,
            "title": title,
            "text": text,
            "extra": extra,
            "completed": extra.get("completed", False),
            "error": extra.get("error", None)
        }

    asyncio.create_task(auto_buyer.run_auto_purchase_flow(user_id, active_card, web_status_callback))
    return json_response({"success": True, "message": "Avto-olish jarayoni boshlandi!"})

async def api_auto_status(request):
    user_id = get_auth_user_id(request)
    if not user_id:
        return json_response({"error": "Avtorizatsiya talab qilinadi!"}, status=401)
    
    st = auto_buy_statuses.get(user_id, {
        "step": 0,
        "total_steps": 6,
        "title": "Kutilmoqda",
        "text": "Faol avto jarayon yo'q",
        "extra": {},
        "completed": False,
        "error": None
    })
    return json_response(st)

def create_webapp_app():
    app = web.Application()

    # CORS options
    app.router.add_route('OPTIONS', '/{tail:.*}', handle_options)

    # Static UI routes
    app.router.add_get('/', handle_index)
    app.router.add_get('/index.html', handle_index)
    app.router.add_get('/app.js', handle_app_js)

    # REST APIs
    app.router.add_get('/api/user/me', api_user_me)
    app.router.add_post('/api/order/get_number', api_get_number)
    app.router.add_post('/api/order/get_code', api_get_code)
    app.router.add_post('/api/order/received', api_order_received)
    app.router.add_post('/api/order/freeze', api_order_freeze)
    app.router.add_post('/api/order/cancel', api_order_cancel)
    app.router.add_get('/api/rating', api_rating)
    app.router.add_get('/api/history', api_history)
    app.router.add_post('/api/withdraw', api_withdraw)
    app.router.add_get('/api/withdrawals', api_withdrawals)

    # Cards & Auto-Buy APIs
    app.router.add_get('/api/cards', api_get_cards)
    app.router.add_post('/api/cards/add', api_add_card)
    app.router.add_post('/api/cards/delete', api_delete_card)
    app.router.add_post('/api/order/auto_buy', api_auto_buy)
    app.router.add_get('/api/order/auto_status', api_auto_status)

    return app

async def start_webapp_server(host='0.0.0.0', port=8080):
    app = create_webapp_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    logger.info(f"🌐 Telegram Mini App server started on http://{host}:{port}")
    return runner
