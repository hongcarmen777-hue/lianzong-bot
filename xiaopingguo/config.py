\
from dataclasses import dataclass
import os


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on", "y"}


@dataclass(frozen=True)
class Settings:
    qq_app_id: str
    qq_app_secret: str
    deepseek_api_key: str
    deepseek_model: str
    claim_token: str
    port: int
    database_url: str
    enable_ai_chat: bool
    ai_history_limit: int

    @classmethod
    def from_env(cls) -> "Settings":
        database_url = os.getenv("DATABASE_URL", "").strip()
        if not database_url:
            # 仅用于第一版快速跑通。云容器重启后本地文件可能丢失。
            database_url = "sqlite:////tmp/xiaopingguo.db"

        return cls(
            qq_app_id=os.getenv("QQ_APP_ID", "").strip(),
            qq_app_secret=os.getenv("QQ_APP_SECRET", "").strip(),
            deepseek_api_key=os.getenv("DEEPSEEK_API_KEY", "").strip(),
            deepseek_model=os.getenv("DEEPSEEK_MODEL", "deepseek-flash").strip(),
            claim_token=os.getenv("CLAIM_TOKEN", "").strip(),
            port=int(os.getenv("PORT", "8080")),
            database_url=database_url,
            enable_ai_chat=_bool("ENABLE_AI_CHAT", True),
            ai_history_limit=max(4, int(os.getenv("AI_HISTORY_LIMIT", "12"))),
        )

    def validate(self) -> None:
        missing = []
        if not self.qq_app_id:
            missing.append("QQ_APP_ID")
        if not self.qq_app_secret:
            missing.append("QQ_APP_SECRET")
        if not self.claim_token:
            missing.append("CLAIM_TOKEN")
        if missing:
            raise RuntimeError("缺少环境变量：" + ", ".join(missing))
