"""A prompt that asks for several quantities must not pass with one stated result."""

from studium.authoring.problems import unanswered_request

_ONE = {"result": "v = 0.25\\ \\mathrm{m^3/kg}"}
_TWO = {"result": ["v = 0.25\\ \\mathrm{m^3/kg}", "\\rho = 4\\ \\mathrm{kg/m^3}"]}
_PROMPT = "A tank holds 2.0 kg in 0.50 m^3. Find the specific volume of the gas and its density."


def test_two_requested_one_stated_is_flagged():
    flagged = unanswered_request(_PROMPT, _ONE)
    assert flagged is not None
    assert flagged["requested"] == 2
    assert flagged["stated"] == 1


def test_every_requested_quantity_stated_passes():
    assert unanswered_request(_PROMPT, _TWO) is None


def test_single_request_is_not_flagged():
    assert unanswered_request("Find the amount of substance in the vessel.", _ONE) is None


def test_conjunction_without_determiner_is_not_a_second_request():
    assert unanswered_request("Find the work done between 300 K and 400 K.", _ONE) is None


def test_non_string_prompt_is_ignored():
    assert unanswered_request(None, _ONE) is None
