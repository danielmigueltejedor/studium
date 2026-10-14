from studium.mcp.server import _failed


def test_problem_verdicts_are_results_not_errors():
    for status in ("two_witnesses", "unchecked"):
        assert _failed({"status": status, "problem": {"id": "PRB-0001"}}) is False


def test_other_unchecked_payloads_and_failures_stay_errors():
    assert _failed({"status": "unchecked"}) is True
    assert _failed({"status": "stale", "problem": {"id": "PRB-0001"}}) is True
    assert _failed({"status": "compiler_missing", "problem": {"id": "PRB-0001"}}) is True
