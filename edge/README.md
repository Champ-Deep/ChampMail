# champmail-edge

Cloudflare Worker for `track.<domain>`: open pixel, click redirect, one-click unsubscribe. It holds no state.
It verifies the HMAC token ChampMail signed (`backend/app/services/tracking.py`), then posts the event to
`POST /api/v1/events/internal` on ChampMail with `X-Edge-Secret`. ChampMail dedupes and decides.

| Route | Good token | Bad token |
|---|---|---|
| GET /o/{token}.gif | 200 gif, `opened` posted in the background | 404, nothing posted |
| GET /c/{token} | 302 to the signed URL, `clicked` posted in the background | 400, nothing posted |
| GET /u/{token} | confirmation page with a POST button, nothing posted | 404 |
| POST /u/{token} with `List-Unsubscribe=One-Click` | `unsubscribed` posted, 200 plain text; 404 if ChampMail refuses, 502 if it is down | 404 |

Secrets: `wrangler secret put TRACKING_SECRET` and `wrangler secret put EDGE_SHARED_SECRET` (same values as ChampMail's).
`CHAMPMAIL_URL` is a var in `wrangler.toml`. Routes are not in `wrangler.toml`: Cloudflare route patterns are per zone and
reject an infix wildcard, so ChampMail creates `track.<domain>/*` in each zone when it provisions the domain.

```
pnpm install
pnpm typecheck
pnpm test        # vitest in the Workers runtime
```

`test/fixtures/tokens.json` is written by the Python signer (`python -m tests.test_edge_contract` in `backend/`) and read by both
test suites, so a change to the signature scheme on either side fails a test.
