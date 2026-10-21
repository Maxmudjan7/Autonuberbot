import asyncio
import os
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
import config

async def main():
    print("=" * 50)
    print("   TELEGRAM USERBOT AKKAUNTNI ULASH")
    print("=" * 50)
    print("Bu orqali sizning hisobingiz Diller botlariga ulanadi.\n")

    client = TelegramClient(config.SESSION_NAME, config.API_ID, config.API_HASH)
    await client.connect()

    if await client.is_user_authorized():
        me = await client.get_me()
        print(f"✅ Akkaunt allaqachon ulangan: {me.first_name} (@{me.username or 'username yoq'})")
        await client.disconnect()
        return

    phone = input("Telefon raqamingizni kiriting (masalan: +998901234567): ").strip()
    try:
        sent = await client.send_code_request(phone)
    except Exception as e:
        print(f"❌ Xatolik: {e}")
        await client.disconnect()
        return

    code = input("Telegram ilovangizga kelgan 5 xonali kodni kiriting: ").strip()
    try:
        await client.sign_in(phone, code)
    except SessionPasswordNeededError:
        password = input("Ikki bosqichli parolingizni (2FA password) kiriting: ").strip()
        await client.sign_in(password=password)
    except Exception as e:
        print(f"❌ Xatolik: {e}")
        await client.disconnect()
        return

    me = await client.get_me()
    print("\n" + "=" * 50)
    print(f"🎉 MUVAFFAQITYATLI ULINDI!")
    print(f"👤 Ism: {me.first_name}")
    print(f"📱 Telefon: {me.phone}")
    print(f"🆔 ID: {me.id}")
    print("Endi bot to'liq diller botlar bilan ishlay oladi!")
    print("=" * 50)
    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
