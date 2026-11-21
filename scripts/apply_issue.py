"""GitHub 이슈 → data/overrides.yaml 반영 (issues.yml 워크플로에서 실행).

지원하는 이슈:
  제목 "star: <id>"   → 캘린더에 넣기
  제목 "hide: <id>"   → 숨기기
  제목 "unstar: <id>" / "unhide: <id>" → 되돌리기
  '직접 추가' 이슈 양식 → manual 목록에 추가
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
PATH = ROOT / "data/overrides.yaml"
ID_RE = re.compile(r"^[a-z0-9-]+-[0-9a-f]{8}$")


def parse_form(body: str) -> dict[str, str]:
    """이슈 양식 본문('### 라벨\\n\\n값')을 dict로."""
    fields, key = {}, None
    for line in body.splitlines():
        if line.startswith("### "):
            key = line[4:].strip()
            fields[key] = ""
        elif key is not None:
            fields[key] = (fields[key] + "\n" + line).strip()
    return {k: ("" if v == "_No response_" else v) for k, v in fields.items()}


def apply(title: str, body: str, data: dict) -> str:
    data.setdefault("star", [])
    data.setdefault("hide", [])
    data.setdefault("manual", [])
    m = re.match(r"^\s*(star|hide|unstar|unhide)\s*:\s*(\S+)\s*$", title)
    if m:
        action, eid = m.groups()
        if not ID_RE.match(eid):
            raise ValueError(f"잘못된 id: {eid}")
        for lst in ("star", "hide"):
            if eid in data[lst]:
                data[lst].remove(eid)
        if action in ("star", "hide"):
            data[action].append(eid)
        return f"{action} {eid}"

    if title.startswith("[직접 추가]"):
        f = parse_form(body)
        kind = {"대회": "contest", "인턴": "internship", "행사": "event"}.get(f.get("종류", ""), "contest")
        deadline = f.get("마감일", "").strip()
        if not re.match(r"^\d{4}-\d{2}-\d{2}( \d{1,2}:\d{2})?$", deadline):
            raise ValueError("마감일은 2027-01-20 또는 2027-01-20 18:00 형식이어야 해요")
        row = {"title": f.get("이름", "").strip() or title[len("[직접 추가]"):].strip(),
               "category": kind,
               "deadline": deadline.replace(" ", "T") if " " in deadline else deadline,
               "url": f.get("링크", "").strip(),
               "organizer": f.get("주최", "").strip()}
        data["manual"].append({k: v for k, v in row.items() if v})
        return f"manual {row['title']}"
    raise ValueError("처리할 수 없는 이슈 제목")


def main() -> int:
    title = os.environ.get("ISSUE_TITLE", "")
    body = os.environ.get("ISSUE_BODY", "")
    data = yaml.safe_load(PATH.read_text(encoding="utf-8")) or {}
    try:
        msg = apply(title, body, data)
    except ValueError as exc:
        print(f"error={exc}")
        Path(os.environ.get("GITHUB_OUTPUT", "/dev/null")).open("a").write(f"error={exc}\n")
        return 1
    header = "".join(l for l in PATH.read_text(encoding="utf-8").splitlines(True) if l.startswith("#"))
    PATH.write_text(header + yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    Path(os.environ.get("GITHUB_OUTPUT", "/dev/null")).open("a").write(f"message={msg}\n")
    print(msg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
