import asyncio
from pathlib import Path
import tempfile

from xiaopingguo.commands import CommandContext, CommandRouter
from xiaopingguo.config import Settings
from xiaopingguo.db import Database
from xiaopingguo.db_http import CloudBaseHTTPDatabase
from xiaopingguo.parser import parse_local_application


FORM = """昵称：阿北
性别：女
年龄：28
意向身份牌：03
想玩：女强男弱，但男方不能太废
雷点：无脑雌竞
补充：更喜欢事业线重一点。
"""


class FakeAI:
    async def parse_show(self, *, code, raw_text):
        return {"code": code, "title": "", "full_name": code, "tags": [], "deadlines": {}, "days": [], "identity_cards": []}

    async def parse_application(self, *, show_code, raw_text):
        data = parse_local_application(show_code, raw_text)
        data["tags"] = ["女强男弱", "事业线"]
        data["preferences"] = ["女强男弱", "事业线重"]
        data["boundaries"] = ["无脑雌竞"]
        data["summary"] = "偏好女强男弱和事业线。"
        return data

    async def reply(self, **kwargs):
        return "自然回复"


def settings():
    return Settings(
        qq_app_id="x",
        qq_app_secret="x",
        deepseek_api_key="x",
        deepseek_model="deepseek-chat",
        claim_token="token",
        port=8080,
        database_url="sqlite:///:memory:",
        ai_history_limit=12,
    )


def test_local_application_parser_keeps_common_fields():
    data = parse_local_application("P1", FORM)
    assert data["show_code"] == "P1"
    assert data["applicant_name"] == "阿北"
    assert data["gender"] == "女"
    assert data["age"] == "28"
    assert data["preferred_card"] == "03"
    assert len(data["fields"]) >= 5


def test_admin_can_ingest_application_in_private_chat():
    with tempfile.TemporaryDirectory() as td:
        db = Database(f"sqlite:///{Path(td) / 'test.db'}")
        db.create_all()
        db.claim_admin("admin")
        router = CommandRouter(settings(), db, FakeAI())

        r1 = asyncio.run(router.handle(CommandContext(user_openid="admin", raw_text="录入一表 P1")))
        assert "开始收 P1 的一表" in r1.text
        draft = db.get_draft("admin")
        assert draft.mode == "application"

        r2 = asyncio.run(router.handle(CommandContext(user_openid="admin", raw_text=FORM)))
        assert "收到一表第 1 段" in r2.text

        r3 = asyncio.run(router.handle(CommandContext(user_openid="admin", raw_text="录入完成")))
        assert "一表落库成功" in r3.text
        rows = db.list_applications("P1")
        assert len(rows) == 1
        assert rows[0].applicant_name == "阿北"
        assert rows[0].raw_text == FORM.strip()
        assert db.get_draft("admin") is None


def test_same_show_and_name_updates_application_version():
    with tempfile.TemporaryDirectory() as td:
        db = Database(f"sqlite:///{Path(td) / 'test.db'}")
        db.create_all()
        first = db.save_application(show_code="P1", structured=parse_local_application("P1", FORM), raw_text=FORM, raw_chunks=[FORM])
        second_text = FORM + "\n备注：新版"
        second = db.save_application(show_code="P1", structured=parse_local_application("P1", second_text), raw_text=second_text, raw_chunks=[second_text])
        assert first.id == second.id
        assert second.version == 2
        assert len(db.list_applications("P1")) == 1


class FakeCloudBaseDB(CloudBaseHTTPDatabase):
    def __init__(self):
        super().__init__("env-test", "key-test")
        self.next_id = 1
        self.tables = {
            "xp_settings": [], "xp_shows": [], "xp_admins": [], "xp_ingest_drafts": [],
            "xp_ai_history": [], "xp_applications": []
        }

    @staticmethod
    def _matches(row, filters):
        if not filters:
            return True
        for key, expr in filters.items():
            if not str(expr).startswith("eq."):
                raise AssertionError(expr)
            if str(row.get(key, "")) != str(expr)[3:]:
                return False
        return True

    def _query(self, table, *, filters=None, select="*", limit=None, order=None):
        rows = [dict(r) for r in self.tables[table] if self._matches(r, filters)]
        if order in {"id.desc", "updated_at.desc"}:
            rows.reverse()
        if limit is not None:
            rows = rows[:limit]
        if select != "*":
            cols = select.split(",")
            rows = [{c: r.get(c) for c in cols} for r in rows]
        return rows

    def _insert(self, table, data):
        row = dict(data)
        if table == "xp_applications" and "id" not in row:
            row["id"] = self.next_id
            self.next_id += 1
        self.tables[table].append(row)

    def _update(self, table, data, filters):
        for row in self.tables[table]:
            if self._matches(row, filters):
                row.update(data)

    def _delete(self, table, filters):
        self.tables[table] = [r for r in self.tables[table] if not self._matches(r, filters)]


def test_cloudbase_application_save_is_read_back_verified():
    db = FakeCloudBaseDB()
    structured = parse_local_application("P1", FORM)
    saved = db.save_application(show_code="P1", structured=structured, raw_text=FORM, raw_chunks=[FORM])
    assert saved.id == 1
    assert saved.show_code == "P1"
    assert saved.applicant_name == "阿北"
    assert db.get_application_by_id(1).raw_text == FORM
