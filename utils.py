import secrets
import logging
from datetime import datetime, timezone
from aiogram import Bot
from db import get_expiring_subscriptions

logger = logging.getLogger(__name__)

# Эмодзи для тарифов
TARIFF_EMOJI = {'1m': '🥈', '3m': '🥇', 'forever': '💎'}


def generate_vpn_key() -> str:
    return 'SHARK-' + secrets.token_hex(16).upper()


def format_subscription_status(sub) -> str:
    if sub is None:
        return (
            '❌ *У вас нет активной подписки.*\n\n'
            'Нажмите «💰 Купить подписку», чтобы оформить доступ.'
        )
    tariff_key = sub['tariff']
    emoji      = TARIFF_EMOJI.get(tariff_key, '📦')
    key        = sub['key']
    end_date   = sub['end_date']
    start_date = sub['start_date']

    if end_date is None:
        time_left = '♾️ Навсегда'
        progress  = '████████████ 100%'
    else:
        now      = datetime.now(timezone.utc)
        total    = (end_date - start_date).total_seconds()
        left     = max(0, (end_date - now).total_seconds())
        days_left = max(0, (end_date - now).days)
        end_str  = end_date.strftime('%d.%m.%Y')
        pct      = int((1 - left / total) * 100) if total > 0 else 100
        filled   = int(pct / 10)
        bar      = '█' * filled + '░' * (10 - filled)
        time_left = f'📅 До {end_str} (осталось {days_left} дн.)'
        progress  = f'{bar} {pct}% использовано'

    return (
        f'{emoji} *SHARKIVPN — Ваша подписка*\n\n'
        f'🔑 Ключ: `{key}`\n'
        f'📦 Тариф: {tariff_key}\n'
        f'⏳ {time_left}\n'
        f'📊 {progress}'
    )


async def notify_expiring_subscriptions(bot: Bot):
    logger.info('Проверка истекающих подписок...')
    rows = await get_expiring_subscriptions(days=3)
    for row in rows:
        user_id = row['user_id']
        end_str = row['end_date'].strftime('%d.%m.%Y')
        try:
            await bot.send_message(
                user_id,
                f'⚠️ *Ваша подписка SHARKIVPN истекает {end_str}!*\n\n'
                f'Продлите её, чтобы не потерять доступ 🦈\n'
                f'Нажмите «💰 Купить подписку» в главном меню.',
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.warning('Уведомление не отправлено %s: %s', user_id, e)
