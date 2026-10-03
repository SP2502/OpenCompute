"""Tests for the planner: JSON plan production, validation, and repair."""

import pytest

from opencompute.core.models import ModelClient, ModelResult
from opencompute.core.planner import Planner
from opencompute.core.task import Plan, Step

from conftest import BrokenJsonModel, FakeModel, _plan_json


class RawModel(ModelClient):
    def __init__(self, text):
        self.text = text
        self.calls = 0

    def complete(self, messages, model=None):
        self.calls += 1
        return ModelResult(self.text, cost_kind="unknown")


def test_planner_produces_valid_plan():
    planner = Planner(FakeModel())
    plan = planner.plan("research weather apis")
    assert isinstance(plan, Plan)
    assert plan.steps
    assert plan.steps[0].capability in {"research", "filesystem"}


def test_planner_tolerates_code_fences():
    fenced = '```json\n' + _plan_json() + '\n```'
    planner = Planner(RawModel(fenced))
    plan = planner.plan("x")
    assert len(plan.steps) == 3


def test_planner_repairs_broken_json():
    model = BrokenJsonModel()
    planner = Planner(model)
    plan = planner.plan("x")
    assert len(plan.steps) == 3
    assert model.calls >= 2


def test_plan_rejects_unknown_top_level_field():
    bad = '{"steps": [], "notes": "", "bogus": 1}'
    planner = Planner(RawModel(bad))
    with pytest.raises(Exception):
        planner.plan("x")  # extra top-level field -> Pydantic rejects


def test_step_rejects_extra_fields():
    with pytest.raises(Exception):
        Step(capability="research", input={}, bogus=1)
