"""Event 목록 → .ics 피드 (기획안 6장)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from icalendar import Calendar, Event as IEvent

from yc.models import Event

KST = timezone(timedelta(hours=9))
DOMAIN = "yonsei-calendar"


def _calendar(name: str) -> Calendar:
    cal = Calendar()
    cal.add("prodid", "-//jaebin06//yonsei-calendar//KO")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("x-wr-calname", name)
    cal.add("x-wr-timezone", "Asia/Seoul")
    # 구글이 다시 읽는 주기에 대한 힌트(지켜지지 않을 수 있음)
    cal.add("refresh-interval;value=duration", "PT12H")
    cal.add("x-published-ttl", "PT12H")
    return cal


def _all_day(uid: str, summary: str, start, end_inclusive, description: str, url: str,
             stamp: datetime) -> IEvent:
    ie = IEvent()
    ie.add("uid", f"{uid}@{DOMAIN}")
    ie.add("summary", summary)
    ie.add("dtstart", start)
    ie.add("dtend", end_inclusive + timedelta(days=1))  # 종일 일정의 끝은 다음 날(배타적)
    ie.add("dtstamp", stamp)
    ie.add("transp", "TRANSPARENT")
    if description:
        ie.add("description", description)
    if url:
        ie.add("url", url)
    return ie


def _description(ev: Event) -> str:
    lines = []
    if ev.organizer:
        lines.append(f"주최: {ev.organizer}")
    if ev.deadline:
        lines.append(f"마감: {ev.deadline:%Y-%m-%d %H:%M}")
    if ev.location:
        lines.append(f"장소: {ev.location}")
    if ev.prize:
        lines.append(f"혜택: {ev.prize}")
    if ev.warnings:
        lines.append("주의: " + ", ".join(ev.warnings))
    if ev.score_reasons:
        lines.append(f"점수 {ev.score}: " + ", ".join(ev.score_reasons))
    if ev.url:
        lines.append(f"원문: {ev.url}")
    lines.append("마감일은 원문에서 한 번 더 확인하세요.")
    return "\n".join(lines)


def build_period_feed(name: str, events: list[Event], stamp: datetime) -> bytes:
    """학사·시험: 기간 일정 그대로."""
    cal = _calendar(name)
    for ev in events:
        start = ev.event_start.date()
        end = (ev.event_end or ev.event_start).date()
        cal.add_component(_all_day(ev.id, ev.title, start, end, "", ev.url, stamp))
    return cal.to_ical()


def build_deadline_feed(name: str, events: list[Event], stamp: datetime,
                        label: str = "마감") -> bytes:
    """대회·인턴: [마감] + [D-7] + [본선/행사] 일정."""
    cal = _calendar(name)
    for ev in events:
        desc = _description(ev)
        prefix = "[시험기간] " if ev.warnings else ""
        base = f"{ev.organizer} · {ev.title}" if ev.category == "internship" and ev.organizer else ev.title
        if ev.deadline:
            d = ev.deadline.date()
            cal.add_component(_all_day(f"{ev.id}-deadline", f"{prefix}[{label}] {base}", d, d,
                                       desc, ev.url, stamp))
            remind = d - timedelta(days=7)
            if remind > stamp.astimezone(KST).date():
                cal.add_component(_all_day(f"{ev.id}-d7", f"[D-7] {base}", remind, remind,
                                           desc, ev.url, stamp))
        if ev.event_start:
            s = ev.event_start.date()
            e = (ev.event_end or ev.event_start).date()
            tag = "본선" if ev.category == "contest" else "행사"
            cal.add_component(_all_day(f"{ev.id}-event", f"{prefix}[{tag}] {base}", s, e,
                                       desc, ev.url, stamp))
    return cal.to_ical()
