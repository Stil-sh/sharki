import asyncpg
import logging
from datetime import datetime
from config import DATABASE_URL

logger = logging.getLogger(__name__)
pool = None


async def init_db():
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
    await create_tables()
    logger.info('БД инициализирована.')


async def create_tables():
    async with pool.acquire() as conn:
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id       BIGINT PRIMARY KEY,
                username      TEXT,
                first_name    TEXT,
                registered_at TIMESTAMPTZ DEFAULT NOW(),
                is_blocked    BOOLEAN DEFAULT FALSE,
                is_admin      BOOLEAN DEFAULT FALSE,
                referrer_id   BIGINT DEFAULT NULL,
                ref_count     INT DEFAULT 0
            )
        ''')
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS subscriptions (
                id         SERIAL PRIMARY KEY,
                user_id    BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
                key        TEXT NOT NULL,
                tariff     TEXT NOT NULL,
                start_date TIMESTAMPTZ DEFAULT NOW(),
                end_date   TIMESTAMPTZ,
                is_active  BOOLEAN DEFAULT TRUE
            )
        ''')
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS payments (
                id         SERIAL PRIMARY KEY,
                user_id    BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
                tariff     TEXT NOT NULL,
                amount     NUMERIC(10,2) NOT NULL,
                status     TEXT DEFAULT 'pending',
                comment    TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        ''')
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS promo_codes (
                code       TEXT PRIMARY KEY,
                discount   INT NOT NULL,
                max_uses   INT NOT NULL,
                used_count INT DEFAULT 0,
                is_active  BOOLEAN DEFAULT TRUE
            )
        ''')
    logger.info('Таблицы созданы.')


# ── Пользователи ──────────────────────────────────────────────────────────────

async def upsert_user(user_id: int, username: str, first_name: str, referrer_id: int = None):
    async with pool.acquire() as conn:
        existing = await conn.fetchrow('SELECT user_id FROM users WHERE user_id = $1', user_id)
        if not existing:
            await conn.execute('''
                INSERT INTO users (user_id, username, first_name, referrer_id)
                VALUES ($1, $2, $3, $4)
            ''', user_id, username, first_name, referrer_id)
            # Засчитываем реферал
            if referrer_id:
                await conn.execute('''
                    UPDATE users SET ref_count = ref_count + 1 WHERE user_id = $1
                ''', referrer_id)
        else:
            await conn.execute('''
                UPDATE users SET username = $1, first_name = $2 WHERE user_id = $3
            ''', username, first_name, user_id)


async def get_user(user_id: int):
    async with pool.acquire() as conn:
        return await conn.fetchrow('SELECT * FROM users WHERE user_id = $1', user_id)


async def get_all_user_ids():
    async with pool.acquire() as conn:
        rows = await conn.fetch('SELECT user_id FROM users WHERE is_blocked = FALSE')
        return [r['user_id'] for r in rows]


async def get_all_users():
    async with pool.acquire() as conn:
        return await conn.fetch('SELECT * FROM users WHERE is_blocked = FALSE')


async def block_user(user_id: int, block: bool = True):
    async with pool.acquire() as conn:
        await conn.execute('UPDATE users SET is_blocked = $1 WHERE user_id = $2', block, user_id)


# ── Подписки ──────────────────────────────────────────────────────────────────

async def get_active_subscription(user_id: int):
    async with pool.acquire() as conn:
        return await conn.fetchrow('''
            SELECT * FROM subscriptions
            WHERE user_id = $1
              AND is_active = TRUE
              AND (end_date IS NULL OR end_date > NOW())
            ORDER BY id DESC LIMIT 1
        ''', user_id)


async def create_subscription(user_id: int, key: str, tariff: str, end_date):
    async with pool.acquire() as conn:
        await conn.execute(
            'UPDATE subscriptions SET is_active = FALSE WHERE user_id = $1', user_id
        )
        await conn.execute('''
            INSERT INTO subscriptions (user_id, key, tariff, end_date)
            VALUES ($1, $2, $3, $4)
        ''', user_id, key, tariff, end_date)


async def get_expiring_subscriptions(days: int = 3):
    async with pool.acquire() as conn:
        return await conn.fetch('''
            SELECT s.*, u.user_id FROM subscriptions s
            JOIN users u ON u.user_id = s.user_id
            WHERE s.is_active = TRUE
              AND s.end_date IS NOT NULL
              AND s.end_date BETWEEN NOW() + INTERVAL '2 days 23 hours'
                               AND NOW() + INTERVAL '3 days 1 hour'
        ''')


# ── Платежи ───────────────────────────────────────────────────────────────────

async def create_payment(user_id: int, tariff: str, amount: float) -> int:
    async with pool.acquire() as conn:
        row = await conn.fetchrow('''
            INSERT INTO payments (user_id, tariff, amount)
            VALUES ($1, $2, $3)
            RETURNING id
        ''', user_id, tariff, amount)
        return row['id']


async def get_payment(payment_id: int):
    async with pool.acquire() as conn:
        return await conn.fetchrow('SELECT * FROM payments WHERE id = $1', payment_id)


async def get_pending_payments():
    async with pool.acquire() as conn:
        return await conn.fetch('''
            SELECT p.*, u.username, u.first_name
            FROM payments p
            JOIN users u ON u.user_id = p.user_id
            WHERE p.status = 'pending'
            ORDER BY p.created_at
        ''')


async def update_payment_status(payment_id: int, status: str, comment: str = None):
    async with pool.acquire() as conn:
        await conn.execute('''
            UPDATE payments SET status = $1, comment = $2 WHERE id = $3
        ''', status, comment, payment_id)


# ── Промокоды ─────────────────────────────────────────────────────────────────

async def get_promo(code: str):
    async with pool.acquire() as conn:
        return await conn.fetchrow('''
            SELECT * FROM promo_codes
            WHERE code = $1 AND is_active = TRUE AND used_count < max_uses
        ''', code)


async def use_promo(code: str):
    async with pool.acquire() as conn:
        await conn.execute(
            'UPDATE promo_codes SET used_count = used_count + 1 WHERE code = $1', code
        )


async def create_promo(code: str, discount: int, max_uses: int):
    async with pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO promo_codes (code, discount, max_uses)
            VALUES ($1, $2, $3)
            ON CONFLICT (code) DO UPDATE SET discount=$2, max_uses=$3, is_active=TRUE
        ''', code, discount, max_uses)


# ── Статистика ────────────────────────────────────────────────────────────────

async def get_stats():
    async with pool.acquire() as conn:
        total      = await conn.fetchval('SELECT COUNT(*) FROM users')
        active     = await conn.fetchval('''
            SELECT COUNT(*) FROM subscriptions
            WHERE is_active=TRUE AND (end_date IS NULL OR end_date > NOW())
        ''')
        by_tariff  = await conn.fetch('''
            SELECT tariff, COUNT(*) AS cnt FROM subscriptions
            WHERE is_active=TRUE AND (end_date IS NULL OR end_date > NOW())
            GROUP BY tariff
        ''')
        pending    = await conn.fetchval("SELECT COUNT(*) FROM payments WHERE status='pending'")
        revenue    = await conn.fetchval("SELECT COALESCE(SUM(amount),0) FROM payments WHERE status='paid'")
        new_today  = await conn.fetchval(
            "SELECT COUNT(*) FROM users WHERE registered_at > NOW() - INTERVAL '1 day'"
        )
        return {
            'total': total, 'active': active, 'by_tariff': by_tariff,
            'pending': pending, 'revenue': revenue, 'new_today': new_today,
        }
