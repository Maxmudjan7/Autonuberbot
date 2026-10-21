# smart_glocal.py
"""
Smart Glocal (payment.smart-glocal.com) to'lov tizimi integratsiyasi.
Telegram @PremiumBot invoice havolasidan karta ma'lumotlarini tokenizatsiya qiladi.
"""

import re
import json
import logging
import urllib.request
import urllib.error
import ssl

logger = logging.getLogger(__name__)

SMART_GLOCAL_BASE = "https://payment.smart-glocal.com"

def extract_hash_and_sign(url: str):
    """URL dan hash va sign parametrlarini ajratib oladi"""
    match = re.search(r'tokenize\/([a-zA-Z0-9_\-=]+)\/([a-zA-Z0-9]+)', url)
    if match:
        return match.group(1), match.group(2)
    return None, None

def get_bin_info(bin_number: str, hash_val: str, sign_val: str):
    """Karta BIN (birinchi 6 ta raqami) orqali karta turi va mamlakat kodini oladi"""
    bin_clean = re.sub(r'\D', '', str(bin_number))[:6]
    url = f"{SMART_GLOCAL_BASE}/api/apm/card/{bin_clean}/{hash_val}/{sign_val}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json"
    }
    ctx = ssl.create_default_context()
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            card_info = data.get("cardInfo", {})
            country_code = card_info.get("countryCode", "us")
            return country_code, data
    except Exception as e:
        logger.warning(f"BIN lookup xatosi ({bin_clean}): {e}")
        return "us", {}

def tokenize_card(payment_url: str, card_number: str, exp_month: str, exp_year: str, cvv: str, cardholder_name: str = "TELEGRAM USER"):
    """
    Karta ma'lumotlarini Smart Glocal orqali tokenizatsiya qiladi.
    Muvaffaqiyatli bo'lsa token va type qaytaradi.
    """
    hash_val, sign_val = extract_hash_and_sign(payment_url)
    if not hash_val or not sign_val:
        return {"success": False, "error": "Smart Glocal to'lov URL manzili yaroqsiz!"}

    clean_pan = re.sub(r'\D', '', str(card_number))
    clean_month = str(exp_month).zfill(2)
    clean_year = str(exp_year)[-2:] if len(str(exp_year)) >= 2 else str(exp_year)
    clean_cvv = re.sub(r'\D', '', str(cvv))

    country_code, _ = get_bin_info(clean_pan, hash_val, sign_val)

    url = f"{SMART_GLOCAL_BASE}/api/apm/tokenize/{hash_val}/{sign_val}?country={country_code}"
    
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Origin": SMART_GLOCAL_BASE,
        "Referer": payment_url,
        "Accept": "application/json, text/plain, */*"
    }

    payload = {
        "paymentDetails": {
            "card": {
                "number": clean_pan,
                "expirationMonth": clean_month,
                "expirationYear": clean_year,
                "securityCode": clean_cvv,
                "cardholderName": cardholder_name or "TELEGRAM USER"
            }
        },
        "customerDetails": {
            "email": "user@gmail.com",
            "postalCode": "10001",
            "state": "NY",
            "city": "New York",
            "street": "Broadway 12"
        }
    }

    ctx = ssl.create_default_context()
    data_bytes = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
            res_data = json.loads(resp.read().decode())
            token = res_data.get("token")
            token_type = res_data.get("type", "card")
            title = res_data.get("title", f"**** {clean_pan[-4:]}")
            if token:
                return {
                    "success": True,
                    "token": token,
                    "type": token_type,
                    "title": title
                }
            return {"success": False, "error": "Token olinmadi: " + str(res_data)}
    except urllib.error.HTTPError as e:
        err_body = e.read().decode(errors="ignore")
        logger.error(f"Smart Glocal tokenize HTTP xatolik ({e.code}): {err_body}")
        
        # Limit yoki blok holatlarini aniqlash
        if any(w in err_body.lower() for w in ['limit', 'exceeded', 'decline', 'declined', 'blocked']):
            return {"success": False, "error": "Karta limiti to'lgan yoki bank tomonidan to'lov rad etildi!"}
        if "bank_card.number.invalid_value" in err_body:
            return {"success": False, "error": "Karta raqami noto'g'ri kiritilgan!"}
        return {"success": False, "error": f"To'lov provayderi xatoligi: {err_body}"}
    except Exception as ex:
        logger.error(f"Smart Glocal tokenize xatosi: {ex}")
        return {"success": False, "error": f"Ulanish xatosi: {str(ex)}"}
