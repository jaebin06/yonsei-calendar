"""연세대 공지사항(신촌, 게시판 58) 수집기.

'모집' 분류 전체 + '일반' 분류 중 대회·인턴 키워드가 있는 글만 본다.
마감일: 글 머리의 '기간' 칸 → 본문의 '접수/신청/응모 기간' 줄 → 제목의 '(~11/10)' 순으로 찾는다.
robots.txt: /bbs/ 허용 (2026-11-21 확인). 요청 사이 2초 쉰다.
"""
from __future__ import annotations

import re
import time as _time
from datetime import date, datetime, time, timedelta
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from yc.models import Event, make_id

BASE = "https://www.yonsei.ac.kr"
BOARDS = [
    # (목록 URL, 키워드 필터 적용 여부, 고정 분류)
    (f"{BASE}/bbs/sc/58/artclList.do?findClSeq=258", False, None),           # 모집
    (f"{BASE}/bbs/sc/58/artclList.do?findClSeq=97", True, None),             # 일반
    (f"{BASE}/bbs/sc/58/artclList.do?findClSeq=257", False, "scholarship"),  # 장학
]
SCHOLAR_SKIP_RE = re.compile(r"결과|합격자|선발자|명단|수혜자\s*발표|지급\s*안내|환수|반납|설문|서비스\s*안내|예방|중복지원|^(?!.*(장학|학자금)).*$")
CONDITION_LINE = re.compile(r"대상|자격|요건|조건|기준|선발\s*분야")
UA = "Mozilla/5.0 (yonsei-calendar; personal use; +https://github.com/jaebin06/yonsei-calendar)"
MAX_AGE_DAYS = 60

CONTEST_RE = re.compile(r"공모전|경진대회|대회|해커톤|챌린지|아이디어|창업|Hackathon|Challenge", re.I)
INTERN_RE = re.compile(r"인턴|채용|Intern", re.I)
SKIP_RE = re.compile(r"장학|봉사|시상식|결과\s*발표|수상자|폐강")
DEADLINE_LINE = re.compile(r"(접수|신청|응모|모집|제출|참가)\s*(기간|마감|기한|일정)|마감\s*[:：]")

FULL = re.compile(r"(20\d\d)\s*[.\-/년]\s*(\d{1,2})\s*[.\-/월]\s*(\d{1,2})")
SHORT = re.compile(r"(?<![\d.])(\d{1,2})\s*[./월]\s*(\d{1,2})\s*\.?\s*(?:일)?\s*\(\s*[월화수목금토일]")
TITLE_TILDE = re.compile(r"~\s*(\d{1,2})\s*[./]\s*(\d{1,2})")
HOUR = re.compile(r"(\d{1,2})\s*시|(\d{1,2}):(\d{2})")


