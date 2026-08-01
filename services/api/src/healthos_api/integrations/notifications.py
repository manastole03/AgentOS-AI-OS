import asyncio
import smtplib
from email.message import EmailMessage

import httpx

from healthos_api.config import Settings


class NotificationDispatcher:
    def __init__(self, settings: Settings, client: httpx.AsyncClient) -> None:
        self.settings, self.client = settings, client

    async def dispatch(self, *, channel: str, email: str, title: str, body: str) -> bool:
        if channel == "in_app":
            return True
        if channel == "webhook":
            if not self.settings.notification_webhook_url:
                return False
            response = await self.client.post(
                self.settings.notification_webhook_url,
                json={"title": title, "body": body},
                timeout=15,
            )
            response.raise_for_status()
            return True
        if channel == "email":
            if not self.settings.smtp_host:
                return False
            await asyncio.to_thread(self._email, email, title, body)
            return True
        return False

    def _email(self, email: str, title: str, body: str) -> None:
        message = EmailMessage()
        message["From"] = self.settings.smtp_from_email
        message["To"] = email
        message["Subject"] = title
        message.set_content(body)
        with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port, timeout=10) as smtp:
            if self.settings.smtp_use_tls:
                smtp.starttls()
            if self.settings.smtp_username:
                smtp.login(
                    self.settings.smtp_username,
                    self.settings.smtp_password.get_secret_value(),
                )
            smtp.send_message(message)
