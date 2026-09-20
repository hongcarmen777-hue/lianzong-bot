import asyncio
from pathlib import Path
import tempfile

from xiaopingguo.commands import CommandContext, CommandRouter
from xiaopingguo.config import Settings
from xiaopingguo.db import Database
from xiaopingguo.parser import parse_local_show


SAMPLE = """离开伊甸以后P2：驾鹤西去\nTAG：#死亡#宿命\n——身份牌——\n01｜白鹤使 × 亡魂｜未了执念\n正文。\n"""


class FakeAI:
    def __init__(self):
        self.calls = []

    async def parse_show(self, *, code, raw_text):
        self.calls.append((code, raw_text))
        return parse_local_show(code, raw_text)

    async def reply(self, **kwargs):
        return "自然回复"


def settings():
    return Settings(
        qq_app_id="x",
        qq_app_secret="x",
        deepseek_api_key="x",
        deepseek_model="deepseek-v4-flash",
        claim_token="token",
        port=8080,
        database_url="sqlite:///:memory:",
        ai_history_limit=12,
    )


def test_admin_can_ingest_entire_show_in_private_chat():
    with tempfile.TemporaryDirectory() as td:
        db = Database(f"sqlite:///{Path(td) / 'test.db'}")
        db.create_all()
        db.claim_admin("admin")
        router = CommandRouter(settings(), db, FakeAI())

        r1 = asyncio.run(router.handle(CommandContext(user_openid="admin", raw_text="录入恋综 P2")))
        assert "开始收 P2" in r1.text
        assert "私聊" in r1.text

        r2 = asyncio.run(router.handle(CommandContext(user_openid="admin", raw_text=SAMPLE)))
        assert "收到第 1 段" in r2.text

        r3 = asyncio.run(router.handle(CommandContext(user_openid="admin", raw_text="录入完成")))
        assert "P2" in r3.text
        assert "共享档案库" in r3.text
        assert db.get_show_by_code("P2") is not None
        assert db.get_draft("admin") is None


def test_group_ingest_is_redirected_to_private_chat():
    with tempfile.TemporaryDirectory() as td:
        db = Database(f"sqlite:///{Path(td) / 'test.db'}")
        db.create_all()
        db.claim_admin("admin")
        db.set_main_group("group1")
        router = CommandRouter(settings(), db, FakeAI())

        r = asyncio.run(router.handle(CommandContext(
            user_openid="admin", group_openid="group1", raw_text="录入恋综 P2"
        )))
        assert "私聊" in r.text
        assert db.get_draft("admin") is None


def test_private_ingest_overwrites_and_increments_version():
    with tempfile.TemporaryDirectory() as td:
        db = Database(f"sqlite:///{Path(td) / 'test.db'}")
        db.create_all()
        db.claim_admin("admin")
        router = CommandRouter(settings(), db, FakeAI())

        for body in (SAMPLE, SAMPLE + "\n新版补充"):
            asyncio.run(router.handle(CommandContext(user_openid="admin", raw_text="录入恋综 P2")))
            asyncio.run(router.handle(CommandContext(user_openid="admin", raw_text=body)))
            asyncio.run(router.handle(CommandContext(user_openid="admin", raw_text="录入完成")))

        assert db.get_show_by_code("P2").version == 2
