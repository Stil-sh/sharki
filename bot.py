import logging
import asyncio
from datetime import datetime, timezone, timedelta
from aiohttp import web
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
    admin_payment_kb, support_kb, happ_install_kb, subscription_kb
)
from utils import format_subscription_status, notify_expiring_subscriptions
from happ import generate_token, make_sub_url, handle_subscription

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

bot     = Bot(token=config.BOT_TOKEN, parse_mode='Markdown')
storage = MemoryStorage()
dp      = Dispatcher(bot, storage=storage)


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

    if referrer_id:
        try:
            await bot.send_message(
                referrer_id,
                '🎉 По вашей реферальной ссылке зарегистрировался новый пользователь!\n'
                'Свяжитесь с поддержкой для получения бонуса.'
            )
        except Exception:
            pass

    name = message.from_user.first_name or 'друг'
    await message.answer(
        f'🦈 *Привет, {name}! Добро пожаловать в SHARKIVPN!*\n\n'
        f'Быстрый и надёжный VPN для России и СНГ.\n\n'
        f'🔒 Без логов · ⚡ Высокая скорость · 🌍 30+ серверов\n\n'
        f'Выберите нужный пункт меню:',
        reply_markup=main_menu_kb()
    )


# ═════════════════════════════════════════════════════════════════════════════
#   ПОКУПКА
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

    await call.message.answer(
        f'💳 *Оплата тарифа «{tariff["name"]}»*\n\n'
        f'Сумма: *{amount}₽*\n\n'
        f'Переведите на карту:\n'
        f'`{config.PAYMENT_CARD}`\n'
        f'Банк: {config.PAYMENT_BANK} · Получатель: {config.PAYMENT_NAME}\n\n'
        f'⚠️ В комментарии укажите ваш ID: `{user_id}`\n\n'
        f'После оплаты нажмите кнопку ниже — подписка придёт в течение нескольких минут.',
        reply_markup=payment_confirm_kb(payment_id)
    )
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

    await bot.send_message(
        config.ADMIN_CHAT_ID,
        f'🔔 *Новая заявка на оплату!*\n\n'
        f'👤 {name} {uname}\n'
        f'🆔 ID: `{call.from_user.id}`\n'
        f'📦 Тариф: {tariff.get("name", payment["tariff"])}\n'
        f'💰 Сумма: {payment["amount"]}₽\n'
        f'🆔 Платёж №{payment_id}',
        reply_markup=admin_payment_kb(payment_id, call.from_user.id)
    )

    await call.message.edit_reply_markup()
    await call.message.answer(
        '✅ *Заявка отправлена администратору!*\n\n'
        'Подписка будет выдана после проверки. Обычно до 10 минут.'
    )
    await call.answer()


@dp.callback_query_handler(lambda c: c.data.startswith('cancel:'))
async def callback_cancel_payment(call: types.CallbackQuery):
    payment_id = int(call.data.split(':')[1])
    await db.update_payment_status(payment_id, 'cancelled')
    await call.message.edit_reply_markup()
    await call.message.answer('❌ Оплата отменена.')
    await call.answer()


# ═════════════════════════════════════════════════════════════════════════════
#   ВЫДАЧА ПОДПИСКИ (общая функция)
# ═════════════════════════════════════════════════════════════════════════════

async def _deliver_subscription(user_id: int, tariff_key: str, end_date):
    """
    Создаёт подписку в БД, генерирует уникальный токен,
    формирует subscription URL и отправляет пользователю.
    """
    token   = generate_token()
    sub_url = make_sub_url(token)

    await db.create_subscription(user_id, token, tariff_key, end_date)

    tariff      = config.TARIFFS.get(tariff_key, {})
    tariff_name = tariff.get('name', tariff_key)
    period_text = f'до *{end_date.strftime("%d.%m.%Y")}*' if end_date else '*навсегда* 🔥'

    await bot.send_message(
        user_id,
        f'🎉 *Подписка активирована!*\n\n'
        f'📦 Тариф: *{tariff_name}*\n'
        f'⏳ Действует {period_text}\n\n'
        f'*Как подключиться:*\n'
        f'1️⃣ Установите Happ (кнопки ниже)\n'
        f'2️⃣ Нажмите «📲 Добавить подписку в Happ»\n'
        f'3️⃣ Happ автоматически загрузит все серверы '
        f'и покажет дату окончания подписки\n\n'
        f'🔄 Серверы обновляются в Happ автоматически каждые 24ч.\n\n'
        f'❓ Если кнопка не открывается — скопируйте ссылку вручную:\n'
        f'`{sub_url}`',
        reply_markup=subscription_kb(sub_url)
    )
    logger.info('Подписка выдана пользователю %s, токен %s', user_id, token)


