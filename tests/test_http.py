"""Tests for the HTTP capability using a local server (offline)."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from opencompute.capabilities.base import CapabilityContext
from opencompute.capabilities.http import HttpCapability


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/echo":
            body = b'{"hello": "world"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        self.send_response(201)
        self.end_headers()

    def log_message(self, *a):
        pass


def _server():
    srv = HTTPServer(("127.0.0.1", 0), _Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv, f"http://127.0.0.1:{srv.server_port}"


def _ctx(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir(parents=True)
    return CapabilityContext(workspace=ws, log=lambda *a: None)


def test_http_success(tmp_path):
    srv, base = _server()
    try:
        out = HttpCapability().execute({"method": "GET", "url": f"{base}/echo"}, _ctx(tmp_path))
        assert out["status"] == "ok"
        assert out["status_code"] == 200
        assert "hello" in out["text"]
    finally:
        srv.shutdown()


def test_http_post(tmp_path):
    srv, base = _server()
    try:
        out = HttpCapability().execute(
            {"method": "POST", "url": base, "json": {"a": 1}}, _ctx(tmp_path))
        assert out["status"] == "ok"
        assert out["status_code"] == 201
    finally:
        srv.shutdown()


def test_http_not_found(tmp_path):
    srv, base = _server()
    try:
        out = HttpCapability().execute({"method": "GET", "url": f"{base}/missing"}, _ctx(tmp_path))
        assert out["status"] == "failed"
        assert out.get("status_code") == 404
    finally:
        srv.shutdown()


def test_http_rejects_bad_input(tmp_path):
    cap = HttpCapability()
    ctx = _ctx(tmp_path)
    assert cap.execute({"method": "GET"}, ctx)["status"] == "failed"  # no url
    assert cap.execute({"method": "GET", "url": "file:///etc/passwd"}, ctx)["status"] == "failed"
    assert cap.execute({"method": "DELETE", "url": "http://x"}, ctx)["status"] == "failed"
