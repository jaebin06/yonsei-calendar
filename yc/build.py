"""전체 파이프라인: 수집 → 병합 → 점수 → 피드·대시보드 데이터.

    python -m yc.build                 # 수집부터 전부
    python -m yc.build --offline       # 수집 없이 저장된 events.json으로 다시 빌드
    python -m yc.build --fixture PATH  # Dev-Event README 파일로 테스트
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from yc import ics, manual, score
from yc.collectors import COLLECTORS, devevent
from yc.models import Event, normalize_title

ROOT = Path(__file__).resolve().parent.parent
KST = timezone(timedelta(hours=9))


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_state(path: Path) -> dict[str, Event]:
    if not path.exists():
        return {}
    rows = json.loads(path.read_text(encoding="utf-8")).get("events", [])
    return {r["id"]: Event.model_validate(r) for r in rows}


def _richness(ev: Event) -> int:
    return sum(bool(x) for x in (ev.organizer, ev.url, ev.location, ev.prize, ev.apply_start, ev.event_start))


def dedupe(events: list[Event]) -> list[Event]:
    """같은 날짜에 제목이 같거나 한쪽이 다른 쪽을 포함하면 하나로. 정보가 많은 쪽을 남긴다.

    예: 위비티 '2026 서울관광 프롬프톤' = Dev-Event '2026 서울관광 프롬프톤 (Seoul Tourism Prompt-thon)'
    """
    kept: list[Event] = []
    for ev in sorted(events, key=_richness, reverse=True):
        nt = normalize_title(ev.title)
        dup = False
        for k in kept:
            if k.category == "internship" or ev.category == "internship":
                if k.category != ev.category:
                    continue
            if k.key_date() != ev.key_date():
                continue
            kt = normalize_title(k.title)
            short, long_ = sorted((nt, kt), key=len)
            if short == long_ or (len(short) >= 6 and short in long_):
                dup = True
                break
        if not dup:
            kept.append(ev)
    return kept


def collect(fixture: Path | None) -> tuple[list[Event], dict]:
    health: dict[str, dict] = {}
    found: list[Event] = []
    if fixture:
        evs = devevent.parse(fixture.read_text(encoding="utf-8"))
        health["dev-event"] = {"ok": True, "count": len(evs), "note": "fixture"}
        return evs, health
    for name, fn in COLLECTORS.items():
        try:
            evs = fn()
            health[name] = {"ok": len(evs) > 0, "count": len(evs)}
            found.extend(evs)
        except Exception as exc:  # 한 소스가 깨져도 나머지는 계속
            health[name] = {"ok": False, "count": 0, "error": f"{type(exc).__name__}: {exc}"}
    return found, health


def run(offline: bool = False, fixture: Path | None = None, out: Path | None = None,
        now: datetime | None = None) -> dict:
    now = now or datetime.now(KST)
    today = now.date()
    out = out or ROOT / "public"
    cfg = load_yaml(ROOT / "config/profile.yaml")
    overrides = load_yaml(ROOT / "data/overrides.yaml")
    state_path = ROOT / "data/events.json"
    state = load_state(state_path)

    academic = manual.load_dated(ROOT / "data/manual/academic.yaml", "academic", "yonsei")
    exams = manual.load_dated(ROOT / "data/manual/exams.yaml", "exam", "manual-exam")

    if offline:
        scraped = [e for e in state.values() if e.source not in ("yonsei", "manual-exam", "manual")]
        health = {"offline": {"ok": True, "count": len(scraped)}}
    else:
        scraped, health = collect(fixture)
        # 소스가 실패하면 그 소스의 기존 데이터를 유지해서 캘린더에서 사라지지 않게 한다
        for name, h in health.items():
            if not h["ok"]:
                scraped.extend(e for e in state.values() if e.source == name)

    scraped = dedupe(scraped + manual.load_manual_entries(overrides.get("manual")))
    periods = score.exam_periods(academic)
    star, hide = set(overrides.get("star") or []), set(overrides.get("hide") or [])

    result: list[Event] = []
    for ev in scraped:
        prev = state.get(ev.id)
        ev.first_seen = prev.first_seen if prev and prev.first_seen else now.replace(tzinfo=None)
        if ev.source != "manual":
            if ev.category == "internship":
                score.score_internship(ev, cfg, today)
            else:
                score.score_contest(ev, cfg, periods, today)
        else:
            clash = score._conflict(ev, periods)
            if clash:
                ev.warnings.append(f"{clash} 기간과 겹침")
        if ev.id in star:
            ev.status = "starred"
        if ev.id in hide:
            ev.status = "hidden"
        result.append(ev)

    # 지난 지 30일이 넘은 대회는 상태 파일에서 정리
    cutoff = today - timedelta(days=30)
    result = [e for e in result if (e.key_date() or today) >= cutoff]
    result.sort(key=lambda e: (e.key_date() or today, -e.score))

    in_cal = lambda e: e.status in ("recommended", "starred")
    feeds = {
        "academic.ics": ics.build_period_feed("연세 학사", academic, now),
        "exams.ics": ics.build_period_feed("시험·자격증", exams, now),
        "contests.ics": ics.build_deadline_feed(
            "대회", [e for e in result if e.category in ("contest", "event") and in_cal(e)], now),
        "internships.ics": ics.build_deadline_feed(
            "인턴", [e for e in result if e.category == "internship" and in_cal(e)], now, label="인턴 마감"),
    }

    # 출력: public/ (Pages로 배포) + data/events.json (다음 실행의 상태)
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(ROOT / "site", out)
    (out / "feeds").mkdir(parents=True, exist_ok=True)
    for name, body in feeds.items():
        (out / "feeds" / name).write_bytes(body)

    payload = {
        "generated_at": now.isoformat(timespec="minutes"),
        "repo": cfg.get("repo", ""),
        "health": health,
        "events": [json.loads(e.model_dump_json()) for e in (academic + exams + result)],
    }
    text = json.dumps(payload, ensure_ascii=False, indent=1)
    (out / "events.json").write_text(text, encoding="utf-8")
    state_payload = dict(payload, events=[json.loads(e.model_dump_json()) for e in result])
    state_path.write_text(json.dumps(state_payload, ensure_ascii=False, indent=1), encoding="utf-8")

    summary = {k: sum(1 for e in result if e.status == k) for k in ("recommended", "starred", "maybe", "hidden")}
    print(f"[yc] {now:%Y-%m-%d %H:%M} 수집 {len(result)}건 · {summary} · health={health}")
    return {"health": health, "summary": summary}


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--offline", action="store_true")
    p.add_argument("--fixture", type=Path)
    p.add_argument("--out", type=Path)
    args = p.parse_args(argv)
    res = run(offline=args.offline, fixture=args.fixture, out=args.out)
    # 모든 소스가 0건이면 실패로 끝내서 GitHub Actions가 메일을 보내게 한다
    if not args.offline and not any(h["ok"] for h in res["health"].values()):
        print("[yc] 모든 소스 수집 실패", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
