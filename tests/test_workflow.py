"""Full fake offline workflow: planner -> research -> research(uses prior) ->
http -> filesystem -> verifier."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from opencompute.capabilities.filesystem import FilesystemCapability
from opencompute.capabilities.http import HttpCapability
from opencompute.capabilities.research import ResearchCapability
from opencompute.core.database import Database
from opencompute.core.models import ModelResult
from opencompute.core.runtime import Runtime

from conftest import GOOD_SUMMARY, fake_fetch, fake_search


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"pong"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def _http_server():
    srv = HTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_port}"


def _workflow_plan(url: str) -> str:
    plan = {
        "steps": [
            {"capability": "research", "input": {"query": "open source projects", "instructions": "gather"},
             "purpose": "gather"},
            {"capability": "research", "input": {"query": "compare", "instructions": "write report", "findings": "$research"},
             "purpose": "write report"},
            {"capability": "http", "input": {"method": "GET", "url": url}, "purpose": "check a service"},
            {"capability": "filesystem", "input": {"action": "write", "path": "output/comparison.md", "content": "$research"},
             "purpose": "save"},
        ],
        "notes": "workflow",
    }
    return json.dumps(plan)


class _Model:
    default_model = "m"

    def __init__(self, plan_json):
        self.plan_json = plan_json

    def complete(self, messages, model=None):
        if any(m.get("role") == "system" for m in messages):
            return ModelResult(self.plan_json, cost_status="unknown")
        if "Instructions:" in messages[-1]["content"]:
            return ModelResult(GOOD_SUMMARY, cost_status="unknown")
        return ModelResult("ok", cost_status="unknown")


def test_full_workflow_with_http(tmp_path):
    srv, base = _http_server()
    try:
        ws = tmp_path / "ws"
        ws.mkdir()
        db = Database(ws / "state" / "events.db")
        caps = {
            "filesystem": FilesystemCapability(),
            "research": ResearchCapability(search_fn=fake_search, fetch_fn=fake_fetch),
            "http": HttpCapability(),
        }
        rt = Runtime(model=_Model(_workflow_plan(base)), capabilities=caps,
                     workspace=ws, db=db)
        task = rt.run("full workflow")

        kinds = [e.kind for e in db.events_for(task.id)]
        db.close()

        assert task.status == "succeeded"
        assert "http" in kinds or "capability" in kinds
        report = ws / "output" / "comparison.md"
        assert report.exists()
        assert "## References" in report.read_text()
    finally:
        srv.shutdown()
