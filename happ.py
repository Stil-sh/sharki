import secrets
import logging
import aiohttp
from aiohttp import web
from datetime import timezone

import config
import db

logger = logging.getLogger(__name__)


def generate_token() -> str:
    """Уникальный токен подписки — используется в URL."""
    return secrets.token_urlsafe(24)


def make_sub_url(token: str) -> str:
    """
    Формирует публичный URL подписки для Happ.
    Например: https://worker-production-f472.up.railway.app/sub/AbCd1234
    """
    return f'{config.PUBLIC_URL.rstrip("/")}/sub/{token}'


async def fetch_servers() -> list[str]:
    """Скачивает servers.txt с GitHub, возвращает список vless-строк."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                config.SERVERS_URL,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                resp.raise_for_status()
                text = await resp.text()
        lines = [l.strip() for l in text.splitlines() if l.strip().startswith('vless://')]
        logger.info('Загружено %d серверов', len(lines))
        return lines
    except Exception as e:
        logger.error('Ошибка загрузки серверов: %s', e)
        return []


async def handle_subscription(request: web.Request) -> web.Response:
    """
    GET /sub/<token>

    Happ делает запрос на этот эндпоинт при добавлении/обновлении подписки.
    Возвращаем список серверов и заголовки:
      - subscription-userinfo: expire=<unix_timestamp>
      - profile-title: SHARKIVPN
      - content-disposition: attachment; filename="sharkivpn.txt"

    Happ читает заголовок expire и отображает дату окончания подписки
    прямо в интерфейсе приложения рядом с названием подписки.
    """
    token = request.match_info.get('token', '')
    if not token:
        return web.Response(status=400, text='missing token')

    # Ищем подписку по токену
    sub = await db.get_subscription_by_token(token)
    if not sub:
        # Подписка не найдена или истекла — возвращаем 404
        # Happ покажет ошибку обновления подписки
        return web.Response(status=404, text='subscription not found or expired')

    # Скачиваем серверы с GitHub
    servers = await fetch_servers()
    if not servers:
        return web.Response(status=503, text='servers unavailable')

    body = '\n'.join(servers)

    # Формируем заголовки
    headers = {
        'Content-Type':        'text/plain; charset=utf-8',
        'profile-title':       'SHARKIVPN',
        'profile-update-interval': '24',  # Happ обновляет каждые 24 часа
    }

    end_date = sub['end_date']
    if end_date is not None:
        # Переводим в UTC Unix timestamp
        expire_ts = int(end_date.replace(tzinfo=timezone.utc).timestamp()
                        if end_date.tzinfo is None
                        else end_date.astimezone(timezone.utc).timestamp())
        # Happ читает этот заголовок и показывает дату окончания в UI
        headers['subscription-userinfo'] = f'expire={expire_ts}'
    else:
        # Для тарифа "навсегда" ставим дату через 100 лет
        headers['subscription-userinfo'] = 'expire=4102444800'

    tariff_name = config.TARIFFS.get(sub['tariff'], {}).get('name', sub['tariff'])
    headers['content-disposition'] = f'attachment; filename="sharkivpn_{tariff_name}.txt"'

    return web.Response(text=body, headers=headers)
