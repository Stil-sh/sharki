import os
from dotenv import load_dotenv

load_dotenv()

# ── Telegram ──────────────────────────────────────────────────────────────────
BOT_TOKEN     = os.getenv('BOT_TOKEN',     '8646823051:AAFDxz7zJSifThYiKcLFGxoGMZ9oB2zuJSA')
ADMIN_IDS     = [int(x.strip()) for x in os.getenv('ADMIN_IDS', '7062072067').split(',') if x.strip()]
ADMIN_CHAT_ID = int(os.getenv('ADMIN_CHAT_ID', '7062072067'))

# ── База данных ────────────────────────────────────────────────────────────────
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://user:password@localhost:5432/sharkivpn')

# ── Сервер ─────────────────────────────────────────────────────────────────────
PORT       = int(os.getenv('PORT', 8080))
# Публичный домен Railway — используется для формирования subscription URL
PUBLIC_URL = os.getenv('PUBLIC_URL', 'https://worker-production-f472.up.railway.app')

# ── Тарифы ─────────────────────────────────────────────────────────────────────
TARIFFS = {
    '1m':      {'name': '1 месяц',     'days': 30,   'price': 50},
    '3m':      {'name': '3 месяца',    'days': 90,   'price': 150},
    'forever': {'name': 'Навсегда 🔥', 'days': None, 'price': 500},
}

# ── GitHub: исходный список серверов ──────────────────────────────────────────
SERVERS_URL = os.getenv(
    'SERVERS_URL',
    'https://raw.githubusercontent.com/Denis-space/v1/refs/heads/main/servers.txt'
)

# ── Реквизиты для ручной оплаты ────────────────────────────────────────────────
PAYMENT_CARD = '2200 7007 5758 6709'
PAYMENT_BANK = 'Сбербанк'
PAYMENT_NAME = 'Иван С.'

# ── Ссылки на приложение Happ ──────────────────────────────────────────────────
SUPPORT_URL      = 'https://t.me/sharkivpn_support'
HAPP_URL_ANDROID = 'https://play.google.com/store/apps/details?id=ru.happ.vpn'
HAPP_URL_IOS     = 'https://apps.apple.com/app/happ-proxy-utility/id6504287480'
