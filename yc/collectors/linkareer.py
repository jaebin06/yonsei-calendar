"""링커리어(linkareer.com) 인턴 공고 수집기.

/list/intern 페이지에 서버가 넣어주는 __NEXT_DATA__ (Apollo 캐시)를 읽는다.
robots.txt: /list/ 허용 (2026-11-22 확인). 요청 사이 2초 쉰다.
"""
from __future__ import annotations

import json
import re
import time as _time
from datetime import datetime, timedelta, timezone

import httpx

from yc.models import Event, make_id

LIST_URL = "https://linkareer.com/list/intern?page={page}"
PAGES = [1, 2, 3, 4, 5]
UA = "Mozilla/5.0 (yonsei-calendar; personal use; +https://github.com/jaebin06/yonsei-calendar)"
KST = timezone(timedelta(hours=9))
NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


def parse(html: str) -> list[Event]:
    m = NEXT_DATA.search(html)
    if not m:
        return []
    props = json.loads(m.group(1)).get("props", {}).get("pageProps", {})
    state = props.get("__APOLLO_STATE__", {})

    def deref(x):
        return state.get(x["__ref"], {}) if isinstance(x, dict) and "__ref" in x else (x or {})

    events = []
    for key, a in state.items():
        if not key.startswith("Activity:") or "INTERN" not in (a.get("jobTypes") or []):
            continue
        close = a.get("recruitCloseAt")
        if not close:
            continue  # 상시 채용은 마감일이 없어 캘린더에 넣지 않는다
        deadline = datetime.fromtimestamp(close / 1000, KST).replace(tzinfo=None, second=0, microsecond=0)
        cats = [deref(c).get("name", "") for c in a.get("categories") or []]
        cats = [c for c in cats if c and c != "전체"]
        intern_types = sorted({deref(i).get("name", "")
                               for r in a.get("recruitInformations") or []
                               for i in deref(r).get("internTypes") or []} - {""})
        regions = [r.get("name", "") for r in a.get("regions") or []]
        sidos = [deref(x).get("sido", "") for x in a.get("addresses") or []]
        wfh = any(deref(x).get("isPossibleWorkingFromHome") for x in a.get("addresses") or [])
        locs = sorted({s for s in sidos + regions if s})
        if wfh:
            locs.append("재택")
        events.append(Event(
            id=make_id("linkareer", a["id"]),
            category="internship",
            title=a.get("title", "").strip(),
            source="linkareer",
            url=f"https://linkareer.com/activity/{a['id']}",
            organizer=(a.get("organizationName") or "").strip(),
            deadline=deadline,
            tags=cats + intern_types,
            location=", ".join(f"오프라인({l})" if l not in ("재택",) else l for l in locs),
        ))
    return events


def collect(delay: float = 2.0) -> list[Event]:
    found: dict[str, Event] = {}
    with httpx.Client(headers={"User-Agent": UA}, timeout=20, follow_redirects=True) as client:
        for page in PAGES:
            resp = client.get(LIST_URL.format(page=page))
            resp.raise_for_status()
            evs = parse(resp.text)
            new = [e for e in evs if e.id not in found]
            for e in new:
                found[e.id] = e
            _time.sleep(delay)
            if not new:  # 페이지 파라미터가 무시되면 같은 목록이 반복된다
                break
    return list(found.values())
