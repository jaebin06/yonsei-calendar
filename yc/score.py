"""하드 필터 + 0~100점 점수화 (기획안 5장)."""
from __future__ import annotations

from datetime import date
from typing import Iterable

from yc.models import Event


def exam_periods(academic: Iterable[Event]) -> list[tuple[date, date, str]]:
    periods = []
    for ev in academic:
        if "exam" in ev.tags and ev.event_start:
            end = (ev.event_end or ev.event_start).date()
            periods.append((ev.event_start.date(), end, ev.title))
    return periods


def _has_any(text: str, words: list[str]) -> list[str]:
    low = text.lower()
    return [w for w in words if w.lower() in low]


def _region_ok(ev: Event, regions: list[str]) -> bool:
    if not ev.location:
        return True  # 모르면 통과시키고 사람이 판단
    parts = [p.strip() for p in ev.location.split(",")]
    for p in parts:
        if p.startswith("온라인") or "재택" in p:
            return True
        if any(r in p for r in regions):
            return True
    return False


def _organizer_points(org: str, cfg: dict) -> tuple[int, str]:
    o = cfg["organizers"]
    if not org:
        return 3, "주최 정보 없음 +3"
    tokens = org.replace(",", " ").split()
    if _has_any(org, o["major"]) or any(t.endswith(tuple(o.get("major_suffix", []))) for t in tokens):
        return 15, "대기업·공공·대학 주최 +15"
    if _has_any(org, o["mid"]):
        return 8, "협회·커뮤니티 주최 +8"
    return 3, "기타 주최 +3"


def _conflict(ev: Event, periods) -> str | None:
    days = [d for d in (ev.key_date(), ev.event_start.date() if ev.event_start else None) if d]
    for d in days:
        for start, end, name in periods:
            if start <= d <= end:
                return name
    return None


def score_contest(ev: Event, cfg: dict, periods, today: date) -> Event:
    kw = cfg["keywords"]
    reasons: list[str] = []
    text = " ".join([ev.title, " ".join(ev.tags), ev.organizer])

    # ① 하드 필터
    kd = ev.key_date()
    if kd is None:
        return _hide(ev, "날짜 확인 필요")
    if (kd - today).days < cfg.get("min_days_left", 2):
        return _hide(ev, "마감 임박·지남")
    if not _region_ok(ev, cfg["regions"]):
        return _hide(ev, "허용 지역 아님")
    bad = _has_any(ev.title, kw["exclude"])
    if bad:
        return _hide(ev, f"제외 키워드({bad[0]})")

    # ② 점수
    score = 0
    core_title = _has_any(ev.title, kw["core"])
    core_any = _has_any(text, kw["core"])
    related = _has_any(text, kw["related"])
    if core_title:
        score += 40; reasons.append(f"제목에 '{core_title[0]}' +40")
    elif core_any:
        score += 25; reasons.append(f"태그·주최에 '{core_any[0]}' +25")
    elif related:
        score += 10; reasons.append(f"주변 키워드 '{related[0]}' +10")

    if ev.category == "contest":
        if _has_any(ev.title, ["해커톤", "hackathon", "개발", "챌린지", "challenge", "대회", "경진", "contest", "competition", "cup"]):
            score += 20; reasons.append("해커톤·개발 대회 +20")
        else:
            score += 14; reasons.append("공모전 +14")
    else:
        score += 6; reasons.append("세미나·모임 +6")

    pts, why = _organizer_points(ev.organizer, cfg)
    score += pts; reasons.append(why)

    if ev.prize or _has_any(ev.title, ["상금", "시상", "채용", "장학"]):
        score += 10; reasons.append("상금·혜택 +10")

    clash = _conflict(ev, periods)
    if clash:
        ev.warnings.append(f"{clash} 기간과 겹침")
        reasons.append(f"{clash}과 겹침 +0")
    else:
        score += 15; reasons.append("시험기간과 안 겹침 +15")

    ev.score = score
    ev.score_reasons = reasons
    ev.status = _grade(ev, score, cfg)
    return ev


def score_internship(ev: Event, cfg: dict, today: date) -> Event:
    ic = cfg["internship"]
    reasons: list[str] = []
    kd = ev.key_date()
    if kd is None:
        return _hide(ev, "날짜 확인 필요")
    if (kd - today).days < cfg.get("min_days_left", 2):
        return _hide(ev, "마감 임박·지남")
    if not _region_ok(ev, cfg["regions"]):
        return _hide(ev, "허용 지역 아님")
    if _has_any(ev.eligibility + " " + ev.title, ic["exclude"]):
        return _hide(ev, "지원 자격 불일치")

    score = 0
    if _has_any(ev.title, ic["roles_core"]):
        score += 40; reasons.append("PM·기획 직무 +40")
    elif _has_any(ev.title, ic["roles_related"]):
        score += 25; reasons.append("AI·데이터 직무 +25")
    else:
        score += 10; reasons.append("기타 직무 +10")

    if ev.work_start and ev.work_end and _in_vacation(ev.work_start, ev.work_end):
        score += 25; reasons.append("방학 중 근무 +25")
    elif ev.work_start is None:
        score += 10; reasons.append("근무 기간 미상 +10")

    pts, why = _organizer_points(ev.organizer, cfg)
    company_pts = {15: 20, 8: 12, 3: 5}[pts]  # 인턴은 회사 배점이 20점 만점
    score += company_pts; reasons.append(why.rsplit(" +", 1)[0] + f" +{company_pts}")
    if "재학" in ev.eligibility:
        score += 15; reasons.append("재학생 지원 가능 +15")

    ev.score = score
    ev.score_reasons = reasons
    ev.status = _grade(ev, score, cfg)
    return ev


def _in_vacation(start: date, end: date) -> bool:
    """여름(6/22~8/31)·겨울(12/22~2/28) 방학 안에 끝나는지."""
    def vac(d: date) -> bool:
        md = (d.month, d.day)
        return (6, 22) <= md <= (8, 31) or md >= (12, 22) or md <= (2, 28)
    return vac(start) and vac(end)


def _grade(ev: Event, score: int, cfg: dict) -> str:
    t = cfg["thresholds"]
    if ev.category == "event":  # 세미나·모임은 캘린더에 자동으로 넣지 않는다
        return "maybe" if score >= t["maybe"] else "hidden"
    if score >= t["recommended"]:
        return "recommended"
    return "maybe" if score >= t["maybe"] else "hidden"


def _hide(ev: Event, reason: str) -> Event:
    ev.status = "hidden"
    ev.score = 0
    ev.score_reasons = [f"제외: {reason}"]
    return ev
