"""Tests for capabilities: filesystem and research."""

from pathlib import Path

from opencompute.capabilities.base import CapabilityContext
from opencompute.capabilities.filesystem import FilesystemCapability
from opencompute.capabilities.research import ResearchCapability

from conftest import FakeModel, fake_fetch, fake_search


def _ctx(tmp_path):
    ws = tmp_path / "ws"
    (ws / "output").mkdir(parents=True)
    return ws, CapabilityContext(workspace=ws, log=lambda *a: None, model=FakeModel())


def test_filesystem_write_and_read(tmp_path):
    ws, ctx = _ctx(tmp_path)
    cap = FilesystemCapability()
    out = cap.execute({"action": "write", "path": "output/a.md", "content": "# hi"}, ctx)
    assert out["status"] == "ok"
    assert (ws / "output" / "a.md").read_text() == "# hi"
    red = cap.execute({"action": "read", "path": "output/a.md"}, ctx)
    assert red["content"] == "# hi"


def test_filesystem_rejects_path_escape(tmp_path):
    ws, ctx = _ctx(tmp_path)
    cap = FilesystemCapability()
    out = cap.execute({"action": "write", "path": "../evil.md", "content": "x"}, ctx)
    assert out["status"] == "failed"


def test_research_produces_sourced_summary(tmp_path):
    ws, ctx = _ctx(tmp_path)
    cap = ResearchCapability(search_fn=fake_search, fetch_fn=fake_fetch)
    out = cap.execute({"query": "weather api", "instructions": "compare them"}, ctx)
    assert out["status"] == "ok"
    assert out["summary"]
    assert len(out["sources"]) >= 1


def test_research_requires_query(tmp_path):
    ws, ctx = _ctx(tmp_path)
    cap = ResearchCapability(search_fn=fake_search, fetch_fn=fake_fetch)
    out = cap.execute({}, ctx)
    assert out["status"] == "failed"
