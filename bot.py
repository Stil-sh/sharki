import logging
import asyncio
from datetime import datetime, timezone, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.dispatcher.filters import Text
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import config
import db
from keyboards import (
    main_menu_kb, tariffs_kb, payment_confirm_kb,
    admin_payment_kb, support_kb
)
from utils import generate_vpn_key, format_subscription_status, notify_expiring_subscriptions

# ── Логирование ───────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

# ── Инициализация ─────────────────────────────────────────────────────────────
bot      = Bot(token=config.BOT_TOKEN, parse_mode='Markdown')
storage  = MemoryStorage()
dp       = Dispatcher(bot, storage=storage)


# ── FSM состояния ─────────────────────────────────────────────────────────────
class PromoState(StatesGroup):
    waiting_code = State()

class BroadcastState(StatesGroup):
    waiting_text = State()

class PromoCreateState(StatesGroup):
    waiting_data = State()

class GiveSubState(StatesGroup):
    waiting_data = State()


# ═════════════════════════════════════════════════════════════════════════════
#   /start
# ═════════════════════════════════════════════════════════════════════════════

@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    args = message.get_args()
    referrer_id = None
    if args and args.startswith('ref_'):
        try:
            referrer_id = int(args.split('_')[1])
            if referrer_id == message.from_user.id:
                referrer_id = None
        except Exception:
            pass

    await db.upsert_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name,
        referrer_id
    )

    name = message.from_user.first_name or 'друг'

    # Сообщаем рефереру
    if referrer_id:
        try:
            await bot.send_message(
                referrer_id,
                f'🎉 По вашей реферальной ссылке зарегистрировался новый пользователь!\n'
                f'Вы получаете скидку 10% на следующую покупку — просто упомяните это в чате поддержки.'
            )
        except Exception:
            pass

    await message.answer(
        f'🦈 *Привет, {name}! Добро пожаловать в SHARKIVPN!*\n\n'
        f'Мы обеспечиваем быстрый и надёжный VPN для России и СНГ.\n\n'
        f'🔒 Без логов · ⚡ Высокая скорость · 🌍 30+ серверов\n\n'
        f'Выберите нужный пункт меню:',
        reply_markup=main_menu_kb()
    )


# ═════════════════════════════════════════════════════════════════════════════
#   ПОКУПКА ПОДПИСКИ
# ═════════════════════════════════════════════════════════════════════════════

@dp.message_handler(Text(equals='💰 Купить подписку'))
async def menu_buy(message: types.Message):
    await message.answer(
        '💰 *Выберите тариф:*\n\n'
        '🥈 *1 месяц* — 50₽\n'
        '🥇 *3 месяца* — 150₽ _(выгоднее на 17%)_\n'
        '💎 *Навсегда* — 500₽ _(лучший выбор 🔥)_\n\n'
        '💳 Оплата переводом на карту. После оплаты нажмите «Я оплатил».',
        reply_markup=tariffs_kb()
    )


@dp.callback_query_handler(lambda c: c.data.startswith('buy:'))
async def callback_buy_tariff(call: types.CallbackQuery):
    tariff_key = call.data.split(':')[1]
    tariff     = config.TARIFFS.get(tariff_key)
    if not tariff:
        await call.answer('Неизвестный тариф.', show_alert=True)
        return

    user_id    = call.from_user.id
    amount     = tariff['price']
    payment_id = await db.create_payment(user_id, tariff_key, amount)

    text = (
        f'💳 *Оплата тарифа «{tariff["name"]}»*\n\n'
        f'Сумма: *{amount}₽*\n\n'
        f'Переведите точную сумму на карту:\n'
        f'`{config.PAYMENT_CARD}`\n'
        f'Банк: {config.PAYMENT_BANK}\n'
        f'Получатель: {config.PAYMENT_NAME}\n\n'
        f'⚠️ В комментарии к переводу укажите ваш ID: `{user_id}`\n\n'
        f'После оплаты нажмите кнопку ниже — администратор проверит платёж '
        f'и выдаст ключ в течение нескольких минут.'
    )
    await call.message.answer(text, reply_markup=payment_confirm_kb(payment_id))
    await call.answer()


