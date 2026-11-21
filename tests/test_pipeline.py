from datetime import date, datetime
from pathlib import Path

import yaml
from icalendar import Calendar

from yc import build, ics, score
from yc.collectors import devevent
from yc.models import Event

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests/fixtures/devevent_sample.md"
CFG = yaml.safe_load((ROOT / "config/profile.yaml").read_text(encoding="utf-8"))
EXAM = [(date(2026, 12, 15), date(2026, 12, 21), "학기말 시험")]


SAMPLE = """
## `26년 12월`
- __[테스트 AI 해커톤](https://example.com/a)__
  - 분류: `오프라인(서울 마포구)`, `무료`, `대회`, `AI`
  - 주최: 창업진흥원
  - 접수: 11. 30(월) ~ 12. 10(목) 18:00
- __[연말 밋업](https://example.com/b)__
  - 분류: `오프라인(부산)`, `무료`, `모임`, `기술일반`
  - 주최: 커뮤니티
  - 일시: 12. 20(일) 14:00 ~ 12. 20(일) 17:00

## `27년 1월`
- __[신년 컨퍼런스](https://example.com/c)__
  - 분류: `온라인`, `무료`, `세미나`, `AI`
  - 주최: 누군가
  - 접수: 12. 28(월) ~ 1. 05(화)
"""


def test_parse_sample_fields():
    evs = devevent.parse(SAMPLE)
    assert [e.title for e in evs] == ["테스트 AI 해커톤", "연말 밋업", "신년 컨퍼런스"]
    a, b, c = evs
    assert a.category == "contest" and b.category == "event"
    assert a.deadline == datetime(2026, 12, 10, 18, 0)
    assert a.apply_start == date(2026, 11, 30)
    assert b.deadline is None and b.event_start == datetime(2026, 12, 20, 14, 0)
    # 1월 헤더 아래의 12월 날짜는 전년도
    assert c.apply_start == date(2026, 12, 28)
    assert c.deadline == datetime(2027, 1, 5, 23, 59)


def test_parse_real_readme_has_dates():
    evs = devevent.parse(FIXTURE.read_text(encoding="utf-8"))
    assert len(evs) > 50
    assert all(e.key_date() for e in evs)
    assert len({e.id for e in evs}) == len(evs)


def test_scoring_rules():
    a, b, _ = devevent.parse(SAMPLE)
    today = date(2026, 11, 21)
    score.score_contest(a, CFG, EXAM, today)
    assert a.status == "recommended" and a.score >= 60
    score.score_contest(b, CFG, EXAM, today)
    assert b.status == "hidden" and "지역" in b.score_reasons[0]


def test_exam_conflict_lowers_score():
    ev = Event(id="x", category="contest", title="AI 해커톤", source="t",
               deadline=datetime(2026, 12, 16, 23, 59), location="온라인")
    score.score_contest(ev, CFG, EXAM, date(2026, 11, 21))
    assert ev.warnings and "학기말 시험" in ev.warnings[0]


def test_deadline_passed_hidden():
    ev = Event(id="y", category="contest", title="AI 해커톤", source="t",
               deadline=datetime(2026, 11, 22, 10, 0), location="온라인")
    score.score_contest(ev, CFG, EXAM, date(2026, 11, 21))
    assert ev.status == "hidden"


def test_ics_deadline_feed():
    ev = Event(id="z", category="contest", title="AI 해커톤", source="t",
               deadline=datetime(2027, 1, 20, 23, 59), event_start=datetime(2027, 2, 7, 10, 0),
               score=80, status="recommended")
    body = ics.build_deadline_feed("대회", [ev], datetime(2026, 11, 21, 6, 0, tzinfo=ics.KST))
    cal = Calendar.from_ical(body)
    summaries = sorted(str(c["summary"]) for c in cal.walk("VEVENT"))
    assert summaries == ["[D-7] AI 해커톤", "[마감] AI 해커톤", "[본선] AI 해커톤"]
    uids = [str(c["uid"]) for c in cal.walk("VEVENT")]
    assert len(set(uids)) == 3


def test_full_build(tmp_path, monkeypatch):
    # 상태 파일을 임시 폴더로 돌려서 저장소의 data/events.json을 건드리지 않는다
    monkeypatch.setattr(build, "ROOT", ROOT)
    state = ROOT / "data/events.json"
    backup = state.read_bytes() if state.exists() else None
    try:
        res = build.run(fixture=FIXTURE, out=tmp_path / "public",
                        now=datetime(2026, 11, 21, 6, 0, tzinfo=build.KST))
        assert res["health"]["dev-event"]["ok"]
        for name in ("academic", "exams", "contests", "internships"):
            Calendar.from_ical((tmp_path / f"public/feeds/{name}.ics").read_bytes())
        assert (tmp_path / "public/events.json").exists()
    finally:
        if backup is None:
            state.unlink(missing_ok=True)
        else:
            state.write_bytes(backup)


def test_missing_date_with_keyword_goes_to_review():
    ev = Event(id="m", category="contest", title="「AI 리터러시」 학습 경험 공모전", source="yonsei-notice")
    score.score_contest(ev, CFG, EXAM, date(2026, 11, 21))
    assert ev.status == "maybe" and "마감일 확인 필요" in ev.warnings


def test_generic_idea_contest_not_auto_added():
    ev = Event(id="g", category="contest", title="2026 수목원 제도개선 아이디어 공모", source="wevity",
               organizer="한국수목원정원관리원", tags=["기획/아이디어"], deadline=datetime(2026, 12, 1, 23, 59))
    score.score_contest(ev, CFG, EXAM, date(2026, 11, 21))
    assert ev.status == "maybe"
