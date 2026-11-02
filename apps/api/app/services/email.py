"""Outbound email. The console backend logs messages (development); smtp sends them."""

import logging
import smtplib
from email.message import EmailMessage

from app.core.config import settings

log = logging.getLogger("deploymind.email")


def send_email(to: list[str], subject: str, body: str) -> None:
    if settings.email_backend == "smtp":
        msg = EmailMessage()
        msg["From"] = settings.email_from
        msg["To"] = ", ".join(to)
        msg["Subject"] = subject
        msg.set_content(body)
        try:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
                if settings.smtp_user:
                    smtp.starttls()
                    smtp.login(settings.smtp_user, settings.smtp_password)
                smtp.send_message(msg)
        except OSError:
            # Notification is persisted regardless; surface the delivery failure in logs.
            log.exception("email_send_failed", extra={"to": to, "subject": subject})
        return
    log.info("email_console", extra={"to": to, "subject": subject, "body": body[:500]})
