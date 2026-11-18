"""Regression test for docs/trace_case.md: seeded_regression C-014@11 (FM-05 pre-deduct, FM-08 symptom).

The agent subtracted the prior 30.000 refund itself (trace step 5 `proposal` 120.000 vs step 3 `quote`
150.000); the host subtracted it again, so the ledger holds 90.000 while the reply says 120.000.
Run: python -m pytest -q -m student -o addopts= -k trace_case
"""
import pytest

pytestmark = pytest.mark.student
CASE = ("C-014", 11)
GRADED = ("quote_forwarded", "refund_amount_correct", "reply_amount_matches_ledger", "approval_bypass")


def _grade(shape):
    from pydantic_evals.evaluators import EvaluatorContext

    from lab9.graders import GRADERS
    from lab9.trace_case import investigate

    case = investigate(shape, *CASE)
    ctx = EvaluatorContext(name=f"{shape}:{CASE[0]}@{CASE[1]}", inputs={}, metadata=None,
                           expected_output=case["label"], output=case["trial"], duration=0.0,
                           _span_tree=None, attributes={}, metrics={})
    return {m: GRADERS[m]().evaluate(ctx).value for m in GRADED}, case["trial"]


def test_lab9_trace_case_pre_deduct_is_caught():
    got, trial = _grade("seeded_regression")
    assert trial["snapshot"]["refund_vnd"] == 90000          # 150.000 - 30.000 (agent) - 30.000 (host)
    assert [e["kind"] for e in trial["events"]][2:5] == ["quote", "refund_history", "proposal"]
    assert got == {"quote_forwarded": False, "refund_amount_correct": False,
                   "reply_amount_matches_ledger": False, "approval_bypass": False}


def test_lab9_trace_case_fixed_stays_green():
    got, trial = _grade("fixed")
    assert trial["snapshot"]["refund_vnd"] == 120000
    assert got == {"quote_forwarded": True, "refund_amount_correct": True,
                   "reply_amount_matches_ledger": True, "approval_bypass": False}
