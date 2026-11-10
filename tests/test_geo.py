"""Reading places out of addresses and sentences."""

import pytest

from agent_scout import geo


@pytest.mark.parametrize("code, name", list(geo.COUNTRY_BY_CODE.items()))
def test_every_country_is_recognised_by_name_and_code(code, name):
    assert geo.country_name(name) == name
    assert geo.country_name(code, allow_code=True) == name
    assert geo.parse_place(f"Springfield, {name}") == ("Springfield", name)


@pytest.mark.parametrize("code, name", list(geo.US_STATE_BY_CODE.items()))
def test_every_us_state_implies_the_united_states(code, name):
    assert geo.parse_place(f"Springfield, {code} 12345") == ("Springfield", "United States")
    assert geo.parse_place(f"Springfield, {name}") == ("Springfield", "United States")


@pytest.mark.parametrize("text, expected", [
    ("12 Harbour Lane, Bristol BS1 4XY, United Kingdom", ("Bristol", "United Kingdom")),
    ("Wilhelminakade 900, 3072 AP Rotterdam, Netherlands", ("Rotterdam", "Netherlands")),
    ("San Francisco, CA 94105, USA", ("San Francisco", "United States")),
    ("London, UK", ("London", "United Kingdom")),
    ("Berlin", (None, None)),
    ("write to us, the team", (None, None)),          # "us" is not a country
    ("made in Indiana Jones style", (None, None)),
])
def test_parse_place(text, expected):
    assert geo.parse_place(text) == expected


def test_two_letter_codes_are_only_countries_when_asked():
    assert geo.country_name("NL") is None
    assert geo.country_name("in") is None
    assert geo.country_name("IN", allow_code=True) == "India"
