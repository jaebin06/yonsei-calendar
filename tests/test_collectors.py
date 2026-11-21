from datetime import date, datetime
from pathlib import Path

from yc.build import dedupe
from yc.collectors import wevity, yonsei
from yc.models import Event

RAW = Path(__file__).resolve().parent / "fixtures/raw"


def read(name):
    return (RAW / f"{name}.html").read_text(encoding="utf-8")


def test_wevity_list():
    evs = wevity.parse(read("wevity_it"), date(2026, 11, 21))
    assert len(evs) >= 8
    first = evs[0]
    assert first.title == "VIVID RE:PLAY 6개 IP로 만드는 AI영상 공모전"  # 배지 글자 제거
    assert first.deadline == datetime(2026, 12, 13, 23, 59)        # D-22
    assert first.organizer == "(주)아캐인"
    assert "웹/모바일/IT" in first.tags
    assert len({e.id for e in evs}) == len(evs)


def test_yonsei_list_and_categories():
    rows = yonsei.parse_list(read("yonsei_moji_list"))
    assert len(rows) == 10
    assert rows[0]["posted"] == date(2026, 11, 12)
    assert yonsei._category("제2회 연세 국제 창작 공모전") == "contest"
    assert yonsei._category("2027년도 장학생 모집") is None


def test_yonsei_article_dates():
    a = yonsei.parse_article(read("yonsei_art_contest"), "AI 벤처창업경진대회 (~11/10.화.마감)", date(2026, 10, 23))
    assert a["deadline"] == datetime(2026, 11, 10, 23, 59) and a["date_source"] == "본문"
    assert a["organizer"] == "창업지원단" and a["graduate_only"]
    b = yonsei.parse_article(read("yonsei_art_scholar"), "장학생 모집(~7/13)", date(2026, 6, 25))
    assert b["deadline"].date() == date(2026, 7, 13) and b["date_source"] == "기간"
    c = yonsei.parse_article(read("yonsei_art_poem"), "제25회 윤동주 시문학상", date(2025, 11, 4))
    assert c["deadline"].date() == date(2025, 12, 12)  # '11. 10.(월) ~ 12. 12.(금)' 의 끝


def test_dedupe_contains():
    a = Event(id="a", category="contest", title="2026 서울관광 프롬프톤", source="wevity",
              deadline=datetime(2026, 11, 29, 23, 59))
    b = Event(id="b", category="contest", title="2026 서울관광 프롬프톤 (Seoul Tourism Prompt-thon)",
              source="dev-event", deadline=datetime(2026, 11, 29, 23, 59), organizer="서울관광재단",
              location="오프라인(서울 종로구)")
    out = dedupe([a, b])
    assert [e.id for e in out] == ["b"]


def test_linkareer_interns():
    from yc.collectors import linkareer
    evs = linkareer.parse(read("linkareer_intern"))
    assert len(evs) >= 15
    kb = next(e for e in evs if "AI Native 인증 서비스 기획자" in e.title)
    assert kb.organizer == "카카오뱅크"
    assert kb.deadline == datetime(2026, 12, 7, 23, 59)
    assert "서비스기획/운영" in kb.tags and "오프라인(경기)" in kb.location
    p2 = {e.id for e in linkareer.parse(read("linkareer_intern_p2"))}
    assert p2 - {e.id for e in evs}  # page 파라미터가 다른 목록을 준다


def test_short_acronym_word_boundary():
    from yc.score import _has_any
    assert _has_any("Poultry and VPH marketing Intern", ["PM"]) == []
    assert _has_any("서비스 PM 인턴", ["PM"]) == ["PM"]
    assert _has_any("AI영상 공모전", ["AI"]) == ["AI"]
