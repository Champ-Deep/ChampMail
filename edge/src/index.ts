import { Hono } from "hono";
import { verify } from "./token";

type Bindings = { TRACKING_SECRET: string; INTERNAL_EVENTS_SECRET: string; CHAMPMAIL_BASE_URL: string };
type EventType = "opened" | "clicked" | "unsubscribed";

const app = new Hono<{ Bindings: Bindings }>();

// 1x1 transparent GIF, the same bytes as ChampMail's own /o route.
const PIXEL = Uint8Array.from("47494638396101000100800000000000ffffff21f90401000000002c00000000010001000002024401003b".match(/../g)!, (h) => parseInt(h, 16));
const NO_STORE = { "Cache-Control": "no-store" };

/** Hands the verified event to ChampMail, which decides (dedupe, suppression). Returns ChampMail's HTTP status, 0 if unreachable. */
async function forward(env: Bindings, event_type: EventType, token: string, host: string, message_id: string): Promise<number> {
  try {
    const res = await fetch(`${env.CHAMPMAIL_BASE_URL.replace(/\/+$/, "")}/api/v1/events/internal`, {
      method: "POST",
      headers: { "content-type": "application/json", "X-Edge-Secret": env.INTERNAL_EVENTS_SECRET },
      body: JSON.stringify({ event_type, token, host, message_id }),
    });
    return res.status;
  } catch {
    return 0;
  }
}

const hostOf = (url: string) => new URL(url).hostname;

app.get("/o/:name", async (c) => {
  const token = c.req.param("name").replace(/\.gif$/, "");
  const claim = await verify(c.env.TRACKING_SECRET, token, "o");
  if (!claim) return c.body(null, 404);
  // Background: the recipient's mail client never waits on ChampMail. A lost open is acceptable noise.
  c.executionCtx.waitUntil(forward(c.env, "opened", token, hostOf(c.req.url), claim.message_id));
  return c.body(PIXEL, 200, { "Content-Type": "image/gif", ...NO_STORE });
});

app.get("/c/:token", async (c) => {
  const token = c.req.param("token");
  const claim = await verify(c.env.TRACKING_SECRET, token, "c");
  if (!claim?.url) return c.text("bad link", 400);
  let location: string;
  try {
    location = new URL(claim.url).href; // percent-encodes what a header cannot carry
  } catch {
    return c.text("bad link", 400);
  }
  c.executionCtx.waitUntil(forward(c.env, "clicked", token, hostOf(c.req.url), claim.message_id));
  return c.redirect(location, 302);
});

app.get("/u/:token", async (c) => {
  if (!(await verify(c.env.TRACKING_SECRET, c.req.param("token"), "u"))) return c.text("not found", 404);
  return c.html(
    `<!doctype html><meta charset="utf-8"><title>Unsubscribe</title>` +
      `<form method="post"><p>Stop receiving these emails? <input type="hidden" name="List-Unsubscribe" value="One-Click">` +
      `<button type="submit">Unsubscribe</button></p></form>`,
    200,
    NO_STORE,
  );
});

// RFC 8058: the mailbox provider POSTs `List-Unsubscribe=One-Click`; the confirmation page's button sends the same body.
app.post("/u/:token", async (c) => {
  const token = c.req.param("token");
  const claim = await verify(c.env.TRACKING_SECRET, token, "u");
  if (!claim) return c.text("not found", 404);
  const form = await c.req.formData().catch(() => null);
  if (form?.get("List-Unsubscribe") !== "One-Click") return c.text("expected List-Unsubscribe=One-Click", 400);
  const status = await forward(c.env, "unsubscribed", token, hostOf(c.req.url), claim.message_id);
  if (status >= 200 && status < 300) return c.text("You are unsubscribed.", 200, NO_STORE);
  return status >= 400 && status < 500 ? c.text("not found", 404) : c.text("try again later", 502);
});

export default app;