# ═════════════════════════════════════════════════════════════════════════════
#   АДМИН: подтверждение / отклонение платежа
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
    end_date   = None
    if days is not None:
        end_date = datetime.now(timezone.utc) + timedelta(days=days)

    await db.update_payment_status(payment_id, 'paid')

    try:
        await _deliver_subscription(user_id, tariff_key, end_date)
    except Exception as e:
        logger.error('Ошибка выдачи подписки %s: %s', user_id, e)
        await call.answer('⚠️ Ошибка выдачи, проверь логи.', show_alert=True)
        return

    await call.message.edit_text(call.message.text + '\n\n✅ *Подтверждено. Подписка выдана.*')
    await call.answer('✅ Готово!')


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
    await call.answer('❌ Отклонено.')


# ═════════════════════════════════════════════════════════════════════════════
#   МОЯ ПОДПИСКА / СТАТУС
# ═════════════════════════════════════════════════════════════════════════════

@dp.message_handler(Text(equals='📱 Моя подписка'))
async def menu_my_subscription(message: types.Message):
    sub = await db.get_active_subscription(message.from_user.id)
    if sub is None:
        await message.answer(
            '❌ У вас нет активной подписки.\n'
            'Нажмите «💰 Купить подписку».'
        )
        return

    sub_url     = make_sub_url(sub['token'])
    end_date    = sub['end_date']
    period_text = f'до *{end_date.strftime("%d.%m.%Y")}*' if end_date else '*навсегда* 🔥'

    await message.answer(
        f'📱 *Ваша подписка SHARKIVPN*\n\n'
        f'⏳ Действует {period_text}\n\n'
        f'Нажмите кнопку для добавления/обновления в Happ.\n\n'
        f'Ссылка подписки:\n`{sub_url}`',
        reply_markup=subscription_kb(sub_url)
    )


@dp.message_handler(Text(equals='📅 Статус подписки'))
async def menu_status(message: types.Message):
    sub  = await db.get_active_subscription(message.from_user.id)
    text = format_subscription_status(sub)
    await message.answer(text)


# ═════════════════════════════════════════════════════════════════════════════
#   РЕФЕРАЛЬНАЯ ПРОГРАММА
# ═════════════════════════════════════════════════════════════════════════════

@dp.message_handler(Text(equals='👥 Реферальная программа'))
async def menu_referral(message: types.Message):
    user_id  = message.from_user.id
    user     = await db.get_user(user_id)
    ref_cnt  = user['ref_count'] if user else 0
    bot_info = await bot.get_me()
    ref_link = f'https://t.me/{bot_info.username}?start=ref_{user_id}'

    await message.answer(
        f'👥 *Реферальная программа SHARKIVPN*\n\n'
        f'🔗 Ваша ссылка:\n`{ref_link}`\n\n'
        f'👤 Приглашено: *{ref_cnt}*\n\n'
        f'За каждого нового пользователя — скидка 10% на следующую покупку.\n'
        f'Свяжитесь с поддержкой для активации бонуса.',
        reply_markup=support_kb()
    )


# ═════════════════════════════════════════════════════════════════════════════
#   ПОДДЕРЖКА / ИНСТРУКЦИЯ
# ═════════════════════════════════════════════════════════════════════════════

@dp.message_handler(Text(equals='🆘 Поддержка'))
async def menu_support(message: types.Message):
    await message.answer(
        '🆘 *Поддержка SHARKIVPN*\n\n'
        'Напишите нам — ответим в течение нескольких минут.',
        reply_markup=support_kb()
    )


@dp.message_handler(Text(equals='📖 Инструкция'))
async def menu_instruction(message: types.Message):
    await message.answer(
        '📖 *Инструкция по подключению SHARKIVPN*\n\n'
        '*1.* Оплатите подписку\n'
        '*2.* Установите приложение *Happ*:\n\n'
        '*3.* После подтверждения оплаты нажмите\n'
        '«📲 Добавить подписку в Happ»\n\n'
        'Happ автоматически загрузит все серверы и '
        'покажет дату окончания подписки в интерфейсе.\n\n'
        '🔄 Серверы обновляются автоматически каждые 24 часа.\n\n'
        '❓ Проблемы? Напишите в поддержку.',
        reply_markup=happ_install_kb()
    )


