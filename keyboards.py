from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from config import SUPPORT_URL, TARIFFS, HAPP_URL_ANDROID, HAPP_URL_IOS


def main_menu_kb() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton('💰 Купить подписку'))
    kb.add(KeyboardButton('📱 Моя подписка'), KeyboardButton('📅 Статус подписки'))
    kb.add(KeyboardButton('👥 Реферальная программа'))
    kb.add(KeyboardButton('🆘 Поддержка'), KeyboardButton('📖 Инструкция'))
    return kb


def tariffs_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=1)
    for key, t in TARIFFS.items():
        label = f'{t["name"]} — {t["price"]}₽'
        kb.add(InlineKeyboardButton(label, callback_data=f'buy:{key}'))
    return kb


def payment_confirm_kb(payment_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton('✅ Я оплатил', callback_data=f'paid:{payment_id}'),
        InlineKeyboardButton('❌ Отмена',    callback_data=f'cancel:{payment_id}'),
    )
    return kb


def admin_payment_kb(payment_id: int, user_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton('✅ Подтвердить', callback_data=f'adm_confirm:{payment_id}:{user_id}'),
        InlineKeyboardButton('❌ Отклонить',   callback_data=f'adm_reject:{payment_id}:{user_id}'),
    )
    return kb


def support_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton('🆘 Написать в поддержку', url=SUPPORT_URL))
    return kb


def happ_install_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton('🤖 Android', url=HAPP_URL_ANDROID),
        InlineKeyboardButton('🍎 iOS',     url=HAPP_URL_IOS),
    )
    return kb


def subscription_kb(sub_url: str) -> InlineKeyboardMarkup:
    """
    Кнопка импорта подписки в Happ.
    happ://import?url=... — deep link, открывает Happ и добавляет подписку.
    """
    from urllib.parse import quote
    happ_deeplink = f'happ://import?url={quote(sub_url, safe="")}'
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton('📲 Добавить подписку в Happ', url=happ_deeplink))
    kb.add(
        InlineKeyboardButton('🤖 Скачать Happ Android', url=HAPP_URL_ANDROID),
        InlineKeyboardButton('🍎 Скачать Happ iOS',     url=HAPP_URL_IOS),
    )
    return kb