@dp.callback_query_handler(lambda c: c.data.startswith('paid:'))
async def callback_paid(call: types.CallbackQuery):
    payment_id = int(call.data.split(':')[1])
    payment    = await db.get_payment(payment_id)
    if not payment:
        await call.answer('Платёж не найден.', show_alert=True)
        return
    if payment['status'] != 'pending':
        await call.answer('Этот платёж уже обработан.', show_alert=True)
        return

    tariff = config.TARIFFS.get(payment['tariff'], {})
    user   = await db.get_user(call.from_user.id)
    name   = (user['first_name'] or '') if user else ''
    uname  = ('@' + user['username']) if (user and user['username']) else str(call.from_user.id)

    # Уведомляем администратора
    await bot.send_message(
        config.ADMIN_CHAT_ID,
        f'🔔 *Новая заявка на оплату!*\n\n'
        f'👤 Пользователь: {name} {uname}\n'
        f'🆔 ID: `{call.from_user.id}`\n'
        f'📦 Тариф: {tariff.get("name", payment["tariff"])}\n'
        f'💰 Сумма: {payment["amount"]}₽\n'
        f'🆔 Платёж №{payment_id}',
        reply_markup=admin_payment_kb(payment_id, call.from_user.id)
    )

    await call.message.edit_reply_markup()
    await call.message.answer(
        '✅ *Заявка отправлена администратору!*\n\n'
        'Ключ будет выдан после проверки платежа. Обычно это занимает до 10 минут.'
    )
    await call.answer()


@dp.callback_query_handler(lambda c: c.data.startswith('cancel:'))
async def callback_cancel_payment(call: types.CallbackQuery):
    payment_id = int(call.data.split(':')[1])
    await db.update_payment_status(payment_id, 'cancelled')
    await call.message.edit_reply_markup()
    await call.message.answer('❌ Оплата отменена. Вы можете начать заново.')
    await call.answer()


# ═════════════════════════════════════════════════════════════════════════════
#   АДМИН: ПОДТВЕРЖДЕНИЕ / ОТКЛОНЕНИЕ ПЛАТЕЖА
# ═════════════════════════════════════════════════════════════════════════════

@dp.callback_query_handler(lambda c: c.data.startswith('adm_confirm:'))
async def admin_confirm(call: types.CallbackQuery):
    if call.from_user.id not in config.ADMIN_IDS:
        await call.answer('Нет доступа.', show_alert=True)
        return

    _, payment_id_str, user_id_str = call.data.split(':')
    payment_id = int(payment_id_str)
    user_id    = int(user_id_str)
    payment    = await db.get_payment(payment_id)

    if not payment or payment['status'] == 'paid':
        await call.answer('Платёж уже обработан.', show_alert=True)
        return

    tariff_key = payment['tariff']
    tariff     = config.TARIFFS.get(tariff_key, {})
    days       = tariff.get('days')

    vpn_key  = generate_vpn_key()
    end_date = None
    if days is not None:
        end_date = datetime.now(timezone.utc) + timedelta(days=days)

    await db.create_subscription(user_id, vpn_key, tariff_key, end_date)
    await db.update_payment_status(payment_id, 'paid')

    period_text = f'до *{end_date.strftime("%d.%m.%Y")}*' if end_date else '*навсегда* 🔥'

    # Сообщаем пользователю
    try:
        await bot.send_message(
            user_id,
            f'🎉 *Оплата подтверждена!*\n\n'
            f'Тариф: *{tariff.get("name", tariff_key)}*\n'
            f'Подписка активна {period_text}\n\n'
            f'🔑 *Ваш VPN-ключ:*\n`{vpn_key}`\n\n'
            f'Вставьте ключ в приложение SHARKIVPN и наслаждайтесь свободным интернетом! 🦈\n\n'
            f'📖 Нажмите «Инструкция» если нужна помощь с подключением.'
        )
    except Exception as e:
        logger.error('Не удалось отправить ключ %s: %s', user_id, e)

    await call.message.edit_text(
        call.message.text + f'\n\n✅ *Подтверждено. Ключ выдан.*'
    )
    await call.answer('✅ Платёж подтверждён!')


