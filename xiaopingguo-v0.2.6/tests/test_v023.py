from xiaopingguo.config import Settings


def test_current_deepseek_flash_id_is_kept(monkeypatch):
    monkeypatch.setenv("QQ_APP_ID", "a")
    monkeypatch.setenv("QQ_APP_SECRET", "b")
    monkeypatch.setenv("CLAIM_TOKEN", "c")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-flash")
    s = Settings.from_env()
    assert s.deepseek_model == "deepseek-flash"


def test_cloudbase_key_alias(monkeypatch):
    monkeypatch.setenv("QQ_APP_ID", "a")
    monkeypatch.setenv("QQ_APP_SECRET", "b")
    monkeypatch.setenv("CLAIM_TOKEN", "c")
    monkeypatch.setenv("TCB_ENV_ID", "env-test")
    monkeypatch.delenv("TCB_API_KEY", raising=False)
    monkeypatch.setenv("CLOUDBASE_APIKEY", "server-key")
    s = Settings.from_env()
    assert s.use_cloudbase_http_db
    assert s.cloudbase_api_key == "server-key"
