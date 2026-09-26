#!/usr/bin/env python3
"""HTTP API for the item checker (public via Cloudflare Tunnel).

POST /api/check  {"text": "..."}  -> checks
GET  /api/health                  -> {"ok": true, "ai": bool}

Guard rails (the service is public and runs on a home machine):
- body ≤ 16 KB, text ≤ 8,000 chars, ≤ 10 items per request
- per client: 6 requests / 10 min and 40 / day (client = CF-Connecting-IP)
- at most 3 requests in flight; the model runs one item at a time
- model output is enum-only (see luna.py); nothing it writes is echoed
- paid-model spend is capped per month and per day (see budget.py)
- the pasted text is never stored or logged; only counts are logged
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(__file__))
import engine  # noqa: E402
import budget  # noqa: E402
import luna  # noqa: E402

HOST, PORT = "127.0.0.1", int(os.environ.get("CHECKER_PORT", "8961"))
ORIGINS = set(filter(None, os.environ.get("CHECKER_ORIGINS", "https://haeminway.com,https://www.haeminway.com,http://localhost:4321").split(",")))
MAX_BODY, MAX_TEXT = 16_000, 8_000
WINDOW, WINDOW_MAX, DAY_MAX = 600, 6, 40
INFLIGHT = threading.BoundedSemaphore(3)
hits: dict[str, deque] = defaultdict(deque)
hits_lock = threading.Lock()
stats = {"requests": 0, "rejected": 0, "items": 0}


def limited(ip: str) -> str | None:
    now = time.time()
    with hits_lock:
        q = hits[ip]
        while q and now - q[0] > 86_400:
            q.popleft()
        recent = sum(1 for t in q if now - t < WINDOW)
        if recent >= WINDOW_MAX:
            return "잠시 후 다시 시도해 주세요. (10분에 6번까지)"
        if len(q) >= DAY_MAX:
            return "오늘 검사 횟수를 다 썼습니다. 내일 다시 이용해 주세요."
        q.append(now)
    return None


class Handler(BaseHTTPRequestHandler):
    server_version = "checker"
    sys_version = ""

    def _cors(self):
        origin = self.headers.get("Origin", "")
        if origin in ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Max-Age", "600")

    def _send(self, code: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # never log request lines (no text, no IPs on disk)
        pass

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        if self.path == "/api/health":
            b = budget.state()
            return self._send(200, {"ok": True, "ai": luna.available(), "month_usd": round(b["month_usd"], 3), "month_cap": b["month_cap"]})
        self._send(404, {"error": "not found"})

    def do_POST(self):
        stats["requests"] += 1
        if self.path != "/api/check":
            return self._send(404, {"error": "not found"})
        origin = self.headers.get("Origin", "")
        if origin and origin not in ORIGINS:
            stats["rejected"] += 1
            return self._send(403, {"error": "허용되지 않은 출처입니다."})
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_BODY:
            stats["rejected"] += 1
            return self._send(413, {"error": "입력이 너무 깁니다. 한 번에 문제 10개, 8,000자까지 넣을 수 있습니다."})
        ip = self.headers.get("CF-Connecting-IP") or self.client_address[0]
        msg = limited(ip)
        if msg:
            stats["rejected"] += 1
            return self._send(429, {"error": msg})
        try:
            text = json.loads(self.rfile.read(length)).get("text", "")
        except Exception:
            return self._send(400, {"error": "형식이 올바르지 않습니다."})
        if not isinstance(text, str) or not text.strip():
            return self._send(400, {"error": "문제를 붙여 넣어 주세요."})
        text = "".join(ch for ch in text if ch == "\n" or ch == "\t" or ch >= " ")[:MAX_TEXT]
        if not INFLIGHT.acquire(timeout=5):
            stats["rejected"] += 1
            return self._send(503, {"error": "지금 검사가 몰려 있습니다. 잠시 후 다시 시도해 주세요."})
        try:
            use_ai = luna.available()
            result = engine.run(text, luna if use_ai else None)
            result["ai"] = use_ai
            stats["items"] += len(result["items"])
            self._send(200, result)
        except Exception:
            self._send(500, {"error": "검사 중 문제가 생겼습니다."})
        finally:
            INFLIGHT.release()


def main():
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    srv.daemon_threads = True
    print(f"checker on http://{HOST}:{PORT}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
