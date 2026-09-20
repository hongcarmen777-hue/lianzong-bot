import pytest

from xiaopingguo.config import Settings
from xiaopingguo.db_http import CloudBaseHTTPDatabase


def test_production_config_cannot_silently_fallback_to_sqlite(monkeypatch):
    for k in [
        "TCB_ENV_ID", "CLOUDBASE_ENV_ID", "TCB_API_KEY", "CLOUDBASE_API_KEY", "CLOUDBASE_APIKEY",
        "DATABASE_URL", "MYSQL_HOST", "MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_DATABASE", "ALLOW_SQLITE_FALLBACK",
    ]:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("QQ_APP_ID", "a")
    monkeypatch.setenv("QQ_APP_SECRET", "b")
    monkeypatch.setenv("CLAIM_TOKEN", "c")
    s = Settings.from_env()
    with pytest.raises(RuntimeError, match="持久化数据库未配置"):
        s.validate()


def test_half_cloudbase_config_fails(monkeypatch):
    monkeypatch.setenv("QQ_APP_ID", "a")
    monkeypatch.setenv("QQ_APP_SECRET", "b")
    monkeypatch.setenv("CLAIM_TOKEN", "c")
    monkeypatch.setenv("TCB_ENV_ID", "env-x")
    monkeypatch.delenv("TCB_API_KEY", raising=False)
    monkeypatch.delenv("CLOUDBASE_API_KEY", raising=False)
    monkeypatch.delenv("CLOUDBASE_APIKEY", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    s = Settings.from_env()
    with pytest.raises(RuntimeError, match="必须同时配置"):
        s.validate()


class FakeCloudBaseDB(CloudBaseHTTPDatabase):
    def __init__(self):
        super().__init__("env-test", "key-test")
        self.tables = {
            "xp_settings": [], "xp_shows": [], "xp_admins": [], "xp_ingest_drafts": [], "xp_ai_history": [], "xp_applications": []
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
        if order == "updated_at.desc":
            rows.reverse()
        if limit is not None:
            rows = rows[:limit]
        if select != "*":
            cols = select.split(",")
            rows = [{c: r.get(c) for c in cols} for r in rows]
        return rows

    def _insert(self, table, data):
        self.tables[table].append(dict(data))

    def _update(self, table, data, filters):
        for row in self.tables[table]:
            if self._matches(row, filters):
                row.update(data)

    def _delete(self, table, filters):
        self.tables[table] = [r for r in self.tables[table] if not self._matches(r, filters)]


def test_cloudbase_probe_really_writes_and_reads():
    db = FakeCloudBaseDB()
    db.verify_connection()
    assert db.tables["xp_settings"] == []


def test_cloudbase_show_upsert_is_read_back_verified():
    db = FakeCloudBaseDB()
    saved = db.upsert_show(
        code="P2",
        structured={"series":"离开伊甸以后", "title":"驾鹤西去", "full_name":"离开伊甸以后P2：驾鹤西去", "tags":[], "deadlines":{}, "days":[], "identity_cards":[]},
        raw_text="完整原文",
        raw_chunks=["完整原文"],
    )
    assert saved.code == "P2"
    assert saved.raw_text == "完整原文"
    assert db.list_shows()[0].code == "P2"
