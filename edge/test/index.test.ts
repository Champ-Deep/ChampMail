import { afterEach, beforeEach, describe, expect, it, vi, type MockInstance } from "vitest";
import app from "../src/index";
import fixture from "./fixtures/tokens.json";

// edge/test/fixtures/tokens.json is written by the Python signer (backend/tests/test_edge_contract.py),
// so every token below is one ChampMail's send path would put in a message.
const { tokens, message_id, click_url, secret } = fixture;
const env = { TRACKING_SECRET: secret, EDGE_SHARED_SECRET: "edge-secret", CHAMPMAIL_URL: "https://champmail.test" };
const HOST = "track.acme-mail.com";

let upstream: MockInstance<typeof fetch>;
beforeEach(() => {
  upstream = vi.spyOn(globalThis, "fetch").mockImplementation(async () => new Response('{"status":"queued"}', { status: 200 }));
});
afterEach(() => vi.restoreAllMocks());

async function call(path: string, init?: RequestInit) {
  const pending: Promise<unknown>[] = [];
  const ctx = { waitUntil: (p: Promise<unknown>) => void pending.push(p), passThroughOnException() {} } as unknown as ExecutionContext;
  const res = await app.fetch(new Request(`https://${HOST}${path}`, init), env, ctx);
  await Promise.all(pending); // background event posts finish before the assertions
  return res;
}

function events() {
  return upstream.mock.calls.map(([url, init]) => ({
    url: String(url),
    secret: new Headers((init as RequestInit).headers).get("x-edge-secret"),
    body: JSON.parse(String((init as RequestInit).body)),
  }));
}

const tamper = (t: string) => t.slice(0, -2) + (t.endsWith("AA") ? "BB" : "AA");
const forgeBody = (t: string, patch: Record<string, unknown>) => {
  const [body, mac] = t.split(".");
  const json = JSON.parse(atob(body.replace(/-/g, "+").replace(/_/g, "/")));
  return `${btoa(JSON.stringify({ ...json, ...patch })).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "")}.${mac}`;
};

describe("a token signed by the Python send path", () => {
  it("opens: /o returns a 1x1 gif and posts exactly one opened event", async () => {
    const res = await call(`/o/${tokens.o}.gif`);
    expect(res.status).toBe(200);
    expect(res.headers.get("content-type")).toBe("image/gif");
    expect(res.headers.get("cache-control")).toBe("no-store");
    expect(new Uint8Array(await res.arrayBuffer()).length).toBe(43);
    expect(events()).toEqual([
      { url: "https://champmail.test/api/v1/events/internal", secret: "edge-secret",
        body: { event_type: "opened", token: tokens.o, host: HOST, message_id } },
    ]);
  });

  it("clicks: /c redirects to the signed destination and posts exactly one clicked event", async () => {
    const res = await call(`/c/${tokens.c}`);
    expect(res.status).toBe(302);
    expect(res.headers.get("location")).toBe(new URL(click_url).href); // non-ASCII is percent-encoded, as Python's redirect does
    expect(events().map((e) => [e.body.event_type, e.body.message_id, e.body.host])).toEqual([["clicked", message_id, HOST]]);
  });

  it("one-click unsubscribe: POST /u with List-Unsubscribe=One-Click forwards and answers 200 plain text", async () => {
    const res = await call(`/u/${tokens.u}`, {
      method: "POST", headers: { "content-type": "application/x-www-form-urlencoded" }, body: "List-Unsubscribe=One-Click",
    });
    expect(res.status).toBe(200);
    expect(res.headers.get("content-type")).toContain("text/plain");
    expect(events().map((e) => [e.body.event_type, e.body.token, e.body.message_id])).toEqual([["unsubscribed", tokens.u, message_id]]);
  });

  it("GET /u shows a one-line confirmation whose button POSTs the one-click body", async () => {
    const res = await call(`/u/${tokens.u}`);
    const html = await res.text();
    expect(res.status).toBe(200);
    expect(res.headers.get("content-type")).toContain("text/html");
    expect(html).toContain('method="post"');
    expect(html).toContain('name="List-Unsubscribe" value="One-Click"');
    expect(events()).toEqual([]); // viewing the page unsubscribes nobody
  });
});

