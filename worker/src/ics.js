// ICS 읽기(LearnUs)와 쓰기(개인 피드). 외부 라이브러리 없이 필요한 만큼만 구현.

const KST_OFFSET_MS = 9 * 3600 * 1000;

/** 줄 접기 해제 + VEVENT 파싱 → [{UID, SUMMARY, DTSTART:{value,params}, ...}] */
export function parseICS(text) {
  const lines = text.replace(/\r\n[ \t]/g, "").replace(/\n[ \t]/g, "").split(/\r?\n/);
  const events = [];
  let cur = null;
  for (const line of lines) {
    if (line === "BEGIN:VEVENT") { cur = {}; continue; }
    if (line === "END:VEVENT") { if (cur) events.push(cur); cur = null; continue; }
    if (!cur) continue;
    const i = line.indexOf(":");
    if (i < 0) continue;
    const [name, ...paramParts] = line.slice(0, i).split(";");
    const params = Object.fromEntries(paramParts.map((p) => p.split("=")));
    cur[name.toUpperCase()] = { value: unescapeText(line.slice(i + 1)), params };
  }
  return events;
}

function unescapeText(s) {
  return s.replace(/\\n/gi, "\n").replace(/\\([,;\\])/g, "$1");
}

/** ICS 날짜값 → KST 기준 'YYYY-MM-DDTHH:MM' (시간 없는 날짜는 'YYYY-MM-DD') */
export function icsDateToKst(prop) {
  if (!prop) return null;
  const v = prop.value.trim();
  if (/^\d{8}$/.test(v)) return `${v.slice(0, 4)}-${v.slice(4, 6)}-${v.slice(6, 8)}`;
  const m = v.match(/^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})(Z?)$/);
  if (!m) return null;
  const [, y, mo, d, h, mi, s, z] = m;
  let ms = Date.UTC(+y, +mo - 1, +d, +h, +mi, +s);
  if (z === "Z") ms += KST_OFFSET_MS; // UTC → KST
  // TZID가 있으면(예: Asia/Seoul) 이미 현지 시각으로 본다
  return new Date(ms).toISOString().slice(0, 16);
}

/** FNV-1a 32bit → 8자리 hex (안정적인 id용) */
export function shortHash(s) {
  let h = 0x811c9dc5;
  for (const ch of new TextEncoder().encode(s)) {
    h ^= ch;
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h.toString(16).padStart(8, "0");
}

/** LearnUs ICS → 대시보드 공통 형식 */
export function learnusEvents(text) {
  return parseICS(text).map((ve) => {
    const title = ve.SUMMARY?.value?.trim() || "(제목 없음)";
    const desc = ve.DESCRIPTION?.value || "";
    const start = icsDateToKst(ve.DTSTART);
    const end = icsDateToKst(ve.DTEND);
    // 기간이 있는 항목(예: 20일 00시 ~ 24일 00시)은 끝나는 시각이 마감 → 끝나는 날에만 표시
    const due = end && start && end > start ? end : start;
    const from = due !== start ? start : null;
    const hay = `${title} ${desc}`;
    let kind = "assignment";
    if (/동영상|영상|VOD|vod|시청|강의\s*콘텐츠/.test(hay)) kind = "video";
    else if (/퀴즈|quiz|시험/i.test(hay)) kind = "quiz";
    const isOpen = /\b(opens|열림)\b|시작\s*$|오픈/.test(title);
    return {
      id: `learnus-${shortHash(ve.UID?.value || title + start)}`,
      category: "learnus",
      kind,
      is_open: isOpen,
      title,
      course: ve.CATEGORIES?.value || "",
      source: "learnus",
      deadline: due && due.length > 10 ? due : null,
      event_start: due,
      event_end: due,
      available_from: from,
      url: "https://ys.learnus.org/calendar/view.php?view=upcoming",
    };
  }).filter((e) => e.event_start);
}

// ---------- 쓰기 ----------

function escapeText(s) {
  return String(s ?? "").replace(/\\/g, "\\\\").replace(/;/g, "\\;").replace(/,/g, "\\,").replace(/\r?\n/g, "\\n");
}

/** 75바이트 단위 줄 접기 (UTF-8 글자 중간에서 자르지 않음) */
function fold(line) {
  const enc = new TextEncoder();
  const out = [];
  let cur = "", bytes = 0;
  for (const ch of line) {
    const b = enc.encode(ch).length;
    if (bytes + b > (out.length ? 74 : 75)) {
      out.push(cur);
      cur = "";
      bytes = 0;
    }
    cur += ch;
    bytes += b;
  }
  out.push(cur);
  return out.join("\r\n ");
}

const ymd = (iso) => iso.slice(0, 10).replace(/-/g, "");
const addDays = (iso, n) => {
  const d = new Date(iso.slice(0, 10) + "T00:00:00Z");
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
};
/** KST 'YYYY-MM-DDTHH:MM' → UTC 'YYYYMMDDTHHMMSSZ' */
const kstToUtcStamp = (iso) => {
  const ms = Date.parse(iso + ":00Z") - KST_OFFSET_MS;
  return new Date(ms).toISOString().replace(/[-:]/g, "").slice(0, 15) + "Z";
};

export function buildICS(name, items, now = new Date()) {
  const stamp = now.toISOString().replace(/[-:]/g, "").slice(0, 15) + "Z";
  const lines = [
    "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//jaebin06//yonsei-calendar personal//KO", "CALSCALE:GREGORIAN",
    `X-WR-CALNAME:${escapeText(name)}`, "X-WR-TIMEZONE:Asia/Seoul",
    "REFRESH-INTERVAL;VALUE=DURATION:PT1H", "X-PUBLISHED-TTL:PT1H",
  ];
  for (const it of items) {
    lines.push("BEGIN:VEVENT", `UID:${it.uid}@yonsei-calendar`, `DTSTAMP:${stamp}`, `SUMMARY:${escapeText(it.summary)}`);
    if (it.allDay) {
      lines.push(`DTSTART;VALUE=DATE:${ymd(it.start)}`, `DTEND;VALUE=DATE:${ymd(addDays(it.end || it.start, 1))}`);
    } else {
      lines.push(`DTSTART:${kstToUtcStamp(it.start)}`, `DTEND:${kstToUtcStamp(it.end || it.start)}`);
    }
    if (it.description) lines.push(`DESCRIPTION:${escapeText(it.description)}`);
    if (it.url) lines.push(`URL:${it.url}`);
    lines.push("TRANSP:TRANSPARENT", "END:VEVENT");
  }
  lines.push("END:VCALENDAR");
  return lines.map(fold).join("\r\n") + "\r\n";
}
