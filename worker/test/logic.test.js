import { test } from "node:test";
import assert from "node:assert/strict";
import { buildICS, icsDateToKst, learnusEvents, parseICS } from "../src/ics.js";
import { applyOp, decorate, EMPTY_STATE, feedItems, isIncluded } from "../src/logic.js";

const LEARNUS = [
  "BEGIN:VCALENDAR",
  "BEGIN:VEVENT",
  "UID:1234@ys.learnus.org",
  "SUMMARY:과제3: NLP 감성분류 보고서 마감",
  "DESCRIPTION:보고서를 제출하세요",
  "CATEGORIES:CAS2250-01",
  "DTSTART:20261205T145900Z",
  "DTEND:20261205T145900Z",
  "END:VEVENT",
  "BEGIN:VEVENT",
  "UID:5678@ys.learnus.org",
  "SUMMARY:9주차 강의 동영상 시청 종료",
  "CATEGORIES:CAS3201-01",
  "DTSTART:20261128T145900Z",
  "END:VEVENT",
  "BEGIN:VEVENT",
  "UID:9999@ys.learnus.org",
  "SUMMARY:과제4 opens",
  "DTSTART:20261201T000000Z",
  "END:VEVENT",
  "END:VCALENDAR",
].join("\r\n");

test("LearnUs ICS 파싱: UTC → KST, 종류 판별", () => {
  const evs = learnusEvents(LEARNUS);
  assert.equal(evs.length, 3);
  const [a, v, o] = evs;
  assert.equal(a.event_start, "2026-12-05T23:59");
  assert.equal(a.kind, "assignment");
  assert.equal(a.course, "CAS2250-01");
  assert.equal(v.kind, "video");
  assert.equal(o.is_open, true);
  assert.match(a.id, /^learnus-[0-9a-f]{8}$/);
});

test("줄 접기 해제", () => {
  const evs = parseICS("BEGIN:VEVENT\r\nSUMMARY:긴 제\r\n 목\r\nEND:VEVENT");
  assert.equal(evs[0].SUMMARY.value, "긴 제목");
});

test("기본 포함 규칙", () => {
  const s = EMPTY_STATE;
  assert.equal(isIncluded({ id: "a", category: "academic" }, s), true);
  assert.equal(isIncluded({ id: "b", category: "contest", status: "recommended" }, s), false);
  assert.equal(isIncluded({ id: "c", category: "learnus", is_open: true }, s), false);
  assert.equal(isIncluded({ id: "d", category: "learnus" }, s), true);
});

test("선택·완료·추천 안 함", () => {
  let s = applyOp(EMPTY_STATE, { op: "select", id: "devevent-1234abcd" });
  assert.equal(isIncluded({ id: "devevent-1234abcd", category: "contest" }, s), true);
  s = applyOp(s, { op: "done", id: "devevent-1234abcd" });
  s = applyOp(s, { op: "dismiss", id: "wevity-aaaa1111", reason: "대상 아님" });
  const d = decorate([{ id: "devevent-1234abcd", category: "contest", title: "AI 해커톤", deadline: "2026-12-10T18:00" },
                      { id: "wevity-aaaa1111", category: "contest", title: "X" }], s);
  assert.equal(d[0].done, true);
  assert.equal(d[1].dismissed, "대상 아님");
  assert.equal(d[1].included, false);
  const items = feedItems(d);
  assert.equal(items.length, 1);
  assert.equal(items[0].summary, "✅ [마감] AI 해커톤");
});

test("잘못된 요청 거절", () => {
  assert.throws(() => applyOp(EMPTY_STATE, { op: "select", id: "../x" }));
  assert.throws(() => applyOp(EMPTY_STATE, { op: "drop" }));
  assert.throws(() => applyOp(EMPTY_STATE, { op: "add", title: "", date: "2026-12-01" }));
});

test("직접 추가 → 피드", () => {
  const s = applyOp(EMPTY_STATE, { op: "add", title: "기숙사 퇴사 점검", date: "2026-12-22", time: "10:00", kind: "dorm" }, new Date("2026-11-22T00:00:00Z"));
  const d = decorate(s.custom, s);
  assert.equal(d[0].included, true);
  const ics = buildICS("내 일정", feedItems(d), new Date("2026-11-22T00:00:00Z"));
  assert.match(ics, /DTSTART:20261222T010000Z/); // 10:00 KST
  assert.match(ics, /\[기숙사\] 기숙사 퇴사 점검/);
});

test("ICS 줄은 75바이트를 넘지 않는다", () => {
  const ics = buildICS("내 일정", [{ uid: "x", summary: "가".repeat(80), allDay: true, start: "2026-12-01" }]);
  for (const line of ics.split("\r\n")) assert.ok(new TextEncoder().encode(line).length <= 75, line);
});

test("날짜 변환", () => {
  assert.equal(icsDateToKst({ value: "20261231" }), "2026-12-31");
  assert.equal(icsDateToKst({ value: "20261231T150000Z" }), "2027-01-01T00:00");
});
