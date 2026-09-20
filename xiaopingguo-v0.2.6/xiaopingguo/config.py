from __future__ import annotations

from dataclasses import dataclass
import os
from urllib.parse import quote_plus


def _int(name: str, default: int, minimum: int = 1) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return max(minimum, int(raw))
    except ValueError:
        return default


def _database_url() -> str:
    direct = os.getenv("DATABASE_URL", "").strip()
    if direct:
        return direct

    host = os.getenv("MYSQL_HOST", "").strip()
    user = os.getenv("MYSQL_USER", "").strip()
    password = os.getenv("MYSQL_PASSWORD", "")
    database = os.getenv("MYSQL_DATABASE", "").strip()
    port = os.getenv("MYSQL_PORT", "3306").strip() or "3306"

    if host and user and database:
        return (
            "mysql+pymysql://"
            f"{quote_plus(user)}:{quote_plus(password)}@{host}:{port}/{quote_plus(database)}"
            "?charset=utf8mb4"
        )

    return ""


def _first_env(*names: str) -> str:
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return ""


@dataclass(frozen=True)
class Settings:
    qq_app_id: str
    qq_app_secret: str
    deepseek_api_key: str
    deepseek_model: str
    claim_token: str
    port: int
    database_url: str
    ai_history_limit: int
    cloudbase_env_id: str = ""
    cloudbase_api_key: str = ""
    allow_sqlite_fallback: bool = False

    @property
    def use_cloudbase_http_db(self) -> bool:
        return bool(self.cloudbase_env_id and self.cloudbase_api_key)

    @classmethod
    def from_env(cls) -> "Settings":
        model = os.getenv("DEEPSEEK_MODEL", "deepseek-flash").strip() or "deepseek-flash"
        # DeepSeek V4.1 Flash uses the stable API model id `deepseek-flash`.
        # Legacy `deepseek-v4-flash` is still accepted upstream, so leave any
        # explicitly configured legacy value untouched instead of rewriting it.

        return cls(
            qq_app_id=os.getenv("QQ_APP_ID", "").strip(),
            qq_app_secret=os.getenv("QQ_APP_SECRET", "").strip(),
            deepseek_api_key=os.getenv("DEEPSEEK_API_KEY", "").strip(),
            deepseek_model=model,
            claim_token=os.getenv("CLAIM_TOKEN", "").strip(),
            port=_int("PORT", 8080),
            database_url=_database_url(),
            ai_history_limit=_int("AI_HISTORY_LIMIT", 20, minimum=4),
            cloudbase_env_id=_first_env("TCB_ENV_ID", "CLOUDBASE_ENV_ID"),
            cloudbase_api_key=_first_env(
                "TCB_API_KEY", "CLOUDBASE_API_KEY", "CLOUDBASE_APIKEY"
            ),
            allow_sqlite_fallback=os.getenv("ALLOW_SQLITE_FALLBACK", "").strip().lower() in {"1", "true", "yes", "on"},
        )

    def validate(self) -> None:
        missing: list[str] = []
        if not self.qq_app_id:
            missing.append("QQ_APP_ID")
        if not self.qq_app_secret:
            missing.append("QQ_APP_SECRET")
        if not self.claim_token:
            missing.append("CLAIM_TOKEN")
        if bool(self.cloudbase_env_id) != bool(self.cloudbase_api_key):
            missing.append("TCB_ENV_ID/TCB_API_KEY 必须同时配置")
        if not self.use_cloudbase_http_db and not self.database_url and not self.allow_sqlite_fallback:
            missing.append("持久化数据库未配置（需要 TCB_ENV_ID + TCB_API_KEY）")
        if missing:
            raise RuntimeError("配置错误：" + "；".join(missing))
