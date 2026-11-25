"""모든 소스가 공유하는 공통 일정 형식."""
from __future__ import annotations

import hashlib
import re
from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

Category = Literal["academic", "contest", "exam", "event", "internship", "dorm", "scholarship"]
Status = Literal["recommended", "maybe", "hidden", "starred", "always"]


def make_id(source: str, *parts: str) -> str:
    """소스 + 핵심 필드의 해시. 같은 일정은 매일 같은 id를 갖는다."""
    raw = "|".join([source, *[p or "" for p in parts]])
    return f"{source}-{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:8]}"


def normalize_title(title: str) -> str:
    """중복 판정용 제목: 공백·기호·연도 제거, 소문자."""
    t = re.sub(r"20\d\d", "", title.lower())
    return re.sub(r"[\s\W_]+", "", t)


class Event(BaseModel):
    id: str
    category: Category
    title: str
    source: str
    url: str = ""
    organizer: str = ""
    apply_start: Optional[date] = None
    deadline: Optional[datetime] = None  # KST, tz 정보 없이 저장
    event_start: Optional[datetime] = None
    event_end: Optional[datetime] = None
    tags: list[str] = Field(default_factory=list)
    eligibility: str = ""
    location: str = ""
    prize: str = ""
    work_start: Optional[date] = None
    work_end: Optional[date] = None
    score: int = 0
    score_reasons: list[str] = Field(default_factory=list)
    status: Status = "maybe"
    warnings: list[str] = Field(default_factory=list)
    ask: bool = False  # 점수가 높아서 참여 여부를 먼저 물어볼 대회
    first_seen: Optional[datetime] = None

    def key_date(self) -> Optional[date]:
        """캘린더와 필터가 기준으로 삼는 날짜: 마감 → 행사 시작."""
        if self.deadline:
            return self.deadline.date()
        if self.event_start:
            return self.event_start.date()
        return None