@dp.callback_query_handler(lambda c: c.data.startswith('adm_reject:'))
async def admin_reject(call: types.CallbackQuery):
    if call.from_user.id not in config.ADMIN_IDS:
        await call.answer('Нет доступа.', show_alert=True)
        return

    _, payment_id_str, user_id_str = call.data.split(':')
    payment_id = int(payment_id_str)
    user_id    = int(user_id_str)

    await db.update_payment_status(payment_id, 'rejected', 'Отклонено администратором')

    try:
        await bot.send_message(
            user_id,
            '❌ *Оплата не подтверждена.*\n\n'
            'Возможно, перевод не поступил или указана неверная сумма.\n'
            'Обратитесь в поддержку, если считаете это ошибкой.',
            reply_markup=support_kb()
        )
    except Exception:
        pass

    await call.message.edit_text(call.message.text + '\n\n❌ *Отклонено.*')
    await call.answer('❌ Платёж отклонён.')


# ═════════════════════════════════════════════════════════════════════════════
#   МОЙ КЛЮЧ / СТАТУС
# ═════════════════════════════════════════════════════════════════════════════

@dp.message_handler(Text(equals='🔑 Мой ключ'))
async def menu_key(message: types.Message):
    sub = await db.get_active_subscription(message.from_user.id)
    if sub is None:
        await message.answer(
            '❌ У вас нет активной подписки.\n'
            'Нажмите «💰 Купить подписку».'
        )
        return
    await message.answer(
        f'🔑 *Ваш VPN-ключ:*\n\n`{sub["key"]}`\n\n'
        f'Скопируйте ключ и вставьте в приложение SHARKIVPN.'
    )


@dp.message_handler(Text(equals='📅 Статус подписки'))
async def menu_status(message: types.Message):
    sub  = await db.get_active_subscription(message.from_user.id)
    text = format_subscription_status(sub)
    await message.answer(text)


# ═════════════════════════════════════════════════════════════════════════════
#   ПРОМОКОД
# ═════════════════════════════════════════════════════════════════════════════

@dp.message_handler(Text(equals='🎁 Промокод'))
async def menu_promo(message: types.Message):
    await message.answer(
        '🎁 *Введите промокод:*\n\n'
        'Отправьте код в следующем сообщении.'
    )
    await PromoState.waiting_code.set()


@dp.message_handler(state=PromoState.waiting_code)
async def process_promo(message: types.Message, state: FSMContext):
    code  = message.text.strip().upper()
    promo = await db.get_promo(code)

    if not promo:
        await message.answer(
            '❌ *Промокод недействителен или уже использован.*\n'
            'Попробуйте другой.'
        )
        await state.finish()
        return

    discount = promo['discount']
    await db.use_promo(code)
    await state.finish()

    await message.answer(
        f'✅ *Промокод активирован!*\n\n'
        f'Скидка *{discount}%* на следующую покупку применена.\n\n'
        f'Выберите тариф:',
        reply_markup=tariffs_kb(discount=discount)
    )


# ═════════════════════════════════════════════════════════════════════════════
#   РЕФЕРАЛЬНАЯ ПРОГРАММА
# ═════════════════════════════════════════════════════════════════════════════

@dp.message_handler(Text(equals='👥 Реферальная программа'))
async def menu_referral(message: types.Message):
    user_id  = message.from_user.id
    user     = await db.get_user(user_id)
    ref_cnt  = user['ref_count'] if user else 0
    ref_link = f'https://t.me/{(await bot.get_me()).username}?start=ref_{user_id}'

    await message.answer(
        f'👥 *Реферальная программа SHARKIVPN*\n\n'
        f'Приглашайте друзей и получайте бонусы!\n\n'
        f'🔗 Ваша реферальная ссылка:\n`{ref_link}`\n\n'
        f'👤 Приглашено друзей: *{ref_cnt}*\n\n'
        f'🎁 За каждого нового пользователя по вашей ссылке\n'
        f'вы получаете скидку 10% на следующую покупку.\n'
        f'Свяжитесь с поддержкой для получения бонуса.',
        reply_markup=support_kb()
    )


