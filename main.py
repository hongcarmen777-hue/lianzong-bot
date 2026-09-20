from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading

import botpy

from xiaopingguo.ai import AIService
from xiaopingguo.bot import AppleBot
from xiaopingguo.commands import CommandRouter
from xiaopingguo.config import Settings
from xiaopingguo.db import Database
from xiaopingguo.db_http import CloudBaseHTTPDatabase


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in {"/", "/health", "/healthz"}:
            body = "xiaopingguo v0.2.7 ok\n".encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt, *args):
        return


def start_health_server(port: int):
    server = ThreadingHTTPServer(("0.0.0.0", port), HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def build_database(settings: Settings):
    if settings.use_cloudbase_http_db:
        db = CloudBaseHTTPDatabase(settings.cloudbase_env_id, settings.cloudbase_api_key)
        db.create_all()
        db.verify_connection()
        print(f"[xiaopingguo] database backend: {db.backend_name} | env={settings.cloudbase_env_id}")
        return db

    if settings.database_url:
        db = Database(settings.database_url)
        db.create_all()
        db.verify_connection()
        print(f"[xiaopingguo] database backend: {db.backend_name}")
        return db

    if settings.allow_sqlite_fallback:
        db = Database("sqlite:////tmp/xiaopingguo-v026.db")
        db.create_all()
        db.verify_connection()
        print("[xiaopingguo] WARNING: SQLite fallback explicitly enabled")
        return db

    raise RuntimeError("未配置持久化数据库；v0.2.7 已禁止静默回退到 /tmp SQLite")


def main():
    settings = Settings.from_env()
    settings.validate()

    db = build_database(settings)
    ai = AIService(settings, db)
    router = CommandRouter(settings, db, ai)

    start_health_server(settings.port)

    intents = botpy.Intents(public_messages=True)
    client = AppleBot(intents=intents, router=router)
    client.run(appid=settings.qq_app_id, secret=settings.qq_app_secret)


if __name__ == "__main__":
    main()
