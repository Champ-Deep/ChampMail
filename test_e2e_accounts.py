#!/usr/bin/env python3
"""
End-to-end email pipeline test for ChampMail.
Tests both accounts sending to hemang.k@championsmail.com
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timezone

BACKEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

os.environ.setdefault("DEBUG", "false")

import logging
logging.basicConfig(level=logging.WARNING)

from app.services.email_provider import StalwartSMTPProvider, IMAPReplyDetector, EmailMessage

TARGET_EMAIL = "hemang.k@championsmail.com"

ACCOUNTS = [
    {
        "name": "Account 1 — accountsonline.biz",
        "smtp": {
            "host": "mail.accountsonline.biz",
            "port": 465,
            "username": "test@accountsonline.biz",
            "password": "Champ@123456",
            "from_email": "test@accountsonline.biz",
            "from_name": "ChampMail Test (Account 1)",
            "use_tls": False,
            "use_ssl": True,
        },
        "imap": {
            "host": "mail.accountsonline.biz",
            "port": 993,
            "username": "test@accountsonline.biz",
            "password": "Champ@123456",
            "use_ssl": True,
            "mailbox": "INBOX",
        },
    },
    {
        "name": "Account 2 — infobase360.com (TurboSMTP)",
        "smtp": {
            "host": "pro.turbo-smtp.com",
            "port": 25,
            "username": "768b7b5c38904f7381b0",
            "password": "fTcbZNk6Jym0I2OYzHRp",
            "from_email": "charlie.evans@infobase360.com",
            "from_name": "Charlie Evans (Account 2)",
            "use_tls": False,
            "use_ssl": False,
        },
        "imap": {
            "host": "mail.privatemail.com",
            "port": 993,
            "username": "charlie.evans@infobase360.com",
            "password": ",>y<Vq.%?5D6ug>",
            "use_ssl": True,
            "mailbox": "INBOX",
        },
    },
]


def banner(text):
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}")

def ok(text):
    print(f"  ✓ {text}")

def fail(text):
    print(f"  ✗ {text}")

def step(text):
    print(f"  → {text}")


async def test_account(account):
    """Run full E2E test for one account."""
    smtp_cfg = account["smtp"]
    imap_cfg = account["imap"]
    results = {"account": account["name"]}

    # 1. SMTP Verify
    step("Verifying SMTP connection...")
    provider = StalwartSMTPProvider(
        host=smtp_cfg["host"],
        port=smtp_cfg["port"],
        username=smtp_cfg["username"],
        password=smtp_cfg["password"],
        use_tls=smtp_cfg["use_tls"],
        use_ssl=smtp_cfg.get("use_ssl", False),
        from_email=smtp_cfg["from_email"],
        from_name=smtp_cfg["from_name"],
    )
    try:
        smtp_ok = await provider.verify_connection()
        results["smtp_verified"] = smtp_ok
        if smtp_ok:
            ok(f"SMTP verified: {smtp_cfg['host']}:{smtp_cfg['port']}")
        else:
            fail(f"SMTP verification failed: {smtp_cfg['host']}:{smtp_cfg['port']}")
    except Exception as e:
        results["smtp_verified"] = False
        results["smtp_error"] = str(e)
        fail(f"SMTP error: {e}")

    # 2. Send Email
    step(f"Sending email to {TARGET_EMAIL}...")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    msg = EmailMessage(
        to=TARGET_EMAIL,
        subject=f"ChampMail E2E Test — {account['name']} — {now}",
        html_body=f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <h2 style="color: #6366f1;">ChampMail End-to-End Test</h2>
            <p>This is an automated test from the <b>ChampMail CLI pipeline</b>.</p>
            <table style="border-collapse: collapse; width: 100%;">
                <tr><td style="padding: 8px; border: 1px solid #ddd; font-weight: bold;">Account</td>
                    <td style="padding: 8px; border: 1px solid #ddd;">{account['name']}</td></tr>
                <tr><td style="padding: 8px; border: 1px solid #ddd; font-weight: bold;">From</td>
                    <td style="padding: 8px; border: 1px solid #ddd;">{smtp_cfg['from_name']} &lt;{smtp_cfg['from_email']}&gt;</td></tr>
                <tr><td style="padding: 8px; border: 1px solid #ddd; font-weight: bold;">To</td>
                    <td style="padding: 8px; border: 1px solid #ddd;">{TARGET_EMAIL}</td></tr>
                <tr><td style="padding: 8px; border: 1px solid #ddd; font-weight: bold;">SMTP</td>
                    <td style="padding: 8px; border: 1px solid #ddd;">{smtp_cfg['host']}:{smtp_cfg['port']}</td></tr>
                <tr><td style="padding: 8px; border: 1px solid #ddd; font-weight: bold;">Sent At</td>
                    <td style="padding: 8px; border: 1px solid #ddd;">{now}</td></tr>
            </table>
            <p style="color: #888; margin-top: 20px; font-size: 12px;">
                Sent via ChampMail CLI — E2E Pipeline Test
            </p>
        </div>
        """,
        text_body=f"ChampMail E2E Test | Account: {account['name']} | From: {smtp_cfg['from_email']} | To: {TARGET_EMAIL} | Sent: {now}",
    )
    try:
        result = await provider.send_email(msg)
        results["email_sent"] = result.success
        results["message_id"] = result.message_id
        results["send_error"] = result.error
        if result.success:
            ok(f"Email sent! Message-ID: {result.message_id}")
        else:
            fail(f"Send failed: {result.error}")
    except Exception as e:
        results["email_sent"] = False
        results["send_error"] = str(e)
        fail(f"Send exception: {e}")

    # 3. IMAP Check
    step("Checking IMAP inbox...")
    detector = IMAPReplyDetector(
        host=imap_cfg["host"],
        port=imap_cfg["port"],
        username=imap_cfg["username"],
        password=imap_cfg["password"],
        use_ssl=imap_cfg["use_ssl"],
        mailbox=imap_cfg["mailbox"],
    )
    try:
        imap_ok = await detector.verify_connection()
        results["imap_connected"] = imap_ok
        if imap_ok:
            ok(f"IMAP connected: {imap_cfg['host']}:{imap_cfg['port']}")
            msgs = await detector.check_new_messages()
            results["inbox_messages"] = len(msgs) if msgs else 0
            ok(f"Inbox: {results['inbox_messages']} messages")
            for m in (msgs or [])[:3]:
                print(f"      {m.from_email[:30]:30s}  {m.subject[:40]}")
        else:
            fail("IMAP connection failed")
    except Exception as e:
        results["imap_connected"] = False
        results["imap_error"] = str(e)
        fail(f"IMAP error: {e}")

    return results


async def main():
    banner("ChampMail End-to-End Pipeline Test")
    print(f"  Target: {TARGET_EMAIL}")
    print(f"  Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")

    all_results = []
    for i, account in enumerate(ACCOUNTS, 1):
        banner(f"[{i}/{len(ACCOUNTS)}] {account['name']}")
        result = await test_account(account)
        all_results.append(result)

    banner("RESULTS SUMMARY")
    for r in all_results:
        smtp = "PASS" if r.get("smtp_verified") else "FAIL"
        sent = "PASS" if r.get("email_sent") else "FAIL"
        imap = "PASS" if r.get("imap_connected") else "FAIL"
        print(f"  {r['account']}")
        print(f"    SMTP: {smtp}  |  Send: {sent}  |  IMAP: {imap}")
        if r.get("send_error"):
            print(f"    Error: {r['send_error'][:80]}")
        if r.get("message_id"):
            print(f"    Msg-ID: {r['message_id']}")
        print()

    results_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "e2e_test_results.json")
    with open(results_file, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"  Results saved to: {results_file}")


if __name__ == "__main__":
    asyncio.run(main())