# ═════════════════════════════════════════════════════════════════════════════
#   ПОДДЕРЖКА / ИНСТРУКЦИЯ
# ═════════════════════════════════════════════════════════════════════════════

@dp.message_handler(Text(equals='🆘 Поддержка'))
async def menu_support(message: types.Message):
    await message.answer(
        '🆘 *Поддержка SHARKIVPN*\n\n'
        'Если у вас возникли проблемы — напишите нам, мы ответим в течение нескольких минут.',
        reply_markup=support_kb()
    )


@dp.message_handler(Text(equals='📖 Инструкция'))
async def menu_instruction(message: types.Message):
    await message.answer(
        '📖 *Инструкция по подключению SHARKIVPN*\n\n'
        '*1.* Оплатите подписку и получите ключ\n'
        '*2.* Скачайте приложение:\n'
        '   • Android: [Google Play](https://play.google.com)\n'
        '   • iOS: [App Store](https://apps.apple.com)\n'
        '   • Windows/Mac: наш сайт\n\n'
        '*3.* Откройте приложение → «Добавить сервер»\n'
        '*4.* Вставьте ваш ключ в поле ввода\n'
        '*5.* Нажмите «Подключиться» ✅\n\n'
        '❓ Если что-то не работает — обратитесь в поддержку.',
        disable_web_page_preview=True,
        reply_markup=support_kb()
    )


# ═════════════════════════════════════════════════════════════════════════════
#   АДМИН КОМАНДЫ
# ═════════════════════════════════════════════════════════════════════════════

def is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS


