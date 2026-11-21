"""손으로 관리하는 YAML(학사일정·시험·직접 추가)을 Event로 바꾼다."""
from __future__ import annotations

from datetime import date, datetime, time
from pathlib import Path

import yaml

from yc.models import Event, make_id


def _as_dt(value, end_of_day: bool = False) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, time(23, 59) if end_of_day else time(0, 0))
    return datetime.fromisoformat(str(value))


def load_dated(path: Path, category: str, source: str) -> list[Event]:
    """academic.yaml / exams.yaml: start(필수)·end(선택)를 가진 기간 일정."""
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    events = []
    for row in data.get("events") or []:
        start = _as_dt(row["start"])
        end = _as_dt(row.get("end", row["start"]), end_of_day=True)
        tags = [row["kind"]] if row.get("kind") else []
        events.append(Event(
            id=make_id(source, row["title"], start.date().isoformat()),
            category=category,
            title=row["title"],
            source=source,
            url=row.get("url", ""),
            event_start=start,
            event_end=end,
            tags=tags,
            status="always",
        ))
    return events


def load_manual_entries(rows: list[dict]) -> list[Event]:
    """overrides.yaml의 manual: 직접 추가한 대회·인턴."""
    events = []
    for row in rows or []:
        deadline = _as_dt(row["deadline"], end_of_day=True) if row.get("deadline") else None
        ev_start = _as_dt(row["event_start"]) if row.get("event_start") else None
        events.append(Event(
            id=make_id("manual", row["title"], str(row.get("deadline", ""))),
            category=row.get("category", "contest"),
            title=row["title"],
            source="manual",
            url=row.get("url", ""),
            organizer=row.get("organizer", ""),
            deadline=deadline,
            event_start=ev_start,
            location=row.get("location", ""),
            status="starred",
        ))
    return events
