from datetime import date, datetime
from pathlib import Path

from yc.build import dedupe
from yc.collectors import wevity, yonsei
from yc.models import Event

RAW = Path(__file__).resolve().parent / "fixtures/frozen"  # 고정 샘플: probe 워크플로가 덮어쓰지 않는다


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


def test_dorm_list_and_dates():
    from yc.collectors import dorm
    rows = dorm.parse_list(read("dorm_notice"), "notice")
    assert any(r["category"] == "공통" for r in rows)
    r = next(r for r in rows if "방역" in r["title"])
    assert dorm.dates_from_title(r["title"], r["posted"]) == [date(2026, 11, 30)]
    assert not dorm.wanted("3학사", set()) and dorm.wanted("3학사", {"3학사"})
    ds, note = dorm.dates_from_article(read("dorm_art_winter"), date(2026, 10, 20))
    assert ds == [date(2026, 12, 26)] and "신규 입사" in note
    ev = dorm.build_event({"idx": "9168", "category": "공통", "title": "겨울방학 연장 신청 안내",
                           "url": "u", "posted": date(2026, 10, 20)}, ds, note)
    assert ev.category == "dorm" and "신규 입사" in ev.title
    postponed = dorm.dates_from_title("(일정연기)무악4학사 단수 공지(10.16금→10.30금)", date(2026, 10, 8))
    assert dorm.build_event({"idx": "1", "category": "4학사", "title": "→", "url": "u", "posted": None}, postponed).event_start.date() == date(2026, 10, 30)


def test_scholarship_parsing_and_scoring():
    import yaml
    from pathlib import Path
    from yc import score
    cfg = yaml.safe_load((Path(__file__).resolve().parents[1] / "config/profile.yaml").read_text(encoding="utf-8"))
    rows = yonsei.parse_list(read("yonsei_scholar_list"))
    kept = [r["title"] for r in rows if not yonsei.SCHOLAR_SKIP_RE.search(r["title"])]
    assert "2027년도 [19기] 에몬스 장학생 모집 안내" in kept
    assert not any("통학로" in t or "중복지원" in t or "아동돌봄" in t for t in kept)

    ulsan = yonsei.build_event({"title": "2026년도 상반기 울산연구원 장학생 선발 안내", "url": "u1", "posted": date(2026, 2, 25)},
                               read("yonsei_art_ulsan"), "scholarship")
    assert ulsan.deadline == datetime(2026, 4, 3, 18, 0)  # 머리의 '기간'(2/3)이 아니라 본문 신청기간 끝
    score.score_scholarship(ulsan, cfg, date(2026, 3, 1))
    assert ulsan.status == "recommended" and any("울산" in r for r in ulsan.score_reasons)

    nat = yonsei.build_event({"title": "2026년 1학기 국가장학금 1차 신청 안내", "url": "u2", "posted": date(2025, 11, 18)},
                             read("yonsei_art_national"), "scholarship")
    assert nat.deadline == datetime(2025, 12, 26, 18, 0)
    score.score_scholarship(nat, cfg, date(2025, 11, 20))
    assert nat.status == "recommended"

    grad = Event(id="g", category="scholarship", title="대학원생 연구장학금", source="t",
                 deadline=datetime(2026, 12, 20, 23, 59))
    assert score.score_scholarship(grad, cfg, date(2026, 11, 25)).status == "hidden"
    busan = Event(id="b", category="scholarship", title="부산 출신 대학생 장학금", source="t",
                  deadline=datetime(2026, 12, 20, 23, 59))
    assert score.score_scholarship(busan, cfg, date(2026, 11, 25)).status == "hidden"


def test_scholarship_negation_and_grade():
    import yaml
    from pathlib import Path
    from yc import score
    cfg = yaml.safe_load((Path(__file__).resolve().parents[1] / "config/profile.yaml").read_text(encoding="utf-8"))
    emons = Event(id="e", category="scholarship", title="에몬스 장학생 모집", source="t",
                  eligibility="2) 지원 자격 / ※ 2027년 2월 졸업 예정자, 2027년 신규 입학자, 대학원생(석사 ㆍ 박사 과정 및 수료자)은 지원 대상에서 제외됩니다.",
                  deadline=datetime(2027, 1, 8, 23, 59))
    assert score.score_scholarship(emons, cfg, date(2026, 11, 25)).status != "hidden"
    sea = Event(id="s", category="scholarship", title="세아해암장학생 추천", source="t",
                eligibility="가. 2027-1학기 기준 3학년 이과대학, 공과대학, 인공지능융합대학, 생명시스템대학 학부 재학생 / 다. 소득분위 8분위 이하인 학생")
    score.score_scholarship(sea, cfg, date(2026, 11, 25))
    assert sea.status == "recommended" and sea.score >= 65
    assert "마감일 확인 필요" in sea.warnings and "소득 기준 확인" in sea.warnings
