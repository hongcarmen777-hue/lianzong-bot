from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading

import botpy

from xiaopingguo.ai import AIService
from xiaopingguo.bot import AppleBot
from xiaopingguo.commands import CommandRouter
from xiaopingguo.config import Settings
from xiaopingguo.db import Database


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in {"/", "/health", "/healthz"}:
            body = "xiaopingguo v0.2 ok\n".encode("utf-8")
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


def main():
    settings = Settings.from_env()
    settings.validate()

    db = Database(settings.database_url)
    db.create_all()

    ai = AIService(settings, db)
    router = CommandRouter(settings, db, ai)

    start_health_server(settings.port)

    intents = botpy.Intents(public_messages=True)
    client = AppleBot(intents=intents, router=router)
    client.run(appid=settings.qq_app_id, secret=settings.qq_app_secret)


if __name__ == "__main__":
    main()
