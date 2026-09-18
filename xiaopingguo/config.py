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

    # 只用于第一次跑通。云容器重启/重新部署后可能丢失。
    return "sqlite:////tmp/xiaopingguo-v02.db"


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

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            qq_app_id=os.getenv("QQ_APP_ID", "").strip(),
            qq_app_secret=os.getenv("QQ_APP_SECRET", "").strip(),
            deepseek_api_key=os.getenv("DEEPSEEK_API_KEY", "").strip(),
            deepseek_model=os.getenv("DEEPSEEK_MODEL", "deepseek-flash").strip() or "deepseek-flash",
            claim_token=os.getenv("CLAIM_TOKEN", "").strip(),
            port=_int("PORT", 8080),
            database_url=_database_url(),
            ai_history_limit=_int("AI_HISTORY_LIMIT", 20, minimum=4),
        )

    def validate(self) -> None:
        missing: list[str] = []
        if not self.qq_app_id:
            missing.append("QQ_APP_ID")
        if not self.qq_app_secret:
            missing.append("QQ_APP_SECRET")
        if not self.claim_token:
            missing.append("CLAIM_TOKEN")
        if missing:
            raise RuntimeError("缺少环境变量：" + ", ".join(missing))
