"""End-to-end tests for the runtime, including escalation."""

from opencompute.capabilities.filesystem import FilesystemCapability
from opencompute.capabilities.research import ResearchCapability
from opencompute.core.database import Database
from opencompute.core.runtime import Runtime

from conftest import EscalationFake, FakeModel, fake_fetch, fake_search


def _make_runtime(tmp_path, model, strong="fake-strong", cheap="fake-cheap"):
    ws = tmp_path / "workspace"
    ws.mkdir()
    db = Database(ws / "state" / "events.db")
    caps = {
        "filesystem": FilesystemCapability(),
        "research": ResearchCapability(search_fn=fake_search, fetch_fn=fake_fetch),
    }
    rt = Runtime(model=model, capabilities=caps, workspace=ws, db=db,
                 strong_model=strong, cheap_model=cheap)
    return rt, ws, db


def test_runtime_completes_when_report_is_good(tmp_path):
    rt, ws, db = _make_runtime(tmp_path, FakeModel())
    task = rt.run("research weather apis")
    db.close()
    assert task.status == "succeeded"
    assert task.escalation == 0
    report = ws / "output" / "weather-api-comparison.md"
    assert report.exists()
    assert "## References" in report.read_text()


def test_runtime_events_are_logged(tmp_path):
    rt, ws, db = _make_runtime(tmp_path, FakeModel())
    task = rt.run("research weather apis")
    kinds = [e.kind for e in db.events_for(task.id)]
    db.close()
    for expected in ("task_created", "plan_created", "verify", "cost", "task_done"):
        assert expected in kinds


def test_runtime_escalates_once_on_verification_failure(tmp_path):
    rt, ws, db = _make_runtime(tmp_path, EscalationFake())
    task = rt.run("research weather apis")
    db.close()
    assert task.escalation == 1
    assert task.status == "succeeded"
    report = ws / "output" / "weather-api-comparison.md"
    assert "## References" in report.read_text()


def test_runtime_tracks_model_calls_and_cost(tmp_path):
    class PricedFake(FakeModel):
        default_model = "gpt-4o-mini"

    rt, ws, db = _make_runtime(tmp_path, PricedFake(), cheap="gpt-4o-mini")
    task = rt.run("research weather apis")
    db.close()
    assert task.model_calls >= 1
    assert task.cost_kind in {"estimated", "unknown"}
