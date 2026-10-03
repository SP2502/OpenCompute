"""End-to-end tests for the runtime: completion, escalation, cost, context."""

from opencompute.capabilities.filesystem import FilesystemCapability
from opencompute.capabilities.http import HttpCapability
from opencompute.capabilities.research import ResearchCapability
from opencompute.core.database import Database
from opencompute.core.runtime import Runtime

from conftest import EscalationFake, FakeModel, PricedModel, fake_fetch, fake_search


def _make_runtime(tmp_path, model, strong="fake-strong", cheap="fake-cheap", extra=None):
    ws = tmp_path / "workspace"
    ws.mkdir()
    db = Database(ws / "state" / "events.db")
    caps = {
        "filesystem": FilesystemCapability(),
        "research": ResearchCapability(search_fn=fake_search, fetch_fn=fake_fetch),
        "http": HttpCapability(),
    }
    if extra:
        caps.update(extra)
    rt = Runtime(model=model, capabilities=caps, workspace=ws, db=db,
                 strong_model=strong, cheap_model=cheap)
    return rt, ws, db


def test_runtime_completes_when_report_is_good(tmp_path):
    rt, ws, db = _make_runtime(tmp_path, FakeModel())
    task = rt.run("compare open source projects")
    db.close()
    assert task.status == "succeeded"
    assert task.escalation == 0
    report = ws / "output" / "comparison.md"
    assert report.exists()
    assert "## References" in report.read_text()


def test_runtime_events_are_logged(tmp_path):
    rt, ws, db = _make_runtime(tmp_path, FakeModel())
    task = rt.run("compare open source projects")
    kinds = [e.kind for e in db.events_for(task.id)]
    db.close()
    for expected in ("task_created", "plan_created", "model_call", "capability",
                     "verify", "cost", "task_done"):
        assert expected in kinds


def test_runtime_escalates_once_on_verification_failure(tmp_path):
    rt, ws, db = _make_runtime(tmp_path, EscalationFake())
    task = rt.run("compare open source projects")
    db.close()
    assert task.escalation == 1
    assert task.retries == 1
    assert task.status == "succeeded"
    report = ws / "output" / "comparison.md"
    assert "## References" in report.read_text()


def test_runtime_tracks_model_calls_and_tokens(tmp_path):
    rt, ws, db = _make_runtime(tmp_path, PricedModel(), cheap="gpt-4o-mini")
    task = rt.run("compare open source projects")
    db.close()
    assert task.model_calls >= 1
    assert task.tokens_in > 0
    assert task.tokens_out > 0
    assert task.total_cost > 0
    assert task.estimated_calls >= 1
    assert task.duration >= 0


def test_later_step_consumes_earlier_output(tmp_path):
    # The second research step references "$research" (prior findings). Capture
    # the resolved input the research capability actually receives.
    seen = {}

    class SpyingResearch(ResearchCapability):
        def execute(self, input, ctx):
            seen["findings"] = input.get("findings")
            return super().execute(input, ctx)

    rt, ws, db = _make_runtime(tmp_path, FakeModel(),
                               extra={"research": SpyingResearch(search_fn=fake_search, fetch_fn=fake_fetch)})
    task = rt.run("compare open source projects")
    db.close()
    assert task.status == "succeeded"
    # The findings field should be the first step's summary text, not "$research".
    assert seen["findings"] and seen["findings"] != "$research"
    assert "Project A" in seen["findings"]
