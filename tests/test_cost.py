"""Tests for model cost accounting: exact / estimated / unknown, and that
deterministic operations stay model-free."""

from opencompute.capabilities.filesystem import FilesystemCapability
from opencompute.capabilities.research import ResearchCapability
from opencompute.core.database import Database
from opencompute.core.models import ModelResult
from opencompute.core.runtime import Runtime

from conftest import GOOD_SUMMARY, _plan_json, fake_fetch, fake_search


def _cost_model(status: str, cost: float):
    class M:
        default_model = "m"

        def complete(self, messages, model=None):
            if any(m.get("role") == "system" for m in messages):
                return ModelResult(_plan_json(), cost_status=status, cost=cost)
            if "Instructions:" in messages[-1]["content"]:
                return ModelResult(GOOD_SUMMARY, prompt_tokens=10, completion_tokens=10,
                                   cost=cost, cost_status=status, provider="test")
            return ModelResult("ok", cost_status=status, cost=cost)

    return M()


def _runtime(tmp_path, model):
    ws = tmp_path / "ws"
    ws.mkdir()
    db = Database(ws / "state" / "events.db")
    caps = {
        "filesystem": FilesystemCapability(),
        "research": ResearchCapability(search_fn=fake_search, fetch_fn=fake_fetch),
    }
    return Runtime(model=model, capabilities=caps, workspace=ws, db=db)


def test_exact_cost_recorded(tmp_path):
    rt = _runtime(tmp_path, _cost_model("exact", 0.05))
    task = rt.run("x")
    assert task.cost_exact > 0
    assert task.exact_calls >= 1
    assert task.estimated_calls == 0
    assert task.unknown_calls == 0


def test_estimated_cost_recorded(tmp_path):
    rt = _runtime(tmp_path, _cost_model("estimated", 0.02))
    task = rt.run("x")
    assert task.cost_estimated > 0
    assert task.estimated_calls >= 1
    assert task.cost_exact == 0


def test_unknown_cost_recorded_as_unknown(tmp_path):
    rt = _runtime(tmp_path, _cost_model("unknown", 0.00))
    task = rt.run("x")
    assert task.unknown_calls >= 1
    assert task.total_cost == 0  # unknown cost is not added to a dollar total


def test_task_level_aggregation(tmp_path):
    rt = _runtime(tmp_path, _cost_model("estimated", 0.10))
    task = rt.run("x")
    assert task.total_cost == task.cost_exact + task.cost_estimated
    assert task.total_tokens == task.tokens_in + task.tokens_out


def test_filesystem_does_not_call_model(tmp_path):
    calls = []

    class CountingModel:
        default_model = "m"

        def complete(self, messages, model=None):
            calls.append(model)
            return ModelResult("x", cost_status="unknown")

    ws = tmp_path / "ws"
    ws.mkdir()
    db = Database(ws / "state" / "events.db")
    rt = Runtime(model=CountingModel(), capabilities={"filesystem": FilesystemCapability()},
                 workspace=ws, db=db)

    # The planner still calls the model once; but the filesystem step must not.
    # Reset and drive only the filesystem capability directly.
    from opencompute.capabilities.base import CapabilityContext
    calls.clear()
    ctx = CapabilityContext(workspace=ws, log=lambda *a: None, model=CountingModel())
    cap = FilesystemCapability()
    cap.execute({"action": "write", "path": "output/a.md", "content": "hi"}, ctx)
    rt.db.close()
    assert calls == []  # no model call happened during the write
