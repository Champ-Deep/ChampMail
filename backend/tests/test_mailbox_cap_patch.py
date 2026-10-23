"""PATCH /api/v1/mailboxes/{id}: cap alone leaves status untouched; cap + status still works."""
import pytest

from tests.test_send import run, seed


def test_cap_only_patch_changes_cap_not_status(client):
    async def go(Session):
        _, (mb,) = await seed(Session, limit=30)

        async def scenario(c):
            r = await c.patch(f"/api/v1/mailboxes/{mb}", json={"status": "paused", "reason": "hold"})
            assert r.status_code == 200
            r = await c.patch(f"/api/v1/mailboxes/{mb}", json={"cap": 5})
            assert r.status_code == 200, r.text
            assert (r.json()["cap"], r.json()["status"], r.json()["status_reason"]) == (5, "paused", "hold")
        await client(Session, scenario)
    run(go)


def test_cap_and_status_together(client):
    async def go(Session):
        _, (mb,) = await seed(Session, limit=30)

        async def scenario(c):
            r = await c.patch(f"/api/v1/mailboxes/{mb}", json={"cap": 12, "status": "paused", "reason": "ramp hold"})
            assert r.status_code == 200, r.text
            assert (r.json()["cap"], r.json()["status"], r.json()["status_reason"]) == (12, "paused", "ramp hold")
        await client(Session, scenario)
    run(go)


@pytest.mark.parametrize("body", [{}, {"reason": "x"}, {"cap": 0}, {"cap": 201}, {"cap": "ten"}, {"cap": True},
                                  {"cap": 5, "status": "paused"}])
def test_bad_patch_is_422_and_changes_nothing(client, body):
    async def go(Session):
        _, (mb,) = await seed(Session, limit=30)

        async def scenario(c):
            assert (await c.patch(f"/api/v1/mailboxes/{mb}", json=body)).status_code == 422
            box = (await c.get("/api/v1/mailboxes")).json()[0]
            assert (box["cap"], box["status"]) == (30, "active")
        await client(Session, scenario)
    run(go)


def test_cap_bounds_accepted_and_retired_stays_terminal(client):
    async def go(Session):
        _, (mb,) = await seed(Session, limit=30)

        async def scenario(c):
            assert (await c.patch(f"/api/v1/mailboxes/{mb}", json={"cap": 1})).json()["cap"] == 1
            assert (await c.patch(f"/api/v1/mailboxes/{mb}", json={"cap": 200})).json()["cap"] == 200
            assert (await c.patch(f"/api/v1/mailboxes/{mb}", json={"status": "retired", "reason": "dead"})).status_code == 200
            assert (await c.patch(f"/api/v1/mailboxes/{mb}", json={"cap": 10, "status": "active"})).status_code == 409
            assert (await c.patch(f"/api/v1/mailboxes/{mb}", json={"cap": 404})).status_code == 422
        await client(Session, scenario)
    run(go)