# ═════════════════════════════════════════════════════════════════════════════
#   АДМИН КОМАНДЫ
# ═════════════════════════════════════════════════════════════════════════════

def is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS


@dp.message_handler(commands=['stats'])
async def cmd_stats(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    s = await db.get_stats()
    lines = [
        '📊 *Статистика SHARKIVPN*\n',
        f'👤 Всего: *{s["total"]}*',
        f'🆕 Новых за 24ч: *{s["new_today"]}*',
        f'✅ Активных подписок: *{s["active"]}*',
        f'⏳ Ожидают оплаты: *{s["pending"]}*',
        f'💰 Выручка: *{s["revenue"]}₽*',
    ]
    if s['by_tariff']:
        lines.append('\n📦 *По тарифам:*')
        for row in s['by_tariff']:
            t = config.TARIFFS.get(row['tariff'], {})
            lines.append(f'  • {t.get("name", row["tariff"])}: {row["cnt"]} шт.')
    await message.answer('\n'.join(lines))


@dp.message_handler(commands=['pending'])
async def cmd_pending(message: types.Message):
    if not is_admin(message.from_user.id):
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
    if not is_admin(message.from_user.id):
        return
    args = message.get_args().split()
    if len(args) < 2:
        await message.answer('Использование: `/give <user_id> <tariff>`\nТарифы: `1m` `3m` `forever`')
        return
    try:
        uid        = int(args[0])
        tariff_key = args[1]
        tariff     = config.TARIFFS.get(tariff_key)
        if not tariff:
            await message.answer(f'Неизвестный тариф: {tariff_key}')
            return
        days     = tariff['days']
        end_date = None
        if days is not None:
            end_date = datetime.now(timezone.utc) + timedelta(days=days)
        await _deliver_subscription(uid, tariff_key, end_date)
        period = f'до {end_date.strftime("%d.%m.%Y")}' if end_date else 'навсегда'
        await message.answer(f'✅ Подписка выдана `{uid}` ({period}).')
    except Exception as e:
        await message.answer(f'Ошибка: {e}')


@dp.message_handler(commands=['broadcast'])
async def cmd_broadcast(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    text = message.get_args()
    if not text:
        await message.answer('Использование: `/broadcast Текст`')
        return
    await message.answer('📤 Начинаю рассылку...')
    user_ids   = await db.get_all_user_ids()
    sent, fail = 0, 0
    for uid in user_ids:
        try:
            await bot.send_message(uid, f'📢 *Объявление SHARKIVPN*\n\n{text}')
            sent += 1
            await asyncio.sleep(0.05)
        except Exception:
            fail += 1
    await message.answer(f'✅ Рассылка: {sent} отправлено, {fail} ошибок.')


@dp.message_handler(commands=['help'])
async def cmd_help(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer(
        '🛠 *Команды администратора:*\n\n'
        '/stats — статистика\n'
        '/pending — ожидающие платежи\n'
        '/give `<user_id> <tariff>` — выдать подписку\n'
        '/broadcast `<текст>` — рассылка\n'
    )


# ═════════════════════════════════════════════════════════════════════════════
#   ЗАПУСК: aiohttp-сервер + планировщик
# ═════════════════════════════════════════════════════════════════════════════

async def on_startup(dispatcher):
    await db.init_db()

    # aiohttp-сервер для subscription endpoint
    app = web.Application()
    app.router.add_get('/sub/{token}', handle_subscription)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', config.PORT)
    await site.start()
    logger.info('HTTP-сервер запущен на порту %s', config.PORT)

    # Планировщик уведомлений об истечении
    scheduler = AsyncIOScheduler(timezone='Europe/Moscow')
    scheduler.add_job(
        notify_expiring_subscriptions,
        'cron', hour=10, minute=0, args=[bot]
    )
    scheduler.start()

    try:
        await bot.send_message(
            config.ADMIN_CHAT_ID,
            f'🟢 *SHARKIVPN бот запущен!*\n'
            f'Subscription endpoint: `{config.PUBLIC_URL}/sub/<token>`\n'
            f'/help — список команд.'
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
