from pathlib import Path
import tempfile

from xiaopingguo.db import Database
from xiaopingguo.parser import parse_local_show


SAMPLE = """**离开伊甸以后P1：我用什么把你留住**

TAG：#BGB普恋#电竞#再见爱人

——日程——
一表：10.3截
二表+公知：10.10
正式日程（含d0）：10.11-10.16

D0
第一天
心动信：限20

D1
第二天

——身份牌——
01｜脱节的战队核心选手（男） × 电竞纪录片导演（女）｜夫妻/矛盾期
“因为享受着它的灿烂，因为忍受着它的腐烂。”
这是01的正文。

02｜教练转型锐评主播（男） × 顶流赛事解说（女）｜多年地下恋/刚分手
“在她温柔眼眸的你是什么。”
这是02的正文。
"""


def test_local_parser():
    data = parse_local_show("P1", SAMPLE)
    assert data["series"] == "离开伊甸以后"
    assert data["title"] == "我用什么把你留住"
    assert data["tags"] == ["BGB普恋", "电竞", "再见爱人"]
    assert data["deadlines"]["first_form"] == "10.3截"
    assert len(data["identity_cards"]) == 2
    assert data["identity_cards"][0]["number"] == "01"
    assert "这是01的正文" in data["identity_cards"][0]["raw"]


def test_database_upsert_and_draft():
    with tempfile.TemporaryDirectory() as td:
        db = Database(f"sqlite:///{Path(td) / 'test.db'}")
        db.create_all()
        db.claim_admin("admin")
        db.set_main_group("group1")
        assert db.is_admin("admin")
        assert db.get_main_group() == "group1"

        db.start_draft("admin", "P1")
        assert db.append_draft_chunk("admin", "第一段") == 1
        assert db.append_draft_chunk("admin", "第二段") == 2
        code, chunks = db.draft_payload("admin")
        assert code == "P1"
        assert chunks == ["第一段", "第二段"]

        structured = parse_local_show("P1", SAMPLE)
        first = db.upsert_show(code="P1", structured=structured, raw_text=SAMPLE, raw_chunks=[SAMPLE])
        assert first.version == 1
        second = db.upsert_show(code="P1", structured=structured, raw_text=SAMPLE + "\n新版", raw_chunks=[SAMPLE, "新版"])
        assert second.version == 2
        assert db.get_show_by_code("P1").version == 2
