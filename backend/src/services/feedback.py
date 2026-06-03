import logging

import httpx

from src.config import Settings

logger = logging.getLogger(__name__)


class FeedbackService:
    def __init__(self, settings: Settings) -> None:
        self._token = settings.telegram_bot_token
        self._chat_id = settings.telegram_chat_id
        self._version = settings.app_version
        self._timeout = settings.telegram_timeout

    async def report(self, message: str, room_id: str | None, user_id: str | None) -> None:
        text = (
            f"🐞 Сообщение о баге/идее\n"
            f"Версия: {self._version}\n"
            f"Комната: {room_id or '—'}\n"
            f"Пользователь: {user_id or '—'}\n\n"
            f"{message}"
        )

        if not self._token or not self._chat_id:
            logger.info("FEEDBACK (telegram not configured): %s", text)
            return

        url = f"https://api.telegram.org/bot{self._token}/sendMessage"
        transport = httpx.AsyncHTTPTransport(local_address="0.0.0.0", retries=1)
        try:
            async with httpx.AsyncClient(timeout=self._timeout, transport=transport) as client:
                resp = await client.post(url, json={"chat_id": self._chat_id, "text": text})
                if resp.status_code != 200:
                    logger.warning("Telegram feedback failed: %s %s", resp.status_code, resp.text)
                else:
                    logger.info("Telegram feedback delivered")
        except Exception as e:
            logger.warning("Telegram feedback error: %s: %r", type(e).__name__, str(e))