describe("anything else emits nothing", () => {
  it("/o: forged mac, forged payload, wrong kind, garbage all 404", async () => {
    for (const t of [tamper(tokens.o), forgeBody(tokens.o, { m: "other@x" }), tokens.c, tokens.u, "garbage", ""]) {
      expect((await call(`/o/${t}.gif`)).status).toBe(404);
    }
    expect(events()).toEqual([]);
  });

  it("/c: forged mac, swapped destination, wrong kind, garbage all 400", async () => {
    for (const t of [tamper(tokens.c), forgeBody(tokens.c, { u: "https://evil.example/" }), tokens.o, tokens.u, "garbage"]) {
      const res = await call(`/c/${t}`);
      expect(res.status).toBe(400);
      expect(res.headers.get("location")).toBeNull();
    }
    expect(events()).toEqual([]);
  });

  it("/u: bad token 404 on GET and POST; POST without the one-click body 400", async () => {
    const post = (t: string, body: string) => call(`/u/${t}`, { method: "POST", headers: { "content-type": "application/x-www-form-urlencoded" }, body });
    expect((await call(`/u/${tamper(tokens.u)}`)).status).toBe(404);
    expect((await post(tamper(tokens.u), "List-Unsubscribe=One-Click")).status).toBe(404);
    expect((await post(tokens.o, "List-Unsubscribe=One-Click")).status).toBe(404);
    expect((await post(tokens.u, "")).status).toBe(400);
    expect((await post(tokens.u, "List-Unsubscribe=Nope")).status).toBe(400);
    expect(events()).toEqual([]);
  });

  it("a wrong signing secret rejects every genuine token", async () => {
    const pending: Promise<unknown>[] = [];
    const ctx = { waitUntil: (p: Promise<unknown>) => void pending.push(p), passThroughOnException() {} } as unknown as ExecutionContext;
    const res = await app.fetch(new Request(`https://${HOST}/o/${tokens.o}.gif`), { ...env, TRACKING_SECRET: "rotated" }, ctx);
    expect(res.status).toBe(404);
    expect(events()).toEqual([]);
  });

  it("unknown routes are 404", async () => {
    expect((await call("/")).status).toBe(404);
    expect((await call("/x/anything")).status).toBe(404);
  });
});

describe("ChampMail unreachable or refusing", () => {
  it("a pixel or click still answers the recipient when the event post fails", async () => {
    upstream.mockImplementation(async () => { throw new Error("connection refused"); });
    expect((await call(`/o/${tokens.o}.gif`)).status).toBe(200);
    expect((await call(`/c/${tokens.c}`)).status).toBe(302);
  });

  it("one-click POST relays ChampMail's refusal: 404 stays 404, an outage is 502", async () => {
    const post = () => call(`/u/${tokens.u}`, { method: "POST", headers: { "content-type": "application/x-www-form-urlencoded" }, body: "List-Unsubscribe=One-Click" });
    upstream.mockImplementation(async () => new Response("{}", { status: 404 }));
    expect((await post()).status).toBe(404);
    upstream.mockImplementation(async () => new Response("{}", { status: 503 }));
    expect((await post()).status).toBe(502);
    upstream.mockImplementation(async () => { throw new Error("down"); });
    expect((await post()).status).toBe(502);
  });

  it("an unconfigured Worker (no secrets) refuses instead of guessing", async () => {
    const res = await app.fetch(new Request(`https://${HOST}/o/${tokens.o}.gif`), {} as typeof env, { waitUntil() {}, passThroughOnException() {} } as unknown as ExecutionContext);
    expect(res.status).toBe(404);
  });
});
