import os
from dotenv import load_dotenv

load_dotenv()

# ── Telegram ──────────────────────────────────────────────────────────────────
BOT_TOKEN  = os.getenv('BOT_TOKEN',  '8646823051:AAFDxz7zJSifThYiKcLFGxoGMZ9oB2zuJSA')
ADMIN_IDS  = [int(x.strip()) for x in os.getenv('ADMIN_IDS', '7062072067').split(',') if x.strip()]
ADMIN_CHAT_ID = int(os.getenv('ADMIN_CHAT_ID', '7062072067'))

# ── База данных ────────────────────────────────────────────────────────────────
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://user:password@localhost:5432/sharkivpn')

# ── Сервер ─────────────────────────────────────────────────────────────────────
PORT = int(os.getenv('PORT', 8080))

# ── Тарифы ─────────────────────────────────────────────────────────────────────
TARIFFS = {
    '1m':      {'name': '1 месяц',     'days': 30,   'price': 50},
    '3m':      {'name': '3 месяца',    'days': 90,   'price': 150},
    'forever': {'name': 'Навсегда 🔥', 'days': None, 'price': 500},
}

# ── Реквизиты для ручной оплаты ────────────────────────────────────────────────
PAYMENT_CARD = '2200 7007 5758 6709'
PAYMENT_BANK = 'Сбербанк'
PAYMENT_NAME = 'Иван С.'

# ── Поддержка ──────────────────────────────────────────────────────────────────
SUPPORT_URL = 'https://t.me/sharkivpn_support'
