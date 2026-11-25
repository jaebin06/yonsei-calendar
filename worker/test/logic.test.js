import { test } from "node:test";
import assert from "node:assert/strict";
import { buildICS, icsDateToKst, learnusEvents, parseICS } from "../src/ics.js";
import { applyOp, decorate, EMPTY_STATE, feedItems, isIncluded, kstToday } from "../src/logic.js";

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

test("기간이 있는 LearnUs 항목은 끝나는 시각에만", () => {
  const evs = learnusEvents("BEGIN:VEVENT\r\nUID:7@x\r\nSUMMARY:10주차 동영상\r\nDTSTART:20261119T150000Z\r\nDTEND:20261123T150000Z\r\nEND:VEVENT");
  assert.equal(evs[0].event_start, "2026-11-24T00:00");
  assert.equal(evs[0].event_end, "2026-11-24T00:00");
  assert.equal(evs[0].deadline, "2026-11-24T00:00");
  assert.equal(evs[0].available_from, "2026-11-20T00:00");
  const items = feedItems(decorate(evs, EMPTY_STATE));
  assert.equal(items.length, 1);
  assert.equal(items[0].start, items[0].end);
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

test("90점 이상 대회는 정할 때까지 참여 결정 항목", () => {
  const now = new Date("2026-11-24T03:00:00Z"); // KST 11/24 12:00
  assert.equal(kstToday(now), "2026-11-24");
  const ev = { id: "devevent-aaaa0001", category: "contest", title: "SVC Seoul AI 해커톤", ask: true, score: 90, deadline: "2026-11-29T23:59" };
  let d = decorate([ev], EMPTY_STATE, now);
  assert.equal(d[0].needs_decision, true);
  const items = feedItems(d, now);
  assert.equal(items.length, 1);
  assert.equal(items[0].start, "2026-11-24");
  assert.match(items[0].summary, /참여 결정.*D-5, 90점/);
  // 참여하기로 하면 질문은 사라지고 마감 일정이 들어간다
  let s = applyOp(EMPTY_STATE, { op: "select", id: ev.id }, now);
  d = decorate([ev], s, now);
  assert.equal(d[0].needs_decision, false);
  assert.deepEqual(feedItems(d, now).map((i) => i.summary), ["[마감] SVC Seoul AI 해커톤"]);
  // 안 하기로 해도 사라진다
  s = applyOp(EMPTY_STATE, { op: "dismiss", id: ev.id, reason: "관심 없음" }, now);
  assert.equal(decorate([ev], s, now)[0].needs_decision, false);
  // 마감이 지나면 묻지 않는다
  assert.equal(decorate([{ ...ev, deadline: "2026-11-20T23:59" }], EMPTY_STATE, now)[0].needs_decision, false);
});

test("장학금은 고르면 [장학 마감], 묻는 문구는 신청 결정", () => {
  const now = new Date("2026-11-25T03:00:00Z");
  const ev = { id: "yonsei-notice-aaaa0002", category: "scholarship", title: "울산연구원 장학생 선발", ask: true, score: 95, deadline: "2026-12-10T18:00" };
  assert.match(feedItems(decorate([ev], EMPTY_STATE, now), now)[0].summary, /신청 결정/);
  const s = applyOp(EMPTY_STATE, { op: "select", id: ev.id }, now);
  assert.deepEqual(feedItems(decorate([ev], s, now), now).map((i) => i.summary), ["[장학 마감] 울산연구원 장학생 선발"]);
});

test("Progress start / stop은 할 일 하나로 합친다", () => {
  const ics = [
    "BEGIN:VEVENT", "UID:a1@x", "SUMMARY:11주차 강의 (Progress start)", "CATEGORIES:CAS3201", "DTSTART:20261123T150000Z", "END:VEVENT",
    "BEGIN:VEVENT", "UID:a2@x", "SUMMARY:11주차 강의 (Progress stop)", "CATEGORIES:CAS3201", "DTSTART:20261130T145900Z", "END:VEVENT",
    "BEGIN:VEVENT", "UID:b1@x", "SUMMARY:12주차 강의 Progress start", "CATEGORIES:CAS3201", "DTSTART:20261130T150000Z", "END:VEVENT",
    "BEGIN:VEVENT", "UID:c1@x", "SUMMARY:과제5 마감", "CATEGORIES:CAS2250", "DTSTART:20261201T145900Z", "END:VEVENT",
  ].join("\r\n");
  const evs = learnusEvents(ics);
  const v11 = evs.find((e) => e.title === "11주차 강의");
  assert.ok(v11);
  assert.equal(v11.event_start, "2026-11-30T23:59");
  assert.equal(v11.available_from, "2026-11-24T00:00");
  assert.equal(v11.kind, "video");
  assert.equal(evs.filter((e) => e.title.startsWith("11주차")).length, 1);
  const v12 = evs.find((e) => e.title.startsWith("12주차"));
  assert.equal(v12.is_open, true);
  assert.equal(isIncluded(v12, EMPTY_STATE), false);
  assert.ok(evs.find((e) => e.title === "과제5 마감")); // '마감'은 짝이 없으면 그대로
});
