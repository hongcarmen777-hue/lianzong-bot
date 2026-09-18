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

import asyncio
import sys
import types

# 测试只验证路由，不实际调用 OpenAI SDK。
fake_openai = types.ModuleType("openai")
class DummyAsyncOpenAI:
    pass
fake_openai.AsyncOpenAI = DummyAsyncOpenAI
sys.modules.setdefault("openai", fake_openai)

from xiaopingguo.commands import CommandContext, CommandRouter
from xiaopingguo.config import Settings


class FakeAI:
    def __init__(self):
        self.calls = []

    async def reply(self, **kwargs):
        self.calls.append(kwargs)
        return "私聊自然回复"


def _settings():
    return Settings(
        qq_app_id="x",
        qq_app_secret="x",
        deepseek_api_key="x",
        deepseek_model="deepseek-flash",
        claim_token="token",
        port=8080,
        database_url="sqlite:///:memory:",
        ai_history_limit=12,
    )


def test_admin_private_fallback_and_capability_answer():
    with tempfile.TemporaryDirectory() as td:
        db = Database(f"sqlite:///{Path(td) / 'test.db'}")
        db.create_all()
        db.claim_admin("admin")
        ai = FakeAI()
        router = CommandRouter(_settings(), db, ai)

        r1 = asyncio.run(
            router.handle(
                CommandContext(user_openid="admin", raw_text="我能设置个后台群吗")
            )
        )
        assert "不能设置后台群" in r1.text
        assert not ai.calls

        r2 = asyncio.run(
            router.handle(CommandContext(user_openid="admin", raw_text="已经设置了"))
        )
        assert r2.text == "私聊自然回复"
        assert ai.calls[-1]["admin_private"] is True
