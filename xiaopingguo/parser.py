from __future__ import annotations

import re
from typing import Any


def _clean_heading(text: str) -> str:
    text = text.strip()
    if text.startswith("**") and text.endswith("**") and len(text) >= 4:
        text = text[2:-2].strip()
    return text


def _slice_sections(raw: str, starts: list[tuple[str, int, int]]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for i, (key, start, body_start) in enumerate(starts):
        end = starts[i + 1][1] if i + 1 < len(starts) else len(raw)
        out.append((key, raw[start:end].strip()))
    return out


def parse_local_show(code: str, raw_text: str) -> dict[str, Any]:
    code = code.strip().upper()
    raw = raw_text or ""
    lines = raw.splitlines()

    series = ""
    title = ""
    full_name = ""

    # 优先从开头几十行中寻找“系列名P1：标题”这种格式。
    code_pattern = re.escape(code)
    title_re = re.compile(rf"^(.*?)\s*{code_pattern}\s*[：:]\s*(.+?)$", re.I)
    for line in lines[:30]:
        candidate = _clean_heading(line)
        if not candidate:
            continue
        m = title_re.match(candidate)
        if m:
            series = m.group(1).strip(" -—｜|")
            title = m.group(2).strip()
            full_name = candidate
            break

    if not full_name:
        # 找不到标准标题时，仍然保留编号，避免擅自猜。
        full_name = code

    tags: list[str] = []
    tag_match = re.search(r"(?mi)^\s*TAG\s*[：:]\s*(.+)$", raw)
    if tag_match:
        tag_line = tag_match.group(1).strip()
        hash_tags = [x.strip() for x in re.findall(r"#([^#\n]+)", tag_line) if x.strip()]
        if hash_tags:
            tags = hash_tags
        else:
            tags = [x.strip() for x in re.split(r"[、,，/]+", tag_line) if x.strip()]

    deadlines: dict[str, str] = {}
    deadline_patterns = {
        "first_form": r"(?mi)^\s*一表\s*[：:]\s*(.+)$",
        "second_form": r"(?mi)^\s*二表(?:\+公知)?\s*[：:]\s*(.+)$",
        "official_schedule": r"(?mi)^\s*正式日程(?:（[^）]*）)?\s*[：:]\s*(.+)$",
    }
    for key, pattern in deadline_patterns.items():
        m = re.search(pattern, raw)
        if m:
            deadlines[key] = m.group(1).strip()

    # D0 / D1 ... 日程原文切片。
    day_matches = list(re.finditer(r"(?mi)^\s*(D\d+)\s*$", raw))
    days: list[dict[str, str]] = []
    for i, m in enumerate(day_matches):
        start = m.start()
        end = day_matches[i + 1].start() if i + 1 < len(day_matches) else len(raw)
        section = raw[start:end]
        # 避免把后面的“一表/身份牌”整段吞进最后一天。
        stopper = re.search(r"(?m)^\s*[—-]{2,}\s*(?:一表|身份牌)\s*[—-]{2,}\s*$", section)
        if stopper:
            section = section[: stopper.start()]
        days.append({"day": m.group(1).upper(), "raw": section.strip()})

    # 身份牌：保存每张牌的原始段落，绝不靠 AI 重写原文。
    card_header_re = re.compile(r"(?m)^\s*(?:\*\*)?(\d{2})[｜|]\s*(.+?)(?:\*\*)?\s*$")
    card_matches = list(card_header_re.finditer(raw))
    identity_cards: list[dict[str, str]] = []
    for i, m in enumerate(card_matches):
        start = m.start()
        end = card_matches[i + 1].start() if i + 1 < len(card_matches) else len(raw)
        raw_section = raw[start:end].strip()
        number = m.group(1)
        header = m.group(2).strip().rstrip("*").strip()

        relationship = ""
        role_part = header
        if "｜" in header:
            role_part, relationship = [x.strip() for x in header.rsplit("｜", 1)]
        elif "|" in header:
            role_part, relationship = [x.strip() for x in header.rsplit("|", 1)]

        male_role = ""
        female_role = ""
        if "×" in role_part:
            left, right = [x.strip() for x in role_part.split("×", 1)]
            male_role, female_role = left, right

        quote = ""
        q = re.search(r"[“\"]([^”\"]+)[”\"]", raw_section)
        if q:
            quote = q.group(1).strip()

        identity_cards.append(
            {
                "number": number,
                "header": header,
                "male_role": male_role,
                "female_role": female_role,
                "relationship": relationship,
                "quote": quote,
                "raw": raw_section,
            }
        )

    return {
        "code": code,
        "series": series,
        "title": title,
        "full_name": full_name,
        "tags": tags,
        "deadlines": deadlines,
        "days": days,
        "identity_cards": identity_cards,
    }