@dp.message_handler(commands=['stats'])
async def cmd_stats(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer('⛔ Нет доступа.')
        return

    s = await db.get_stats()
    lines = [
        '📊 *Статистика SHARKIVPN*\n',
        f'👤 Всего пользователей: *{s["total"]}*',
        f'🆕 Новых за 24ч: *{s["new_today"]}*',
        f'✅ Активных подписок: *{s["active"]}*',
        f'⏳ Ожидают оплаты: *{s["pending"]}*',
        f'💰 Общая выручка: *{s["revenue"]}₽*',
    ]
    if s['by_tariff']:
        lines.append('\n📦 *По тарифам:*')
        for row in s['by_tariff']:
            t = config.TARIFFS.get(row['tariff'], {})
            lines.append(f'  • {t.get("name", row["tariff"])}: {row["cnt"]} шт.')

    await message.answer('\n'.join(lines))


@dp.message_handler(commands=['pending'])
async def cmd_pending(message: types.Message):
    """Список ожидающих платежей."""
    if not is_admin(message.from_user.id):
        await message.answer('⛔ Нет доступа.')
        return

    payments = await db.get_pending_payments()
    if not payments:
        await message.answer('✅ Ожидающих платежей нет.')
        return

    for p in payments:
        t     = config.TARIFFS.get(p['tariff'], {})
        name  = p['first_name'] or ''
        uname = ('@' + p['username']) if p['username'] else str(p['user_id'])
        await message.answer(
            f'🔔 *Платёж №{p["id"]}*\n'
            f'👤 {name} {uname}\n'
            f'📦 {t.get("name", p["tariff"])} — {p["amount"]}₽\n'
            f'🕐 {p["created_at"].strftime("%d.%m.%Y %H:%M")}',
            reply_markup=admin_payment_kb(p['id'], p['user_id'])
        )


@dp.message_handler(commands=['give'])
async def cmd_give(message: types.Message):
    """Выдать подписку вручную. /give <user_id> <tariff_key>"""
    if not is_admin(message.from_user.id):
        await message.answer('⛔ Нет доступа.')
        return

    args = message.get_args().split()
    if len(args) < 2:
        await message.answer(
            'Использование: `/give <user_id> <tariff_key>`\n'
            'Тарифы: `1m`, `3m`, `forever`'
        )
        return

    try:
        uid        = int(args[0])
        tariff_key = args[1]
        tariff     = config.TARIFFS.get(tariff_key)
        if not tariff:
            await message.answer(f'Неизвестный тариф: {tariff_key}')
            return

        days     = tariff['days']
        vpn_key  = generate_vpn_key()
        end_date = None
        if days is not None:
            end_date = datetime.now(timezone.utc) + timedelta(days=days)

        await db.create_subscription(uid, vpn_key, tariff_key, end_date)
        period = f'до {end_date.strftime("%d.%m.%Y")}' if end_date else 'навсегда'

        await message.answer(f'✅ Подписка выдана пользователю `{uid}` ({period}).\nКлюч: `{vpn_key}`')

        try:
            await bot.send_message(
                uid,
                f'🎁 *Вам выдана подписка SHARKIVPN!*\n\n'
                f'Тариф: *{tariff["name"]}*\n\n'
                f'🔑 *Ваш ключ:*\n`{vpn_key}`'
            )
        except Exception:
            pass

    except Exception as e:
        await message.answer(f'Ошибка: {e}')


@dp.message_handler(commands=['addpromo'])
async def cmd_addpromo(message: types.Message):
    """Создать промокод. /addpromo <CODE> <скидка%> <кол-во использований>"""
    if not is_admin(message.from_user.id):
        await message.answer('⛔ Нет доступа.')
        return

    args = message.get_args().split()
    if len(args) < 3:
        await message.answer('Использование: `/addpromo CODE 20 100`\n(код, скидка%, макс.исп.)')
        return

    code, discount, max_uses = args[0].upper(), int(args[1]), int(args[2])
    await db.create_promo(code, discount, max_uses)
    await message.answer(f'✅ Промокод `{code}` создан.\nСкидка: {discount}%, использований: {max_uses}')


@dp.message_handler(commands=['broadcast'])
async def cmd_broadcast(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer('⛔ Нет доступа.')
        return

    text = message.get_args()
    if not text:
        await message.answer('Использование: `/broadcast Текст сообщения`')
        return

    await message.answer('📤 Начинаю рассылку...')
    user_ids   = await db.get_all_user_ids()
    sent, fail = 0, 0
    for uid in user_ids:
        try:
            await bot.send_message(uid, f'📢 *Объявление SHARKIVPN*\n\n{text}')
            sent += 1
            await asyncio.sleep(0.05)  # Антифлуд
        except Exception:
            fail += 1

    await message.answer(f'✅ Рассылка завершена.\nОтправлено: {sent}\nОшибок: {fail}')


@dp.message_handler(commands=['help'])
async def cmd_help(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer(
        '🛠 *Команды администратора:*\n\n'
        '/stats — статистика\n'
        '/pending — ожидающие платежи\n'
        '/give `<user_id> <tariff>` — выдать подписку вручную\n'
        '/addpromo `<CODE> <скидка> <макс>` — создать промокод\n'
        '/broadcast `<текст>` — рассылка всем\n'
    )


# ═════════════════════════════════════════════════════════════════════════════
#   ЗАПУСК
# ═════════════════════════════════════════════════════════════════════════════

async def on_startup(dispatcher):
    await db.init_db()

    scheduler = AsyncIOScheduler(timezone='Europe/Moscow')
    scheduler.add_job(
        notify_expiring_subscriptions,
        'cron', hour=10, minute=0,
        args=[bot]
    )
    scheduler.start()
    logger.info('Планировщик запущен.')

    # Уведомляем администратора о запуске
    try:
        await bot.send_message(
            config.ADMIN_CHAT_ID,
            '🟢 *SHARKIVPN бот запущен!*\n'
            'Все системы работают нормально.\n'
            'Введите /help для списка команд.'
        )
    except Exception:
        pass

    logger.info('SHARKIVPN бот запущен!')


async def on_shutdown(dispatcher):
    try:
        await bot.send_message(config.ADMIN_CHAT_ID, '🔴 Бот остановлен.')
    except Exception:
        pass
    await bot.close()


if __name__ == '__main__':
    executor.start_polling(
        dp,
        skip_updates=True,
        on_startup=on_startup,
        on_shutdown=on_shutdown
    )
