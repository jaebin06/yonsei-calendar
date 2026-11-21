// 상태(선택·완료·추천 안 함)를 일정에 적용하는 규칙. Worker와 테스트가 같이 쓴다.

export const EMPTY_STATE = { selected: {}, done: {}, dismissed: {}, custom: [] };

// 기본으로 '내 일정'에 들어가는 종류. 대회·인턴·행사는 직접 골라야 들어간다.
const DEFAULT_IN = new Set(["academic", "exam", "dorm", "learnus", "custom"]);

export function isIncluded(ev, state) {
  if (state.dismissed[ev.id]) return false;
  if (ev.id in state.selected) return !!state.selected[ev.id];
  if (ev.category === "learnus" && ev.is_open) return false; // '과제 열림' 같은 시작 알림은 기본 제외
  if (ev.status === "starred") return true;
  return DEFAULT_IN.has(ev.category);
}

export function decorate(events, state) {
  return events.map((ev) => ({
    ...ev,
    included: isIncluded(ev, state),
    done: !!state.done[ev.id],
    dismissed: state.dismissed[ev.id]?.reason || null,
  }));
}

/** 상태 변경. 잘못된 요청은 Error를 던진다. */
export function applyOp(state, body, now = new Date()) {
  const s = structuredClone(state);
  const { op, id } = body || {};
  const needId = ["select", "unselect", "reset", "done", "undone", "dismiss", "undismiss", "delete"];
  if (needId.includes(op) && !(typeof id === "string" && /^[\w-]{3,80}$/.test(id))) throw new Error("bad id");
  switch (op) {
    case "select": s.selected[id] = true; delete s.dismissed[id]; break;
    case "unselect": s.selected[id] = false; break;
    case "reset": delete s.selected[id]; break;
    case "done": s.done[id] = now.toISOString(); break;
    case "undone": delete s.done[id]; break;
    case "dismiss": {
      const reason = ["대상 아님", "관심 없음", "이미 지원함", "기타"].includes(body.reason) ? body.reason : "관심 없음";
      s.dismissed[id] = { reason, at: now.toISOString() };
      s.selected[id] = false;
      break;
    }
    case "undismiss": delete s.dismissed[id]; delete s.selected[id]; break;
    case "add": {
      const title = String(body.title || "").trim().slice(0, 120);
      const date = String(body.date || "");
      if (!title || !/^\d{4}-\d{2}-\d{2}$/.test(date)) throw new Error("title/date required");
      const time = /^\d{2}:\d{2}$/.test(body.time || "") ? body.time : null;
      const kind = ["assignment", "video", "contest", "internship", "dorm", "other"].includes(body.kind) ? body.kind : "other";
      const cid = `custom-${now.getTime().toString(36)}`;
      s.custom.push({
        id: cid, category: "custom", kind, title, source: "custom",
        deadline: time ? `${date}T${time}` : null,
        event_start: time ? `${date}T${time}` : date,
        event_end: time ? `${date}T${time}` : date,
        url: /^https?:\/\//.test(body.url || "") ? body.url : "",
      });
      break;
    }
    case "delete": s.custom = s.custom.filter((c) => c.id !== id); delete s.done[id]; delete s.selected[id]; break;
    default: throw new Error("unknown op");
  }
  s.updated = now.toISOString();
  return s;
}

const KIND_LABEL = { assignment: "과제", video: "영상", quiz: "퀴즈", contest: "대회", internship: "인턴", dorm: "기숙사", other: "일정" };

/** '내 일정'에 든 일정 → 개인 피드 항목 */
export function feedItems(decorated) {
  const items = [];
  for (const ev of decorated) {
    if (!ev.included) continue;
    const check = ev.done ? "✅ " : "";
    const desc = [ev.course && `과목: ${ev.course}`, ev.organizer && `주최: ${ev.organizer}`, ev.url && `링크: ${ev.url}`]
      .filter(Boolean).join("\n");
    if (["contest", "internship", "event"].includes(ev.category)) {
      const label = ev.category === "internship" ? "인턴 마감" : "마감";
      if (ev.deadline) items.push({ uid: `${ev.id}-deadline`, summary: `${check}[${label}] ${ev.title}`, allDay: true, start: ev.deadline, description: desc, url: ev.url });
      if (ev.event_start) items.push({ uid: `${ev.id}-event`, summary: `${check}[${ev.category === "contest" ? "본선" : "행사"}] ${ev.title}`, allDay: true, start: ev.event_start, end: ev.event_end || ev.event_start, description: desc, url: ev.url });
    } else if (ev.category === "learnus" || ev.category === "custom") {
      const label = KIND_LABEL[ev.kind] || "일정";
      const timed = ev.event_start && ev.event_start.length > 10;
      items.push({ uid: ev.id, summary: `${check}[${label}] ${ev.course ? ev.course + " · " : ""}${ev.title}`, allDay: !timed, start: ev.event_start, end: timed ? ev.event_end || ev.event_start : ev.event_end, description: desc, url: ev.url });
    } else if (ev.event_start) {
      const prefix = ev.category === "dorm" ? "[기숙사] " : ev.category === "exam" ? "[시험] " : "";
      items.push({ uid: ev.id, summary: `${check}${prefix}${ev.title}`, allDay: true, start: ev.event_start, end: ev.event_end || ev.event_start, description: desc, url: ev.url });
    }
  }
  return items;
}
