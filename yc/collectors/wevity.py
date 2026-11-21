"""위비티(wevity.com) 공모전 목록 수집기.

목록의 'D-22 접수중' 표시로 마감일을 계산한다(정확한 시각은 원문 확인).
robots.txt: 모든 경로 허용 (2026-11-21 확인). 요청 사이 2초 쉰다.
"""
from __future__ import annotations

import re
import time as _time
from datetime import date, datetime, time, timedelta
from urllib.parse import parse_qs, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from yc.models import Event, make_id

BASE = "https://www.wevity.com/"
# 웹/모바일/IT, 게임/소프트웨어, 기획/아이디어, 취업/창업 — 각 2페이지
CATEGORIES = [20, 21, 1, 88]
PAGES = [1, 2]
UA = "Mozilla/5.0 (yonsei-calendar; personal use; +https://github.com/jaebin06/yonsei-calendar)"
DDAY = re.compile(r"D-(\d+)")


def list_url(cidx: int, page: int) -> str:
    return f"{BASE}?c=find&s=1&gub=1&cidx={cidx}&gp={page}"


def parse(html: str, today: date) -> list[Event]:
    soup = BeautifulSoup(html, "html.parser")
    events = []
    for li in soup.select("ul.list > li"):
        if "top" in (li.get("class") or []):
            continue
        a = li.select_one(".tit a")
        day = li.select_one(".day")
        if not a or not day:
            continue
        day_text = day.get_text(" ", strip=True)
        if "마감" in day_text and "임박" not in day_text:
            continue  # 이미 끝남 (D+n 마감)
        m = DDAY.search(day_text)
        if m:
            left = int(m.group(1))
        elif "D-day" in day_text or "오늘" in day_text:
            left = 0
        else:
            continue
        for badge in a.select("span"):
            badge.decompose()
        title = a.get_text(" ", strip=True)
        href = urljoin(BASE, a["href"])
        ix = parse_qs(urlparse(href).query).get("ix", [title])[0]
        sub = li.select_one(".sub-tit")
        tags = []
        if sub:
            tags = [t.strip() for t in sub.get_text(strip=True).replace("분야 :", "").split(",") if t.strip()]
        organ = li.select_one(".organ")
        events.append(Event(
            id=make_id("wevity", ix),
            category="contest",
            title=title,
            source="wevity",
            url=f"{BASE}?c=find&s=1&gbn=view&ix={ix}",
            organizer=organ.get_text(strip=True) if organ else "",
            deadline=datetime.combine(today + timedelta(days=left), time(23, 59)),
            tags=tags,
        ))
    return events


def collect(today: date | None = None, delay: float = 2.0) -> list[Event]:
    today = today or date.today()
    found: dict[str, Event] = {}
    with httpx.Client(headers={"User-Agent": UA}, timeout=20, follow_redirects=True) as client:
        for cidx in CATEGORIES:
            for page in PAGES:
                resp = client.get(list_url(cidx, page))
                resp.raise_for_status()
                for ev in parse(resp.text, today):
                    found.setdefault(ev.id, ev)
                _time.sleep(delay)
    return list(found.values())
