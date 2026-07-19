"""Tests for FlowResult and Step models."""
from __future__ import annotations

import json

from ds_e2e.models import FlowResult


def test_flow_result_pass():
    result = FlowResult(flow_name="test")
    result.pass_step("step1", "ok")
    result.pass_step("step2", "also ok", extra="data")
    assert result.passed
    assert len(result.steps) == 2
    assert result.steps[0].status == "PASS"
    assert result.steps[1].data == {"extra": "data"}


def test_flow_result_fail():
    result = FlowResult(flow_name="test")
    result.pass_step("step1", "ok")
    result.fail_step("step2", "something broke", code=500)
    assert not result.passed
    assert result.steps[1].status == "FAIL"
    assert result.steps[1].data == {"code": 500}


def test_flow_result_as_dict():
    result = FlowResult(flow_name="test")
    result.pass_step("s1", "d1")
    d = result.as_dict()
    assert d["status"] == "PASS"
    assert d["flow"] == "test"
    assert len(d["steps"]) == 1
    assert d["steps"][0]["name"] == "s1"


def test_flow_result_to_json():
    result = FlowResult(flow_name="test")
    result.pass_step("s1", "detail")
    parsed = json.loads(result.to_json())
    assert parsed["status"] == "PASS"


def test_flow_result_to_markdown():
    result = FlowResult(flow_name="test")
    result.pass_step("s1", "worked")
    result.fail_step("s2", "broke")
    md = result.to_markdown()
    assert "# E2E Report" in md
    assert "`s1`" in md
    assert "`s2`" in md


def test_none_values_excluded_from_data():
    result = FlowResult(flow_name="test")
    result.pass_step("s1", "ok", present="yes", absent=None)
    assert result.steps[0].data == {"present": "yes"}
