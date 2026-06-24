from __future__ import annotations

import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Tuple
from urllib.parse import parse_qs, urlparse

from trade_bot.config import load_config
from trade_bot.dashboard import build_dashboard_payload
from trade_bot.modes import available_modes, mode_for_config, resolve_mode_or_config


STATIC_DIR = Path(__file__).resolve().parent / "web_static"


class TradeBotRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, config_path: str, **kwargs):
        self._config_path = config_path
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/health":
            self._send_json({"ok": True})
            return
        if parsed.path == "/api/modes":
            default_mode = "demo"
            try:
                default_mode = mode_for_config(load_config(self._config_path))
            except Exception:
                default_mode = "demo"
            self._send_json(
                {
                    "modes": available_modes(),
                    "default_mode": default_mode,
                    "default_config": self._config_path,
                }
            )
            return
        if parsed.path == "/api/dashboard":
            params = parse_qs(parsed.query)
            requested_mode = params.get("mode", [None])[0]
            requested_config = params.get("config", [self._config_path])[0]
            try:
                resolved_config = resolve_mode_or_config(requested_mode, requested_config)
                self._send_json(build_dashboard_payload(resolved_config))
            except Exception as error:
                self._send_json({"error": str(error)}, status=500)
            return
        if parsed.path == "/":
            self.path = "/index.html"
        return super().do_GET()

    def log_message(self, format: str, *args) -> None:
        print(f"[web] {self.address_string()} - {format % args}")

    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def _make_handler(config_path: str):
    def handler(*args, **kwargs):
        return TradeBotRequestHandler(*args, config_path=config_path, **kwargs)

    return handler


def run_server(host: str, port: int, config_path: str) -> int:
    server_address: Tuple[str, int] = (host, port)
    httpd = ThreadingHTTPServer(server_address, _make_handler(config_path))
    print(f"Trade Bot web dashboard running at http://{host}:{port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down Trade Bot web dashboard")
    finally:
        httpd.server_close()
    return 0