def parse_list(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    rows, seen = [], set()
    for li in soup.select("li"):
        a = li.find("a", href=lambda h: h and "artclView" in h)
        t = li.select_one(".title")
        if not a or not t or a["href"] in seen:
            continue
        seen.add(a["href"])
        title = re.sub(r"새글$", "", t.get_text(" ", strip=True)).strip()
        d = li.select_one(".date-area")
        posted = None
        if d:
            m = FULL.search(d.get_text())
            if m:
                posted = date(int(m[1]), int(m[2]), int(m[3]))
        rows.append({"title": title, "url": BASE + a["href"], "posted": posted})
    return rows


def _year_for(month: int, posted: date) -> int:
    return posted.year + 1 if month < posted.month - 2 else posted.year


def _with_time(d: date, line: str) -> datetime:
    # '3. 25.(수) 10:00 ~ 4. 3.(금) 18:00' → 마감 시각은 '~' 뒤쪽에서 찾는다
    seg = line.rsplit("~", 1)[-1] if line and "~" in line else (line.split(str(d.day), 1)[-1] if line else "")
    m = HOUR.search(seg) if seg else None
    if m:
        hh = int(m[1] or m[2])
        mm = int(m[3] or 0)
        if 0 <= hh <= 23:
            return datetime.combine(d, time(hh, mm))
    if line and "자정" in line:
        return datetime.combine(d, time(23, 59))
    return datetime.combine(d, time(23, 59))


def _dates_in(line: str, posted: date) -> list[date]:
    out = []
    for m in FULL.finditer(line):
        try:
            out.append(date(int(m[1]), int(m[2]), int(m[3])))
        except ValueError:
            pass
    stripped = FULL.sub(" ", line)
    for m in SHORT.finditer(stripped):
        mo, dd = int(m[1]), int(m[2])
        try:
            out.append(date(_year_for(mo, posted), mo, dd))
        except ValueError:
            pass
    return out


def parse_article(html: str, title: str, posted: date) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    view = soup.select_one(".board-view") or soup
    info = {"organizer": "", "deadline": None, "date_source": ""}

    # 머리 정보: '담당부서', '기간'
    labels = view.select("span")
    for sp in labels:
        label = sp.get_text(strip=True)
        if label in ("담당부서", "기간"):
            value = sp.parent.get_text(" ", strip=True).replace(label, "", 1).strip()
            if label == "담당부서":
                info["organizer"] = value
            elif label == "기간":
                ds = _dates_in(value, posted)
                if ds:
                    info["deadline"] = datetime.combine(max(ds), time(23, 59))
                    info["date_source"] = "기간"
    header_deadline = info["deadline"]

    # 줄 단위: 블록 요소마다 한 줄 (span으로 쪼개진 '접수기간: ~ 11. 10.'을 한 줄로 합친다)
    lines = [el.get_text(" ", strip=True) for el in view.find_all(["p", "li", "tr", "dd", "h3", "h4"])]
    body = "\n".join(lines)
    # 본문의 '신청기간' 줄도 본다. 머리의 '기간'이 게시 기간일 때가 있어서(예: 2/3~2/3, 실제 신청은 4/3까지) 더 늦은 쪽을 쓴다
    candidates = []
    for line in lines:
        if DEADLINE_LINE.search(line):
            for d in _dates_in(line, posted):
                candidates.append((d, line))
    if candidates:
        d, line = max(candidates, key=lambda x: x[0])
        if header_deadline is None or d > header_deadline.date():
            info["deadline"] = _with_time(d, line)
            info["date_source"] = "본문"
        elif d == header_deadline.date():
            info["deadline"] = _with_time(d, line)  # 같은 날이면 본문의 마감 시각(예: 18시)을 쓴다
    if not info["deadline"]:
        m = TITLE_TILDE.search(title)
        if m:
            mo, dd = int(m[1]), int(m[2])
            try:
                info["deadline"] = datetime.combine(date(_year_for(mo, posted), mo, dd), time(23, 59))
                info["date_source"] = "제목"
            except ValueError:
                pass
    info["eligibility"] = "재학생" if re.search(r"재학생|학부생", body) else ""
    # 장학금용: 지원대상·자격 줄을 모아 둔다 (점수 계산과 대시보드 표시에 사용)
    conds = []
    for line in lines:
        if CONDITION_LINE.search(line) and line not in conds and len(line) < 300:
            conds.append(line)
        if len(conds) >= 6:
            break
    info["conditions"] = " / ".join(conds)[:500]
    info["graduate_only"] = bool(re.search(r"대학원생이 팀장|대학원생\s*대상|대학원생만", body))
    return info


def _category(title: str) -> Optional[str]:
    if SKIP_RE.search(title):
        return None
    if INTERN_RE.search(title):
        return "internship"
    if CONTEST_RE.search(title):
        return "contest"
    return "event"


def collect(today: date | None = None, delay: float = 2.0) -> list[Event]:
    today = today or date.today()
    events: list[Event] = []
    seen: set[str] = set()
    with httpx.Client(headers={"User-Agent": UA}, timeout=20, follow_redirects=True) as client:
        for url, keyword_only, fixed in BOARDS:
            resp = client.get(url)
            resp.raise_for_status()
            _time.sleep(delay)
            for row in parse_list(resp.text):
                if row["url"] in seen:
                    continue
                seen.add(row["url"])
                posted = row["posted"] or today
                if (today - posted).days > MAX_AGE_DAYS:
                    continue
                if fixed == "scholarship":
                    if SCHOLAR_SKIP_RE.search(row["title"]):
                        continue
                    cat = "scholarship"
                else:
                    cat = _category(row["title"])
                if cat is None:
                    continue
                if keyword_only and cat == "event":
                    continue
                art = client.get(row["url"])
                _time.sleep(delay)
                if art.status_code != 200:
                    continue
                ev = build_event(row, art.text, cat)
                if ev:
                    events.append(ev)
    return events


def build_event(row: dict, html: str, cat: str) -> Optional[Event]:
    posted = row["posted"] or date.today()
    info = parse_article(html, row["title"], posted)
    ev = Event(
        id=make_id("yonsei-notice", row["url"]),
        category=cat,
        title=row["title"],
        source="yonsei-notice",
        url=row["url"],
        organizer=info["organizer"] or "연세대학교",
        deadline=info["deadline"],
        eligibility=info["eligibility"],
        tags=["연세대 공지"] + ([f"날짜:{info['date_source']}"] if info["date_source"] else []),
    )
    if cat == "scholarship":
        ev.eligibility = info["conditions"]
    elif info["graduate_only"]:
        ev.eligibility = "대학원생 대상"
    return ev
