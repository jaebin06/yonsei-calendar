"""연세대 신촌 생활관(dorm.yonsei.ac.kr) 공지·일정 수집기 — 무악학사 관련 글만.

분류가 '공통', '무악학사', '무악/우정'인 글 + config/profile.yaml 의 dorm.halls(예: 2학사)에 해당하는 글.
날짜: 제목의 날짜 → 본문에서 신청·단수·방역·점검·퇴사 등의 줄에 있는 날짜 순으로 찾는다.
robots.txt 없음(404). 요청 사이 3초 쉰다.
"""
from __future__ import annotations

import re
import time as _time
from datetime import date, datetime, time
from pathlib import Path
from typing import Optional

import httpx
import yaml
from bs4 import BeautifulSoup

from yc.collectors.yonsei import FULL, _dates_in
from yc.models import Event, make_id

BASE = "https://dorm.yonsei.ac.kr"
BOARDS = ["schedule", "notice"]
UA = "Mozilla/5.0 (yonsei-calendar; personal use; +https://github.com/jaebin06/yonsei-calendar)"
MAX_AGE_DAYS = 45
ALWAYS = {"공통", "무악학사", "무악/우정", "무악"}
KEY_LINE = re.compile(r"신청|기간|단수|정전|방역|점검|훈련|퇴사|입사|중단|일시|일자|납부|공사")


def _halls() -> set[str]:
    cfg = yaml.safe_load((Path(__file__).resolve().parents[2] / "config/profile.yaml").read_text(encoding="utf-8")) or {}
    return set((cfg.get("dorm") or {}).get("halls") or [])


def parse_list(html: str, board: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    for tr in soup.select("tr.hide_when_mobile"):
        tds = tr.find_all("td")
        a = tr.find("a", href=True)
        if not a or len(tds) < 4:
            continue
        m = re.search(r"idx=(\d+)", a["href"])
        if not m:
            continue
        posted = None
        pm = re.search(r"(20\d\d)-(\d{2})-(\d{2})", tr.get_text(" "))
        if pm:
            posted = date(int(pm[1]), int(pm[2]), int(pm[3]))
        rows.append({
            "idx": m.group(1),
            "category": tds[1].get_text(strip=True),
            "title": a.get_text(" ", strip=True),
            "url": f"{BASE}/board/?id={board}&mode=V&idx={m.group(1)}",
            "posted": posted,
        })
    return rows


def wanted(category: str, halls: set[str]) -> bool:
    return category in ALWAYS or category in halls


def dates_from_title(title: str, posted: date) -> list[date]:
    ds = _dates_in(title, posted)
    # '(10.16금→10.30금)' 처럼 요일이 괄호 밖에 붙은 형식
    for m in re.finditer(r"(?<![\d.])(\d{1,2})\.(\d{1,2})\s*[월화수목금토일]", FULL.sub(" ", title)):
        mo, dd = int(m[1]), int(m[2])
        y = posted.year + 1 if mo < posted.month - 2 else posted.year
        try:
            ds.append(date(y, mo, dd))
        except ValueError:
            pass
    return ds


def dates_from_article(html: str, posted: date) -> tuple[list[date], str]:
    """본문에서 날짜가 있는 첫 핵심 줄 → (날짜들, 그 줄). 줄은 캘린더 제목에 붙여서 무슨 날짜인지 보이게 한다."""
    soup = BeautifulSoup(html, "html.parser")
    for el in soup.find_all(["p", "li", "tr", "div"]):
        if el.find(["p", "li", "tr", "div"]):
            continue  # 가장 안쪽 블록만
        line = el.get_text(" ", strip=True)
        if KEY_LINE.search(line):
            ds = _dates_in(line, posted)
            if ds:
                return ds, re.sub(r"\s+", " ", line).strip(" *·,")[:40]
    return [], ""


def build_event(row: dict, ds: list[date], note: str = "") -> Optional[Event]:
    if not ds:
        return None
    if "→" in row["title"]:
        ds = [max(ds)]  # 일정 연기: 바뀐 날짜만
    start, end = min(ds), max(ds)
    if (end - start).days > 60:
        start = end
    return Event(
        id=make_id("dorm", row["idx"]),
        category="dorm",
        title=f"{row['title']} — {note}" if note else row["title"],
        source="dorm",
        url=row["url"],
        organizer=f"생활관 · {row['category']}",
        event_start=datetime.combine(start, time(0, 0)),
        event_end=datetime.combine(end, time(23, 59)),
        tags=[row["category"]],
        status="always",
    )


def collect(today: date | None = None, delay: float = 3.0) -> list[Event]:
    today = today or date.today()
    halls = _halls()
    events: list[Event] = []
    with httpx.Client(headers={"User-Agent": UA}, timeout=25, follow_redirects=True) as client:
        for board in BOARDS:
            resp = client.get(f"{BASE}/board/?id={board}")
            resp.raise_for_status()
            _time.sleep(delay)
            for row in parse_list(resp.text, board):
                posted = row["posted"] or today
                if (today - posted).days > MAX_AGE_DAYS or not wanted(row["category"], halls):
                    continue
                ds, note = dates_from_title(row["title"], posted), ""
                if not ds:
                    try:
                        art = client.get(row["url"])
                        _time.sleep(delay)
                        if art.status_code == 200:
                            ds, note = dates_from_article(art.text, posted)
                    except httpx.HTTPError:
                        continue
                ev = build_event(row, ds, note)
                if ev:
                    events.append(ev)
    return events
