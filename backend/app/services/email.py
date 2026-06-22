"""Transactional email behind a single provider-agnostic interface.

v1 (local, no cloud) ships the ``LoggingEmailSender`` as the active provider: it
logs the would-be email (including any action link) instead of sending. A real
provider (SMTP/Resend/SES) can be added as another ``EmailSender`` subclass and
selected via ``settings.email_provider`` with NO change to callers.

Sending is non-blocking to the caller: ``send`` never raises; delivery failures
are logged and reported via a ``False`` return value.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.config import get_settings

logger = logging.getLogger("app.email")


@dataclass
class EmailMessage:
    to: list[str]
    subject: str
    body: str


class EmailSender(ABC):
    @abstractmethod
    def _deliver(self, message: EmailMessage) -> None:
        """Provider-specific delivery. May raise; ``send`` isolates the caller."""

    def send(self, message: EmailMessage) -> bool:
        try:
            self._deliver(message)
            return True
        except Exception:  # noqa: BLE001 - delivery must never break the caller
            logger.exception("Email delivery failed to=%s subject=%s", message.to, message.subject)
            return False


class LoggingEmailSender(EmailSender):
    """Default v1 provider: logs the email instead of sending it."""

    def _deliver(self, message: EmailMessage) -> None:
        logger.info(
            "EMAIL (stub) to=%s subject=%s body=%s",
            ", ".join(message.to),
            message.subject,
            message.body,
        )


def get_email_sender() -> EmailSender:
    provider = get_settings().email_provider.lower()
    # Future providers register here, e.g. "smtp" -> SmtpEmailSender().
    if provider == "log":
        return LoggingEmailSender()
    logger.warning("Unknown email_provider=%r; falling back to logging stub", provider)
    return LoggingEmailSender()
