# Autonuberbot

Telegram bot, Userbot (Telethon) va WebApp orqali boshqariluvchi avtomatlashtirilgan tizim.

## 🚀 Texnologiyalar
- **Python 3.10+**
- **Aiogram 3.x** - Telegram Bot Framework
- **Telethon** - Telegram MTProto Userbot Client
- **FastAPI / Uvicorn** - WebApp server
- **SQLite / aiosqlite** - Ma'lumotlar bazasi
- **python-dotenv** - Konfiguratsiya va xavfsizlik boshqaruvi

## ⚙️ O'rnatish va Ishga Tushirish

1. **Repozitoriyni klonlash:**
```bash
git clone https://github.com/<username>/<repo-name>.git
cd Autonuberbot
```

2. **Kutubxonalarni o'rnatish:**
```bash
pip install -r requirements.txt
```

3. **Konfiguratsiya:**
`.env.example` faylidan nusxa olib `.env` faylini yarating va ma'lumotlaringizni kiriting:
```bash
cp .env.example .env
```

`.env` ichidagi parametrlarni to'ldiring:
- `BOT_TOKEN`: @BotFather dan olingan bot tokeni
- `ADMIN_ID`: Telegram hisobingiz ID raqami
- `API_ID` & `API_HASH`: my.telegram.org dan olingan API ma'lumotlari

4. **Userbot akkauntini ulash:**
```bash
python login_userbot.py
```
Yoki `AKKAUNTNI_ULASH.bat` faylini ishga tushiring.

5. **Botni ishga tushirish:**
```bash
python main.py
```
Yoki `ISHGA_TUSHIRISH.bat` faylini ishga tushiring.

## 🔒 Xavfsizlik
Maxfiy ma'lumotlar (`.env`, `*.session`, `*.db`) `.gitignore` ga kiritilgan bo'lib, ommaviy repozitoriyga chiqib ketishdan himoyalangan.
