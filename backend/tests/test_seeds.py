"""POST/GET /api/v1/seeds: the registry that bounds which addresses a canary may reach."""
import pytest

from tests.test_send import run


def test_seed_register_list_and_duplicate(client):
    async def go(Session):
        async def scenario(c):
            r = await c.post("/api/v1/seeds", json={"address": "Seed.One@Gmail.com ", "provider": "gmail"})
            assert r.status_code == 201, r.text
            assert r.json()["address"] == "seed.one@gmail.com" and r.json()["provider"] == "gmail"
            assert (await c.post("/api/v1/seeds", json={"address": "o@outlook.com", "provider": "outlook"})).status_code == 201
            listed = (await c.get("/api/v1/seeds")).json()
            assert [(s["address"], s["provider"]) for s in listed] == [("o@outlook.com", "outlook"), ("seed.one@gmail.com", "gmail")]
            dup = await c.post("/api/v1/seeds", json={"address": "SEED.one@gmail.com", "provider": "outlook"})
            assert dup.status_code == 409
            assert len((await c.get("/api/v1/seeds")).json()) == 2
        await client(Session, scenario)
    run(go)


@pytest.mark.parametrize("body", [
    {"address": "a@gmail.com", "provider": "yahoo"},
    {"address": "not-an-address", "provider": "gmail"},
    {"address": "a@gmail.com, b@evil.com", "provider": "gmail"},
    {"address": "Name <a@gmail.com>", "provider": "gmail"},
    {"address": "a@gmail.com\nBcc: b@evil.com", "provider": "gmail"},
])
def test_seed_rejects_bad_input(client, body):
    async def go(Session):
        async def scenario(c):
            assert (await c.post("/api/v1/seeds", json=body)).status_code == 422
            assert (await c.get("/api/v1/seeds")).json() == []
        await client(Session, scenario)
    run(go)


def test_seeds_require_api_key(client):
    async def go(Session):
        async def scenario(c):
            c.headers.pop("X-API-Key")
            assert (await c.get("/api/v1/seeds")).status_code == 401
            assert (await c.post("/api/v1/seeds", json={"address": "a@gmail.com", "provider": "gmail"})).status_code == 401
        await client(Session, scenario)
    run(go)
