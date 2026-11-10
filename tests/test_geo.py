"""Reading places out of addresses and sentences."""

import pytest

from agent_scout import geo


@pytest.mark.parametrize("code, name", list(geo.COUNTRY_BY_CODE.items()))
def test_every_country_is_recognised_by_name_and_code(code, name):
    assert geo.country_name(name) == name
    assert geo.country_name(code, allow_code=True) == name
    assert geo.parse_place(f"Springfield, {name}") == ("Springfield", name)


@pytest.mark.parametrize("code, name", list(geo.US_STATE_BY_CODE.items()))
def test_a_us_state_states_the_country_only_with_a_zip_code_or_written_out(code, name):
    assert geo.parse_place(f"Springfield, {code} 12345") == ("Springfield", "United States")
    assert geo.parse_place(f"Springfield, {code}, USA") == ("Springfield", "United States")
    assert geo.parse_place(f"Springfield, {code}") == ("Springfield", None)        # a bare code is never enough
    written_out = geo.parse_place(f"Springfield, {name}")
    assert written_out == (("Springfield", None) if name == "Georgia" else ("Springfield", "United States"))


def test_state_codes_that_are_also_country_codes_are_all_real_state_codes():
    assert geo.US_STATE_CODES_THAT_ARE_ALSO_COUNTRY_CODES <= set(geo.US_STATE_BY_CODE)
    # the ones this tool has a country for must never resolve to that country from a bare code
    for code in geo.US_STATE_CODES_THAT_ARE_ALSO_COUNTRY_CODES & set(geo.COUNTRY_BY_CODE):
        assert geo.parse_place(f"Springfield, {code}") == ("Springfield", None)


@pytest.mark.parametrize("code, name", [(c, n) for c, n in geo.COUNTRY_BY_CODE.items() if c not in geo.US_STATE_BY_CODE])
def test_a_bare_country_code_that_is_not_a_state_code_states_the_country(code, name):
    assert geo.parse_place(f"Springfield, {code}") == ("Springfield", name)


@pytest.mark.parametrize("text, expected", [
    ("12 Harbour Lane, Bristol BS1 4XY, United Kingdom", ("Bristol", "United Kingdom")),
    ("Wilhelminakade 900, 3072 AP Rotterdam, Netherlands", ("Rotterdam", "Netherlands")),
    ("San Francisco, CA 94105, USA", ("San Francisco", "United States")),
    ("London, UK", ("London", "United Kingdom")),
    ("Berlin", (None, None)),
    ("Austin, TX", ("Austin", None)),
    ("write to us, the team", (None, None)),          # "us" is not a country
    ("made in Indiana Jones style", (None, None)),
])
def test_parse_place(text, expected):
    assert geo.parse_place(text) == expected


def test_two_letter_codes_are_only_countries_when_asked():
    assert geo.country_name("NL") is None
    assert geo.country_name("in") is None
    assert geo.country_name("IN", allow_code=True) == "India"
