"""
Live API smoke test for the InboxKit client code.

Run:
  cd ~/ChampSuite/ChampMail
  INBOXKIT_API_KEY=<key> backend/.venv/bin/python test_inboxkit_live.py

This exercises the ACTUAL InboxKitClient / InboxKitProvider code paths
against the real api.inboxkit.com. Read-only calls only — no purchases.
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))


async def main():
    from app.services.inboxkit.client import InboxKitClient, InboxKitAPIError
    from app.services.inboxkit.provider import InboxKitProvider

    client = InboxKitClient()  # reads INBOXKIT_API_KEY / INBOXKIT_WORKSPACE_ID from env
    results: list[tuple[str, str]] = []

    def record(name, ok, detail=""):
        mark = "PASS" if ok else "FAIL"
        results.append((mark, f"{name}: {detail}"))
        print(f"  [{mark}] {name}: {detail}")

    # 1. Liveness — workspaces/list (no workspace header needed).
    try:
        resp = await client.list_workspaces()
        workspaces = resp.get("workspaces") or []
        record("list_workspaces", True,
               f"{len(workspaces)} workspace(s): "
               + ", ".join(f"{w.get('name')} (uid={w.get('uid')})" for w in workspaces))
        if workspaces:
            ws = workspaces[0]
            record("workspace_uid_present", bool(ws.get("uid")), ws.get("uid", "MISSING"))
            record("workspace_webhook_url", True,
                   f"current='{ws.get('webhook_url', '')}' "
                   + "(empty = needs to be set)" if not ws.get("webhook_url") else ws.get("webhook_url"))
    except InboxKitAPIError as e:
        record("list_workspaces", False, str(e))

    # 2. Domain search — free, read-only. Verifies the endpoint + rate-limit
    #    handling on the search path (50/min limit).
    try:
        resp = await client.search_domains(keyword="champions", tlds=["com", "net", "org"], num=5)
        domains = resp.get("domains") or []
        record("search_domains", True,
               f"{len(domains)} result(s); sample="
               + (f"{domains[0].get('name')} avail={domains[0].get('available')} price=${domains[0].get('price')}"
                  if domains else "none"))
    except InboxKitAPIError as e:
        record("search_domains", False, str(e))

    # 3. Mailbox status with no uids — verified live: 400s "uids is required".
    #    The unfiltered list is POST /mailboxes/list instead (test 4).
    try:
        resp = await client.list_mailboxes()
        mailboxes = resp.get("mailboxes") or []
        record("list_mailboxes", True,
               f"{len(mailboxes)} mailbox(es) in workspace (total={resp.get('total')})")
    except InboxKitAPIError as e:
        record("list_mailboxes", False, str(e))

    # 3b. mailbox_status error path — confirmed raises cleanly with no uids.
    try:
        await client.mailbox_status()
        record("mailbox_status_requires_uids", False, "unexpectedly succeeded")
    except ValueError:
        record("mailbox_status_requires_uids", True, "raises ValueError as designed")

    # 4. Provider-level list_mailboxes (goes through the IAL, reshapes).
    try:
        provider = InboxKitProvider(client)
        mbs = await provider.list_mailboxes()
        record("provider.list_mailboxes", True,
               f"{len(mbs)} mailbox(es), reshaped ok")
    except Exception as e:
        record("provider.list_mailboxes", False, str(e))

    # 5. show_credentials on a non-existent uid — should 4xx cleanly, proving
    #    the error path raises InboxKitAPIError rather than hanging/crashing.
    try:
        await client.show_credentials(uid="nonexistent_uid_12345")
        record("show_credentials_error_path", False,
               "unexpectedly succeeded for a fake uid")
    except InboxKitAPIError as e:
        record("show_credentials_error_path", True,
               f"clean HTTP {e.status} for fake uid (expected)")
    except Exception as e:
        record("show_credentials_error_path", False, f"wrong exception type: {type(e).__name__}: {e}")

    await client.close()

    print()
    passed = sum(1 for m, _ in results if m == "PASS")
    failed = sum(1 for m, _ in results if m == "FAIL")
    print(f"{passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
