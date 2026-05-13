"""
Seed inbox placement tester.

Before launching a campaign, send a test email to your seed accounts
(Gmail, Outlook, Yahoo, iCloud, ProtonMail) and check whether it landed
in inbox, spam, or promotions.

Usage (CLI or API):
    result = await seed_tester.run_test(subject, html_body, from_domain)
    # Returns per-provider placement results
"""
from __future__ import annotations

import asyncio
import imaplib
import logging
import smtplib
import time
from dataclasses import dataclass, field
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid
from typing import Optional
import os

from app.core.config import settings

logger = logging.getLogger(__name__)

_SMTP_HOST = os.getenv("SMTP_HOST", "smtp")
_SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))


@dataclass
class SeedResult:
    provider: str
    email: str
    placement: str          # "inbox" | "spam" | "promotions" | "not_found" | "error"
    found: bool = False
    error: Optional[str] = None


@dataclass
class SeedTestReport:
    subject: str
    from_email: str
    results: list[SeedResult] = field(default_factory=list)

    @property
    def inbox_rate(self) -> float:
        if not self.results:
            return 0.0
        inbox = sum(1 for r in self.results if r.placement == "inbox")
        return inbox / len(self.results)

    def summary(self) -> dict:
        return {
            "subject": self.subject,
            "from_email": self.from_email,
            "inbox_rate": f"{self.inbox_rate:.0%}",
            "results": [
                {"provider": r.provider, "placement": r.placement, "error": r.error}
                for r in self.results
            ],
        }


class SeedTester:
    """Send test emails to seed accounts and check inbox placement via IMAP."""

    async def run_test(
        self,
        subject: str,
        html_body: str,
        from_domain: str,
        wait_seconds: int = 60,
    ) -> SeedTestReport:
        """
        Send to all configured seed accounts, wait, then check placement.

        Parameters
        ----------
        subject : str
            Email subject to test.
        html_body : str
            HTML body to test.
        from_domain : str
            Sending domain (email will come from test@{from_domain}).
        wait_seconds : int
            Seconds to wait for delivery before checking inboxes.
        """
        seed_config = self._get_seed_config()
        if not seed_config:
            logger.warning("No seed accounts configured — set WARMUP_SEED_EMAILS or configure via API")
            return SeedTestReport(subject=subject, from_email=f"test@{from_domain}")

        from_email = f"test@{from_domain}"
        report = SeedTestReport(subject=subject, from_email=from_email)

        # Send to all seeds
        for provider, cfg in seed_config.items():
            try:
                self._send_seed(from_email, cfg["email"], subject, html_body)
                logger.info("Seed sent to %s (%s)", cfg["email"], provider)
            except Exception as e:
                logger.error("Failed to send seed to %s: %s", provider, e)
                report.results.append(SeedResult(
                    provider=provider, email=cfg["email"],
                    placement="error", error=str(e),
                ))

        # Wait for delivery
        logger.info("Waiting %ds for seed delivery...", wait_seconds)
        await asyncio.sleep(wait_seconds)

        # Check each inbox
        for provider, cfg in seed_config.items():
            if not cfg.get("imap_host"):
                continue
            result = await self._check_placement(provider, cfg, subject)
            report.results.append(result)

        logger.info("Seed test complete: %s", report.summary())
        return report

    def _send_seed(self, from_email: str, to_email: str, subject: str, html_body: str):
        msg = MIMEMultipart("alternative")
        msg.attach(MIMEText(subject, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))
        msg["From"] = from_email
        msg["To"] = to_email
        msg["Subject"] = subject
        msg["Date"] = formatdate(localtime=False)
        msg["Message-ID"] = make_msgid(domain=from_email.split("@")[1])

        server = smtplib.SMTP(_SMTP_HOST, _SMTP_PORT, timeout=30)
        server.ehlo()
        server.sendmail(from_email, to_email, msg.as_string())
        server.quit()

    async def _check_placement(self, provider: str, cfg: dict, subject: str) -> SeedResult:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._check_placement_sync, provider, cfg, subject
        )

    def _check_placement_sync(self, provider: str, cfg: dict, subject: str) -> SeedResult:
        try:
            server = imaplib.IMAP4_SSL(cfg["imap_host"], cfg.get("imap_port", 993))
            server.login(cfg["email"], cfg["password"])

            # Check inbox
            server.select("INBOX")
            _, data = server.search(None, f'SUBJECT "{subject}"')
            if data[0]:
                server.logout()
                return SeedResult(provider=provider, email=cfg["email"], placement="inbox", found=True)

            # Check spam / junk
            for folder in ["[Gmail]/Spam", "Junk", "Spam", "Junk Email", "[Gmail]/Promotions", "Promotions"]:
                try:
                    server.select(folder)
                    _, data = server.search(None, f'SUBJECT "{subject}"')
                    if data[0]:
                        placement = "spam" if "spam" in folder.lower() or "junk" in folder.lower() else "promotions"
                        server.logout()
                        return SeedResult(provider=provider, email=cfg["email"], placement=placement, found=True)
                except Exception:
                    continue

            server.logout()
            return SeedResult(provider=provider, email=cfg["email"], placement="not_found")

        except Exception as e:
            return SeedResult(provider=provider, email=cfg["email"], placement="error", error=str(e))

    def _get_seed_config(self) -> dict:
        """Load seed account config from environment variables."""
        config = {}
        seed_vars = {
            "gmail":    ("SEED_GMAIL_EMAIL",   "SEED_GMAIL_PASSWORD",   "imap.gmail.com"),
            "outlook":  ("SEED_OUTLOOK_EMAIL", "SEED_OUTLOOK_PASSWORD", "outlook.office365.com"),
            "yahoo":    ("SEED_YAHOO_EMAIL",   "SEED_YAHOO_PASSWORD",   "imap.mail.yahoo.com"),
        }
        for provider, (email_var, pass_var, imap_host) in seed_vars.items():
            email_val = os.getenv(email_var, "")
            pass_val = os.getenv(pass_var, "")
            if email_val and pass_val:
                config[provider] = {
                    "email": email_val,
                    "password": pass_val,
                    "imap_host": imap_host,
                }
        return config


seed_tester = SeedTester()
