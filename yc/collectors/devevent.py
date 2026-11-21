"""Dev-Event(github.com/brave-people/Dev-Event) README 수집기.

README 형식 예:
    ## `26년 11월`
    - __[행사명](https://...)__
      - 분류: `오프라인(서울 강남구)`, `무료`, `대회`, `AI`
      - 주최: 주최사
      - 접수: 10. 12(월) ~ 11. 20(금) 17:00
      - 일시: 11. 21(토) 13:00 ~ 11. 21(토) 18:00
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Optional

import httpx

from yc.models import Event, make_id

README_URL = "https://raw.githubusercontent.com/brave-people/Dev-Event/master/README.md"

MONTH_HEADER = re.compile(r"^##\s+`(\d{2})년\s+(\d{1,2})월`")
ENTRY = re.compile(r"^- __\[(?P<title>.+?)\]\((?P<url>[^)\s]+)\)__\s*$")
FIELD = re.compile(r"^\s+- (?P<key>분류|주최|접수|일시):\s*(?P<value>.*)$")
TAG = re.compile(r"`([^`]+)`")
# "11. 20(금) 17:00" / "11. 20(금)"
POINT = re.compile(r"(\d{1,2})\.\s*(\d{1,2})\([^)]*\)(?:\s*(\d{1,2}):(\d{2}))?")


def fetch(timeout: float = 20.0) -> str:
    resp = httpx.get(README_URL, timeout=timeout, follow_redirects=True)
    resp.raise_for_status()
    return resp.text


def _resolve_year(month: int, header_year: int, header_month: int) -> int:
    """'1. 05' 처럼 연도가 없는 날짜의 연도를 헤더 월 기준으로 추정."""
    if month - header_month > 6:
        return header_year - 1
    if header_month - month > 6:
        return header_year + 1
    return header_year


def _parse_range(value: str, header_year: int, header_month: int,
                 default_time: tuple[int, int]) -> tuple[Optional[datetime], Optional[datetime]]:
    points = POINT.findall(value)
    if not points:
        return None, None

    def to_dt(p, is_end: bool) -> datetime:
        m, d, hh, mm = int(p[0]), int(p[1]), p[2], p[3]
        y = _resolve_year(m, header_year, header_month)
        if hh:
            return datetime(y, m, d, int(hh), int(mm))
        h, mi = default_time if is_end else (0, 0)
        return datetime(y, m, d, h, mi)

    start = to_dt(points[0], is_end=False)
    end = to_dt(points[-1], is_end=True) if len(points) > 1 else None
    return start, end


def parse(markdown: str) -> list[Event]:
    events: list[Event] = []
    header: Optional[tuple[int, int]] = None
    cur: Optional[dict] = None

    def flush():
        if cur and header:
            ev = _build(cur, header)
            if ev:
                events.append(ev)

    for line in markdown.splitlines():
        h = MONTH_HEADER.match(line)
        if h:
            flush()
            cur = None
            header = (2000 + int(h.group(1)), int(h.group(2)))
            continue
        if line.startswith("## "):  # 다른 섹션(다시보기 등)
            flush()
            cur = None
            header = None
            continue
        e = ENTRY.match(line)
        if e and header:
            flush()
            cur = {"title": e.group("title").strip(), "url": e.group("url"), "fields": {}}
            continue
        f = FIELD.match(line)
        if f and cur is not None:
            cur["fields"][f.group("key")] = f.group("value").strip()
    flush()
    return events


def _build(raw: dict, header: tuple[int, int]) -> Optional[Event]:
    y, m = header
    fields = raw["fields"]
    tags = TAG.findall(fields.get("분류", ""))
    apply_start = deadline = ev_start = ev_end = None
    if "접수" in fields:
        s, e = _parse_range(fields["접수"], y, m, default_time=(23, 59))
        apply_start = s.date() if s and e else None
        deadline = e or s
    if "일시" in fields:
        ev_start, ev_end = _parse_range(fields["일시"], y, m, default_time=(23, 59))
    if not (deadline or ev_start):
        return None

    locations = [t for t in tags if t.startswith(("오프라인", "온라인"))]
    category = "contest" if "대회" in tags else "event"
    return Event(
        id=make_id("devevent", raw["title"], raw["url"]),
        category=category,
        title=raw["title"],
        source="dev-event",
        url=raw["url"],
        organizer=fields.get("주최", ""),
        apply_start=apply_start,
        deadline=deadline,
        event_start=ev_start,
        event_end=ev_end,
        tags=tags,
        location=", ".join(locations),
    )


def collect() -> list[Event]:
    return parse(fetch())
