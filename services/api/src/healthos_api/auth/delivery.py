import asyncio
import smtplib
from email.message import EmailMessage

import httpx

from healthos_api.config import Settings
from healthos_api.db.models import OtpPurpose


class OtpDeliveryError(RuntimeError):
    pass


async def deliver_otp(*, email: str, code: str, purpose: OtpPurpose, settings: Settings) -> None:
    if not settings.smtp_host:
        return
    await asyncio.to_thread(_send_smtp, email, code, purpose, settings)


async def deliver_mobile_otp(*, phone: str, code: str, settings: Settings) -> None:
    """Deliver mobile OTP through a provider-neutral authenticated webhook.

    Local development deliberately performs no external call when the webhook is blank.
    """
    if not settings.sms_webhook_url:
        return
    headers = {"Content-Type": "application/json"}
    token = settings.sms_webhook_token.get_secret_value()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                settings.sms_webhook_url,
                headers=headers,
                json={
                    "to": phone,
                    "template": "healthos_verification",
                    "code": code,
                    "expires_in_minutes": settings.otp_expire_minutes,
                },
            )
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise OtpDeliveryError("Unable to deliver mobile verification code") from exc


def _send_smtp(email: str, code: str, purpose: OtpPurpose, settings: Settings) -> None:
    subject = (
        "Verify your HealthOS account"
        if purpose == OtpPurpose.EMAIL_VERIFICATION
        else (
            "Verify your HealthOS mobile number"
            if purpose == OtpPurpose.MOBILE_VERIFICATION
            else "Reset your HealthOS password"
        )
    )
    message = EmailMessage()
    message["From"] = settings.smtp_from_email
    message["To"] = email
    message["Subject"] = subject
    message.set_content(
        f"Your HealthOS verification code is {code}. "
        f"It expires in {settings.otp_expire_minutes} minutes. "
        "If you did not request this code, you can ignore this message."
    )
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
            if settings.smtp_use_tls:
                smtp.starttls()
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password.get_secret_value())
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        raise OtpDeliveryError("Unable to deliver verification code") from exc
