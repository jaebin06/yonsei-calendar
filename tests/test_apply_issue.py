import pytest

from scripts.apply_issue import apply, parse_form


def test_star_then_hide_moves_id():
    data = {}
    apply("star: devevent-3f9a1c2b", "", data)
    assert data["star"] == ["devevent-3f9a1c2b"]
    apply("hide: devevent-3f9a1c2b", "", data)
    assert data["star"] == [] and data["hide"] == ["devevent-3f9a1c2b"]
    apply("unhide: devevent-3f9a1c2b", "", data)
    assert data["hide"] == []


def test_rejects_bad_id():
    with pytest.raises(ValueError):
        apply("star: ../../etc", "", {})


def test_manual_form():
    body = "### 이름\n\n○○ AI 해커톤\n\n### 종류\n\n대회\n\n### 마감일\n\n2027-01-20 18:00\n\n### 링크\n\nhttps://example.com\n\n### 주최\n\n_No response_\n"
    assert parse_form(body)["주최"] == ""
    data = {}
    apply("[직접 추가] ○○ AI 해커톤", body, data)
    assert data["manual"][0] == {"title": "○○ AI 해커톤", "category": "contest",
                                 "deadline": "2027-01-20T18:00", "url": "https://example.com"}
