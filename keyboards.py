from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from config import SUPPORT_URL, TARIFFS


def main_menu_kb() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton('💰 Купить подписку'))
    kb.add(KeyboardButton('🔑 Мой ключ'), KeyboardButton('📅 Статус подписки'))
    kb.add(KeyboardButton('👥 Реферальная программа'), KeyboardButton('🎁 Промокод'))
    kb.add(KeyboardButton('🆘 Поддержка'), KeyboardButton('📖 Инструкция'))
    return kb


def tariffs_kb(discount: int = 0) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=1)
    for key, t in TARIFFS.items():
        price = t['price']
        if discount:
            discounted = int(price * (100 - discount) / 100)
            label = f'{t["name"]} — ~~{price}₽~~ {discounted}₽ (-{discount}%)'
        else:
            label = f'{t["name"]} — {price}₽'
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
