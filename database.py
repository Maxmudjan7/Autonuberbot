import sqlite3
import math
from datetime import datetime, timedelta

DB_NAME = "bot_database.db"

def get_connection():
    conn = sqlite3.connect(DB_NAME, timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=30000;")
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # Foydalanuvchilar jadvali
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            balance REAL DEFAULT 0,
            total_earned REAL DEFAULT 0,
            total_withdrawn REAL DEFAULT 0,
            successful_premiums INTEGER DEFAULT 0,
            status TEXT DEFAULT 'pending', -- active, pending, banned
            join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Ustunlar borligini tekshirish va qo'shish (Migratsiya)
    cursor.execute("PRAGMA table_info(users)")
    user_columns = [col[1] for col in cursor.fetchall()]
    if "successful_premiums" not in user_columns:
        cursor.execute("ALTER TABLE users ADD COLUMN successful_premiums INTEGER DEFAULT 0")
    if "full_name" not in user_columns:
        cursor.execute("ALTER TABLE users ADD COLUMN full_name TEXT")

    # Buyurtmalar jadvali
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            phone_number TEXT,
            code TEXT,
            diller_bot_username TEXT,
            diller_msg_id INTEGER,
            userbot_id INTEGER,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP,
            finished_at TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')
    cursor.execute("PRAGMA table_info(orders)")
    order_columns = [col[1] for col in cursor.fetchall()]
    if "userbot_id" not in order_columns:
        cursor.execute("ALTER TABLE orders ADD COLUMN userbot_id INTEGER")
    if "diller_bot_username" not in order_columns:
        cursor.execute("ALTER TABLE orders ADD COLUMN diller_bot_username TEXT")
    if "diller_msg_id" not in order_columns:
        cursor.execute("ALTER TABLE orders ADD COLUMN diller_msg_id INTEGER")
    if "expires_at" not in order_columns:
        cursor.execute("ALTER TABLE orders ADD COLUMN expires_at TIMESTAMP")
    if "finished_at" not in order_columns:
        cursor.execute("ALTER TABLE orders ADD COLUMN finished_at TIMESTAMP")
    if "password" not in order_columns:
        cursor.execute("ALTER TABLE orders ADD COLUMN password TEXT")

    # Userbotlar jadvali
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS userbots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            phone TEXT,
            tg_id TEXT DEFAULT 'Noma''lum',
            session_string TEXT,
            priority INTEGER DEFAULT 100,
            status TEXT DEFAULT 'active',
            holat TEXT DEFAULT 'bosh',
            active_numbers INTEGER DEFAULT 0,
            added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Sozlamalar jadvali
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            setting_name TEXT PRIMARY KEY,
            setting_value TEXT
        )
    ''')

    # Diller botlar (Any botlar) jadvali
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS any_bots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bot_username TEXT UNIQUE,
            priority INTEGER DEFAULT 100,
            status TEXT DEFAULT 'active',
            added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Foydalanuvchi to'lov kartalari jadvali (Telegram Premium uchun)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_cards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            card_number TEXT,
            exp_month TEXT,
            exp_year TEXT,
            cvv TEXT,
            used_count INTEGER DEFAULT 0,
            max_limit INTEGER DEFAULT 3,
            status TEXT DEFAULT 'active',
            is_default INTEGER DEFAULT 1,
            cardholder_name TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')
    cursor.execute("PRAGMA table_info(user_cards)")
    card_columns = [col[1] for col in cursor.fetchall()]
    if "cardholder_name" not in card_columns:
        cursor.execute("ALTER TABLE user_cards ADD COLUMN cardholder_name TEXT DEFAULT ''")

    # Adminlar jadvali
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            admin_id INTEGER PRIMARY KEY,
            username TEXT,
            added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute("PRAGMA table_info(admins)")
    admin_columns = [col[1] for col in cursor.fetchall()]
    if "username" not in admin_columns:
        cursor.execute("ALTER TABLE admins ADD COLUMN username TEXT")

    # Pul yechishlar jadvali
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS withdrawals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount REAL,
            card_details TEXT,
            status TEXT DEFAULT 'pending',
            request_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Broadcastlar jadvali
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS broadcasts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            message_id INTEGER,
            target_count INTEGER,
            limit_count INTEGER DEFAULT 0,
            sent_count INTEGER DEFAULT 0,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute("PRAGMA table_info(broadcasts)")
    bcast_columns = [col[1] for col in cursor.fetchall()]
    if "chat_id" not in bcast_columns:
        cursor.execute("ALTER TABLE broadcasts ADD COLUMN chat_id INTEGER")
    if "limit_count" not in bcast_columns:
        cursor.execute("ALTER TABLE broadcasts ADD COLUMN limit_count INTEGER DEFAULT 0")
    if "created_at" not in bcast_columns:
        cursor.execute("ALTER TABLE broadcasts ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")

    # 3-rasmdagi barcha standart sozlamalar
    default_settings = [
        ('account_active_minutes', '60'),
        ('admin_username', 'Im_darkhacker'),
        ('any_bot_cancel_buffer_minutes', '2'),
        ('auto_premium_enabled', 'false'),
        ('auto_premium_mode', 'off'),
        ('auto_premium_notify_admins', 'true'),
        ('auto_premium_user_ids', ''),
        ('is_accepting_orders', 'true'),
        ('max_active_numbers_per_user', '5'),
        ('max_numbers_per_fetch', '10'),
        ('min_withdraw_amount', '100000'),
        ('premium_price_monthly', '40000'),
        ('reward_per_account', '40.000'),
        ('stat_total_get_code', '1351'),
        ('stat_total_get_number', '1460'),
        ('diller_bot_username', ''),
        ('channel_number_logs', ''),
        ('channel_payment_logs', ''),
        ('webapp_url', ''),
        ('bestbit_ref_link', 'https://t.me/BestBitBot?start=U6278841173'),
        ('bestbit_target_channel', '@meningtolovlarim'),
        ('bestbit_auto_spin', 'true'),
        ('proxy_enabled', 'false'),
        ('proxy_url', ''),
        ('proxy_rotation_url', ''),
        ('proxy_auto_rotate_minutes', '1')
    ]
    cursor.executemany('INSERT OR IGNORE INTO settings (setting_name, setting_value) VALUES (?, ?)', default_settings)

    conn.commit()
    conn.close()

# Foydalanuvchini ro'yxatdan o'tkazish yoki olish
def register_or_get_user(user_id: int, username: str, full_name: str, is_admin_user: bool = False):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, status, successful_premiums FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if not row:
        init_st = 'active' if is_admin_user else 'pending'
        cursor.execute(
            "INSERT INTO users (user_id, username, full_name, status) VALUES (?, ?, ?, ?)",
            (user_id, username, full_name, init_st)
        )
        conn.commit()
        status, premiums = init_st, 0
    else:
        cursor.execute("UPDATE users SET username = ?, full_name = ? WHERE user_id = ?", (username, full_name, user_id))
        conn.commit()
        status, premiums = row[1], row[2]
    conn.close()
    return status, premiums

# Sozlamalar
def get_setting(key: str, default: str = "") -> str:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT setting_value FROM settings WHERE setting_name = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else default

def set_setting(key: str, value: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (setting_name, setting_value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()

def get_all_settings():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT setting_name, setting_value FROM settings ORDER BY setting_name ASC")
    rows = cursor.fetchall()
    conn.close()
    return rows

def increment_setting_counter(key: str, amount: int = 1):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT setting_value FROM settings WHERE setting_name = ?", (key,))
    row = cursor.fetchone()
    current = int(row[0]) if row and row[0].isdigit() else 0
    new_val = str(current + amount)
    cursor.execute("INSERT OR REPLACE INTO settings (setting_name, setting_value) VALUES (?, ?)", (key, new_val))
    conn.commit()
    conn.close()
    return new_val

# Userbotlar boshqaruvi (Rasm 1)
def get_all_userbots():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, phone, tg_id, status, holat, active_numbers, session_string FROM userbots ORDER BY id ASC")
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_active_userbot():
    """Raqam olish uchun faol userbotni olish"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, phone, tg_id, session_string FROM userbots WHERE status = 'active' ORDER BY holat ASC, id ASC LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    return row

def add_userbot_record(name: str, phone: str, tg_id: str, session_string: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO userbots (name, phone, tg_id, session_string, status, holat) VALUES (?, ?, ?, ?, 'active', 'bosh')",
        (name, phone, tg_id, session_string)
    )
    ub_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return ub_id

def toggle_userbot_status(ub_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM userbots WHERE id = ?", (ub_id,))
    row = cursor.fetchone()
    if row:
        new_st = 'inactive' if row[0] == 'active' else 'active'
        cursor.execute("UPDATE userbots SET status = ? WHERE id = ?", (new_st, ub_id))
        conn.commit()
    conn.close()

def delete_userbot_record(ub_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM userbots WHERE id = ?", (ub_id,))
    conn.commit()
    conn.close()

# Orderlar
def create_order(user_id: int, phone_number: str, diller_bot: str, diller_msg_id: int = None, userbot_id: int = None, duration_seconds: int = 300) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    expires_at = datetime.now() + timedelta(seconds=duration_seconds)
    cursor.execute('''
        INSERT INTO orders (user_id, phone_number, diller_bot_username, diller_msg_id, userbot_id, status, expires_at)
        VALUES (?, ?, ?, ?, ?, 'active', ?)
    ''', (user_id, phone_number, diller_bot, diller_msg_id, userbot_id, expires_at))
    order_id = cursor.lastrowid

    # Ichki tranzaksiyada bitta ulanishda hisoblagichni oshirish
    cursor.execute("SELECT setting_value FROM settings WHERE setting_name = 'stat_total_get_number'")
    s_row = cursor.fetchone()
    cur_cnt = int(s_row[0]) if s_row and s_row[0].isdigit() else 0
    cursor.execute("INSERT OR REPLACE INTO settings (setting_name, setting_value) VALUES ('stat_total_get_number', ?)", (str(cur_cnt + 1),))

    conn.commit()
    conn.close()
    return order_id

def update_order_status(order_id: int, status: str, code: str = None, password: str = None):
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now()
    if code:
        if password:
            cursor.execute("UPDATE orders SET status = ?, code = ?, password = ?, finished_at = ? WHERE id = ?", (status, code, password, now, order_id))
        else:
            cursor.execute("UPDATE orders SET status = ?, code = ?, finished_at = ? WHERE id = ?", (status, code, now, order_id))
        
        # Bitta ulanishda hisoblagichni oshirish (deadlock bo'lmasligi uchun)
        cursor.execute("SELECT setting_value FROM settings WHERE setting_name = 'stat_total_get_code'")
        s_row = cursor.fetchone()
        cur_cnt = int(s_row[0]) if s_row and s_row[0].isdigit() else 0
        cursor.execute("INSERT OR REPLACE INTO settings (setting_name, setting_value) VALUES ('stat_total_get_code', ?)", (str(cur_cnt + 1),))
    else:
        cursor.execute("UPDATE orders SET status = ?, finished_at = ? WHERE id = ?", (status, now, order_id))
    
    if status == 'completed':
        cursor.execute("SELECT user_id FROM orders WHERE id = ?", (order_id,))
        row = cursor.fetchone()
        if row:
            u_id = row[0]
            cursor.execute("UPDATE users SET successful_premiums = successful_premiums + 1, total_earned = total_earned + 40000, balance = balance + 40000 WHERE user_id = ?", (u_id,))

    conn.commit()
    conn.close()

def get_order(order_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, user_id, phone_number, code, diller_bot_username, diller_msg_id, status, created_at, expires_at, userbot_id, password FROM orders WHERE id = ?", (order_id,))
    row = cursor.fetchone()
    conn.close()
    return row

def get_active_order_for_user(user_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, user_id, phone_number, code, diller_bot_username, diller_msg_id, status, created_at, expires_at, userbot_id, password FROM orders WHERE user_id = ? AND status = 'active' ORDER BY id DESC LIMIT 1", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row

# Kengaytirilgan Statistika (Rasm 2)
def get_full_admin_statistics():
    conn = get_connection()
    cursor = conn.cursor()

    # Userbotlar
    cursor.execute("SELECT COUNT(*) FROM userbots")
    total_ub = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM userbots WHERE status = 'active'")
    active_ub = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM userbots WHERE holat = 'band'")
    busy_ub = cursor.fetchone()[0]

    # Orderlar umumiy
    cursor.execute("SELECT COUNT(*) FROM orders")
    total_orders = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM orders WHERE status = 'completed'")
    completed_orders = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM orders WHERE status = 'frozen' OR status = 'cancelled'")
    failed_orders = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM orders WHERE status = 'expired'")
    expired_orders = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM orders WHERE status = 'active'")
    active_orders = cursor.fetchone()[0]

    # Harakatlar
    stat_get_number = get_setting('stat_total_get_number', '1460')
    stat_get_code = get_setting('stat_total_get_code', '1351')

    # Foydalanuvchilar
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    cursor.execute("SELECT SUM(balance), SUM(total_earned), SUM(total_withdrawn) FROM users")
    ubal, uearn, uwith = cursor.fetchone()
    total_balance = ubal or 0
    total_earned = uearn or 0
    total_paid = uwith or 0

    # So'nggi 24 soat
    since_24h = datetime.now() - timedelta(hours=24)
    cursor.execute("SELECT COUNT(*) FROM users WHERE join_date >= ?", (since_24h,))
    new_users_24h = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM orders WHERE created_at >= ?", (since_24h,))
    orders_24h = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM orders WHERE status = 'completed' AND created_at >= ?", (since_24h,))
    completed_24h = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM orders WHERE (status = 'frozen' OR status = 'cancelled') AND created_at >= ?", (since_24h,))
    failed_24h = cursor.fetchone()[0]

    cursor.execute("SELECT SUM(total_earned), SUM(total_withdrawn) FROM users WHERE join_date >= ?", (since_24h,))
    e24, p24 = cursor.fetchone()
    earned_24h = e24 or 0
    paid_24h = p24 or 0

    conn.close()

    return {
        "total_ub": total_ub,
        "active_ub": active_ub,
        "busy_ub": busy_ub,
        "ready_cnt": max(0, int(stat_get_number) - total_orders),
        "pending_cnt": active_orders,
        "finish_cnt": completed_orders,
        "total_numbers": total_orders + 100,
        "stat_get_number": stat_get_number,
        "stat_get_code": stat_get_code,
        "total_orders": total_orders,
        "completed_orders": completed_orders,
        "failed_orders": failed_orders,
        "expired_orders": expired_orders,
        "active_orders": active_orders,
        "total_users": total_users,
        "total_balance": total_balance,
        "total_earned": total_earned,
        "total_paid": total_paid,
        "new_users_24h": new_users_24h,
        "get_number_24h": orders_24h,
        "orders_24h": orders_24h,
        "completed_24h": completed_24h,
        "failed_24h": failed_24h,
        "earned_24h": earned_24h,
        "paid_24h": paid_24h
    }

# Foydalanuvchi shaxsiy statistikasi (5-rasm)
def get_user_statistics(user_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM orders WHERE user_id = ?", (user_id,))
    total_orders = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM orders WHERE user_id = ? AND status = 'completed'", (user_id,))
    completed_orders = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM orders WHERE user_id = ? AND status = 'frozen'", (user_id,))
    frozen_orders = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM orders WHERE user_id = ? AND status = 'expired'", (user_id,))
    expired_orders = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM orders WHERE user_id = ? AND status = 'active'", (user_id,))
    active_orders = cursor.fetchone()[0]

    since_24h = datetime.now() - timedelta(hours=24)
    cursor.execute("SELECT COUNT(*) FROM orders WHERE user_id = ? AND created_at >= ?", (user_id, since_24h))
    orders_24h = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM orders WHERE user_id = ? AND status = 'completed' AND created_at >= ?", (user_id, since_24h))
    completed_24h = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM orders WHERE user_id = ? AND status = 'frozen' AND created_at >= ?", (user_id, since_24h))
    frozen_24h = cursor.fetchone()[0]
    conn.close()

    return {
        "total_orders": total_orders,
        "completed_orders": completed_orders,
        "frozen_orders": frozen_orders,
        "expired_orders": expired_orders,
        "active_orders": active_orders,
        "orders_24h": orders_24h,
        "completed_24h": completed_24h,
        "frozen_24h": frozen_24h
    }

def get_user_history(user_id: int, limit: int = 15):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT phone_number, status, created_at FROM orders WHERE user_id = ? ORDER BY id DESC LIMIT ?", (user_id, limit))
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_top_rating(limit: int = 10):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT username, full_name, successful_premiums FROM users WHERE successful_premiums > 0 ORDER BY successful_premiums DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    return rows

# Pending Userlar
def get_pending_users(limit: int = 15):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, username, full_name, join_date FROM users WHERE status = 'pending' ORDER BY join_date DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    return rows

def set_user_status(user_id: int, new_status: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET status = ? WHERE user_id = ?", (new_status, user_id))
    conn.commit()
    conn.close()

# Foydalanuvchilar
def get_all_users(limit: int = 20):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, username, full_name, balance, status FROM users ORDER BY join_date DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_users_page(page: int = 0, page_size: int = 10):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    total_count = cursor.fetchone()[0]
    offset = page * page_size
    cursor.execute(
        "SELECT user_id, username, full_name, balance, status, join_date FROM users ORDER BY join_date DESC LIMIT ? OFFSET ?",
        (page_size, offset)
    )
    users = cursor.fetchall()
    conn.close()
    total_pages = math.ceil(total_count / page_size) if total_count > 0 else 1
    return users, total_count, total_pages

def get_user_full_detail(user_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, username, full_name, balance, total_earned, total_withdrawn, successful_premiums, status, join_date FROM users WHERE user_id = ?", (user_id,))
    user_row = cursor.fetchone()
    if not user_row:
        conn.close()
        return None

    # Buyurtmalar umumiy
    cursor.execute("SELECT COUNT(*) FROM orders WHERE user_id = ?", (user_id,))
    total_orders = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM orders WHERE user_id = ? AND status = 'completed'", (user_id,))
    completed_orders = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM orders WHERE user_id = ? AND (status = 'frozen' OR status = 'cancelled')", (user_id,))
    failed_orders = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM orders WHERE user_id = ? AND status = 'expired'", (user_id,))
    expired_orders = cursor.fetchone()[0]

    # Mukofot hisobi
    try:
        reward_per_acc = float(get_setting('reward_per_account', '40').replace(',', '.'))
    except Exception:
        reward_per_acc = 40.0
    ishlangan = completed_orders * reward_per_acc

    # So'nggi 24 soat
    since_24h = datetime.now() - timedelta(hours=24)
    cursor.execute("SELECT COUNT(*) FROM orders WHERE user_id = ? AND created_at >= ?", (user_id, since_24h))
    orders_24h = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM orders WHERE user_id = ? AND status = 'completed' AND created_at >= ?", (user_id, since_24h))
    completed_24h = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM orders WHERE user_id = ? AND (status = 'frozen' OR status = 'cancelled') AND created_at >= ?", (user_id, since_24h))
    failed_24h = cursor.fetchone()[0]
    ishlangan_24h = completed_24h * reward_per_acc

    conn.close()

    return {
        "user_id": user_row[0],
        "username": user_row[1],
        "full_name": user_row[2],
        "balance": user_row[3] or 0.0,
        "total_earned": user_row[4] or 0.0,
        "total_withdrawn": user_row[5] or 0.0,
        "successful_premiums": user_row[6] or 0,
        "status": user_row[7],
        "join_date": user_row[8],
        "total_orders": total_orders,
        "completed": completed_orders,
        "failed": failed_orders,
        "expired": expired_orders,
        "ishlangan": ishlangan,
        "orders_24h": orders_24h,
        "completed_24h": completed_24h,
        "failed_24h": failed_24h,
        "ishlangan_24h": ishlangan_24h
    }

def update_user_balance(user_id: int, new_balance: float):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET balance = ? WHERE user_id = ?", (new_balance, user_id))
    conn.commit()
    conn.close()

def clear_user_statistics(user_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM orders WHERE user_id = ?", (user_id,))
    cursor.execute("UPDATE users SET successful_premiums = 0, total_earned = 0 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def clear_all_statistics():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM orders")
    cursor.execute("UPDATE users SET successful_premiums = 0, total_earned = 0, total_withdrawn = 0")
    conn.commit()
    conn.close()

def get_user_withdrawals(user_id: int, limit: int = 10):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, amount, card_details, status, request_date FROM withdrawals WHERE user_id = ? ORDER BY id DESC LIMIT ?", (user_id, limit))
    rows = cursor.fetchall()
    conn.close()
    return rows

def toggle_user_ban(user_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    new_st = 'banned' if row and row[0] != 'banned' else 'active'
    cursor.execute("UPDATE users SET status = ? WHERE user_id = ?", (new_st, user_id))
    conn.commit()
    conn.close()
    return new_st

def set_user_ban_status(user_id: int, status: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET status = ? WHERE user_id = ?", (status, user_id))
    conn.commit()
    conn.close()

# Adminlar (Rasm 4)
def get_all_admins():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT admin_id, username, added_date FROM admins")
    rows = cursor.fetchall()
    conn.close()
    return rows

def add_admin(admin_id: int, username: str = ""):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO admins (admin_id, username) VALUES (?, ?)", (admin_id, username))
    cursor.execute("UPDATE users SET status = 'active' WHERE user_id = ?", (admin_id,))
    conn.commit()
    conn.close()

def delete_admin(admin_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM admins WHERE admin_id = ?", (admin_id,))
    conn.commit()
    conn.close()

def is_admin(user_id: int, main_admin_id: int) -> bool:
    if str(user_id) == str(main_admin_id):
        return True
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT admin_id FROM admins WHERE admin_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return bool(row)

# Any botlar (Diller botlar)
def get_active_diller_bot() -> str:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT bot_username FROM any_bots WHERE status = 'active' ORDER BY priority ASC LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    if row:
        return row[0]
    return get_setting("diller_bot_username", "")

def get_all_any_bots():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, bot_username, priority, status FROM any_bots ORDER BY priority ASC")
    rows = cursor.fetchall()
    conn.close()
    return rows

def add_any_bot(bot_username: str, priority: int = 100):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO any_bots (bot_username, priority, status) VALUES (?, ?, 'active')", (bot_username, priority))
    conn.commit()
    conn.close()

def delete_any_bot(bot_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM any_bots WHERE id = ?", (bot_id,))
    conn.commit()
    conn.close()

def toggle_any_bot(bot_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM any_bots WHERE id = ?", (bot_id,))
    row = cursor.fetchone()
    if row:
        new_st = 'inactive' if row[0] == 'active' else 'active'
        cursor.execute("UPDATE any_bots SET status = ? WHERE id = ?", (new_st, bot_id))
        conn.commit()
    conn.close()

# Broadcast (Rasm 5)
def create_broadcast(chat_id: int, message_id: int, target_count: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO broadcasts (chat_id, message_id, target_count, limit_count, status) VALUES (?, ?, ?, ?, 'pending')",
        (chat_id, message_id, target_count, target_count)
    )
    b_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return b_id

def get_broadcast(b_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, chat_id, message_id, target_count, limit_count, sent_count, status FROM broadcasts WHERE id = ?", (b_id,))
    row = cursor.fetchone()
    conn.close()
    return row

def update_broadcast_limit(b_id: int, new_limit: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE broadcasts SET limit_count = ? WHERE id = ?", (new_limit, b_id))
    conn.commit()
    conn.close()

def delete_broadcast(b_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM broadcasts WHERE id = ?", (b_id,))
    conn.commit()
    conn.close()

def create_withdrawal(user_id: int, amount: float, card_details: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if not row or row[0] < amount:
        conn.close()
        return False, "Balansingizda yetarli mablag' mavjud emas!"
    cursor.execute("UPDATE users SET balance = balance - ?, total_withdrawn = total_withdrawn + ? WHERE user_id = ?", (amount, amount, user_id))
    cursor.execute("INSERT INTO withdrawals (user_id, amount, card_details, status) VALUES (?, ?, ?, 'pending')", (user_id, amount, card_details))
    w_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return True, w_id

def get_user_withdrawals(user_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, amount, card_details, status, request_date FROM withdrawals WHERE user_id = ? ORDER BY id DESC LIMIT 10", (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return rows

# ==========================================
# FOYDALANUVCHI KARTALARI (PREMIUM TO'LOV)
# ==========================================

def add_user_card(user_id: int, card_number: str, exp_month: str, exp_year: str, cvv: str, cardholder_name: str = "", max_limit: int = 3):
    clean_number = "".join(filter(str.isdigit, str(card_number)))
    clean_month = str(exp_month).zfill(2)
    clean_year = str(exp_year)[-2:] if len(str(exp_year)) >= 2 else str(exp_year)
    clean_cvv = str(cvv).strip()
    clean_name = str(cardholder_name).strip()

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM user_cards WHERE user_id = ? AND is_default = 1", (user_id,))
    has_default = cursor.fetchone()
    is_default = 0 if has_default else 1

    cursor.execute('''
        INSERT INTO user_cards (user_id, card_number, exp_month, exp_year, cvv, cardholder_name, used_count, max_limit, status, is_default)
        VALUES (?, ?, ?, ?, ?, ?, 0, ?, 'active', ?)
    ''', (user_id, clean_number, clean_month, clean_year, clean_cvv, clean_name, max_limit, is_default))
    card_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return card_id

def get_user_cards(user_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, card_number, exp_month, exp_year, cvv, cardholder_name, used_count, max_limit, status, is_default, created_at
        FROM user_cards
        WHERE user_id = ?
        ORDER BY is_default DESC, id DESC
    ''', (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_active_card_for_user(user_id: int):
    """Foydalanuvchining limiti to'lmagan (used_count < max_limit) faol kartasini qaytaradi"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, card_number, exp_month, exp_year, cvv, cardholder_name, used_count, max_limit, status, is_default
        FROM user_cards
        WHERE user_id = ? AND status = 'active' AND used_count < max_limit
        ORDER BY is_default DESC, id ASC LIMIT 1
    ''', (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row

def increment_card_usage(card_id: int):
    """Karta ishlatilganlik hisoblagichini oshiradi. 3 taga yetsa status='limit_reached' bo'ladi"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE user_cards SET used_count = used_count + 1 WHERE id = ?", (card_id,))
    cursor.execute("SELECT used_count, max_limit, user_id FROM user_cards WHERE id = ?", (card_id,))
    row = cursor.fetchone()
    limit_reached = False
    if row and row[0] >= row[1]:
        cursor.execute("UPDATE user_cards SET status = 'limit_reached' WHERE id = ?", (card_id,))
        limit_reached = True
    conn.commit()
    conn.close()
    return limit_reached

def delete_user_card(card_id: int, user_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM user_cards WHERE id = ? AND user_id = ?", (card_id, user_id))
    conn.commit()
    conn.close()

def set_default_card(card_id: int, user_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE user_cards SET is_default = 0 WHERE user_id = ?", (user_id,))
    cursor.execute("UPDATE user_cards SET is_default = 1 WHERE id = ? AND user_id = ?", (card_id, user_id))
    conn.commit()
    conn.close()
