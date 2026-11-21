// 연세 통합 일정 — 개인 서버 (Cloudflare Worker)
//
// GET  /api/events        내 상태가 적용된 전체 일정 (공개 일정 + LearnUs + 직접 추가)   [인증]
// POST /api/state         {op, id, ...} 선택·완료·추천 안 함·직접 추가                      [인증]
// GET  /api/feed-url      내 일정 구독 주소                                                [인증]
// GET  /feed/<토큰>.ics    '내 일정'에 든 것만 담은 구글 캘린더 구독용 피드
//
// 비밀값(GitHub Secrets → wrangler secret): APP_KEY, LEARNUS_URL
// 변수(wrangler.toml): PUBLIC_BASE, ALLOWED_ORIGINS

import { buildICS, learnusEvents } from "./ics.js";
import { applyOp, decorate, EMPTY_STATE, feedItems } from "./logic.js";

const STATE_KEY = "state";

async function loadState(env) {
  const raw = await env.STATE.get(STATE_KEY, "json");
  return { ...EMPTY_STATE, ...(raw || {}) };
}

async function hmacHex(key, msg) {
  const k = await crypto.subtle.importKey("raw", new TextEncoder().encode(key), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const sig = await crypto.subtle.sign("HMAC", k, new TextEncoder().encode(msg));
  return [...new Uint8Array(sig)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function authorized(request, env) {
  const got = (request.headers.get("Authorization") || "").replace(/^Bearer\s+/i, "");
  if (!env.APP_KEY || !got) return false;
  // 길이와 무관하게 같은 시간으로 비교 (해시끼리 비교)
  const [a, b] = await Promise.all([hmacHex("cmp", got), hmacHex("cmp", env.APP_KEY)]);
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

function cors(request, env) {
  const origin = request.headers.get("Origin") || "";
  const allowed = (env.ALLOWED_ORIGINS || "").split(",").map((s) => s.trim());
  return allowed.includes(origin)
    ? { "Access-Control-Allow-Origin": origin, "Access-Control-Allow-Headers": "Authorization, Content-Type", "Access-Control-Allow-Methods": "GET, POST, OPTIONS", Vary: "Origin" }
    : {};
}

const json = (data, status, headers) =>
  new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store", ...headers } });

async function fetchPublic(env) {
  const res = await fetch(`${env.PUBLIC_BASE}/events.json`, { cf: { cacheTtl: 600 } });
  if (!res.ok) throw new Error(`public events ${res.status}`);
  return res.json();
}

async function fetchLearnus(env) {
  if (!env.LEARNUS_URL) return { events: [], error: "LEARNUS_URL 미설정" };
  try {
    const res = await fetch(env.LEARNUS_URL, { cf: { cacheTtl: 900 }, headers: { "User-Agent": "yonsei-calendar personal" } });
    if (!res.ok) return { events: [], error: `LearnUs ${res.status}` };
    return { events: learnusEvents(await res.text()), error: null };
  } catch (e) {
    return { events: [], error: `LearnUs ${e.message}` };
  }
}

async function allEvents(env, state) {
  const [pub, ln] = await Promise.all([fetchPublic(env), fetchLearnus(env)]);
  const events = decorate([...pub.events, ...ln.events, ...state.custom], state);
  return {
    generated_at: pub.generated_at,
    health: { ...pub.health, learnus: ln.error ? { ok: false, count: 0, error: ln.error } : { ok: true, count: ln.events.length } },
    events,
  };
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const h = cors(request, env);
    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: h });

    try {
      // 구독 피드: 토큰 = HMAC(APP_KEY, "feed") → APP_KEY를 바꾸면 주소도 바뀐다
      const feed = url.pathname.match(/^\/feed\/([0-9a-f]{32})\.ics$/);
      if (feed) {
        const token = (await hmacHex(env.APP_KEY, "feed")).slice(0, 32);
        if (feed[1] !== token) return new Response("not found", { status: 404 });
        const state = await loadState(env);
        const data = await allEvents(env, state);
        return new Response(buildICS("내 일정", feedItems(data.events)), {
          headers: { "Content-Type": "text/calendar; charset=utf-8", "Cache-Control": "no-store" },
        });
      }

      if (!url.pathname.startsWith("/api/")) return new Response("yonsei-calendar", { status: 200 });
      if (!(await authorized(request, env))) return json({ error: "unauthorized" }, 401, h);

      if (url.pathname === "/api/events" && request.method === "GET") {
        const state = await loadState(env);
        return json(await allEvents(env, state), 200, h);
      }
      if (url.pathname === "/api/state" && request.method === "POST") {
        const body = await request.json().catch(() => ({}));
        const next = applyOp(await loadState(env), body);
        await env.STATE.put(STATE_KEY, JSON.stringify(next));
        return json({ ok: true, state: next }, 200, h);
      }
      if (url.pathname === "/api/feed-url" && request.method === "GET") {
        const token = (await hmacHex(env.APP_KEY, "feed")).slice(0, 32);
        return json({ url: `${url.origin}/feed/${token}.ics` }, 200, h);
      }
      return json({ error: "not found" }, 404, h);
    } catch (e) {
      return json({ error: e.message }, e.message.startsWith("bad") || e.message.includes("required") || e.message.startsWith("unknown") ? 400 : 500, h);
    }
  },
};
