from __future__ import annotations

import logging

import pytest

from app.services.email import (
    EmailMessage,
    EmailSender,
    LoggingEmailSender,
    get_email_sender,
)


def test_logging_sender_logs_the_email_and_succeeds(caplog: pytest.LogCaptureFixture) -> None:
    sender = LoggingEmailSender()
    message = EmailMessage(
        to=["bookie@example.com"],
        subject="Set your password",
        body="Open https://app.local/set-password?token=abc123 to continue.",
    )

    with caplog.at_level(logging.INFO):
        ok = sender.send(message)

    assert ok is True
    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert "bookie@example.com" in logged
    assert "token=abc123" in logged


def test_send_is_non_blocking_when_delivery_fails(caplog: pytest.LogCaptureFixture) -> None:
    class BrokenSender(EmailSender):
        def _deliver(self, message: EmailMessage) -> None:
            raise RuntimeError("smtp down")

    ok = BrokenSender().send(
        EmailMessage(to=["a@b.com"], subject="x", body="y")
    )

    assert ok is False  # failure is swallowed and reported, never raised


def test_factory_returns_logging_sender_by_default() -> None:
    assert isinstance(get_email_sender(), LoggingEmailSender)
