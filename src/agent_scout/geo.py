"""Reference data for reading addresses: countries and US states.

Used only to recognise a country that a site wrote down. Nothing here infers
a country from a city name, and nothing guesses between two readings:

- a country name or common short form ("Germany", "UK", "USA") states the country;
- a US state with a ZIP code ("Austin, TX 78701") or a US state written out
  ("San Francisco, California") states the United States;
- a bare two-letter code after a city does NOT state the United States:
  "Toronto, CA", "Berlin, DE", "Bengaluru, IN" and "Perth, WA" are not in the
  US. If the code is an ISO country code and not also a US state code
  ("Lyon, FR") it states that country; otherwise the country stays unknown;
- "Georgia" alone is a country and a US state, so it states neither.
"""

from __future__ import annotations

import re

# ISO code | name used in results | other spellings a site may use
_COUNTRIES = """
AE|United Arab Emirates|UAE,U.A.E.
AR|Argentina|
AT|Austria|
AU|Australia|
BE|Belgium|
BG|Bulgaria|
BR|Brazil|Brasil
CA|Canada|
CH|Switzerland|
CL|Chile|
CN|China|People's Republic of China,PRC
CO|Colombia|
CY|Cyprus|
CZ|Czech Republic|Czechia
DE|Germany|Deutschland
DK|Denmark|
EE|Estonia|
EG|Egypt|
ES|Spain|España
FI|Finland|
FR|France|
GB|United Kingdom|UK,U.K.,Great Britain,England,Scotland,Wales,Northern Ireland
GR|Greece|
HK|Hong Kong|Hong Kong SAR
HR|Croatia|
HU|Hungary|
ID|Indonesia|
IE|Ireland|Republic of Ireland
IL|Israel|
IN|India|
IS|Iceland|
IT|Italy|Italia
JP|Japan|
KE|Kenya|
KR|South Korea|Republic of Korea,Korea
LT|Lithuania|
LU|Luxembourg|
LV|Latvia|
MT|Malta|
MX|Mexico|México
MY|Malaysia|
NG|Nigeria|
NL|Netherlands|The Netherlands,Holland
NO|Norway|
NZ|New Zealand|
PE|Peru|
PH|Philippines|
PK|Pakistan|
PL|Poland|
PT|Portugal|
RO|Romania|
RS|Serbia|
SA|Saudi Arabia|
SE|Sweden|
SG|Singapore|
SI|Slovenia|
SK|Slovakia|
TH|Thailand|
TR|Turkey|Türkiye
TW|Taiwan|
UA|Ukraine|
US|United States|USA,U.S.A.,U.S.,United States of America,US
UY|Uruguay|
VN|Vietnam|Viet Nam
ZA|South Africa|
"""

_US_STATES = """
AL|Alabama AK|Alaska AZ|Arizona AR|Arkansas CA|California CO|Colorado CT|Connecticut DE|Delaware
FL|Florida GA|Georgia HI|Hawaii ID|Idaho IL|Illinois IN|Indiana IA|Iowa KS|Kansas KY|Kentucky
LA|Louisiana ME|Maine MD|Maryland MA|Massachusetts MI|Michigan MN|Minnesota MS|Mississippi
MO|Missouri MT|Montana NE|Nebraska NV|Nevada NH|New_Hampshire NJ|New_Jersey NM|New_Mexico
NY|New_York NC|North_Carolina ND|North_Dakota OH|Ohio OK|Oklahoma OR|Oregon PA|Pennsylvania
RI|Rhode_Island SC|South_Carolina SD|South_Dakota TN|Tennessee TX|Texas UT|Utah VT|Vermont
VA|Virginia WA|Washington WV|West_Virginia WI|Wisconsin WY|Wyoming DC|District_of_Columbia
"""

COUNTRY_BY_CODE: dict[str, str] = {}
COUNTRY_NAMES: dict[str, str] = {}        # lower-case spelling -> name used in results
UPPERCASE_ONLY = {"US", "UK", "UAE", "PRC"}   # short forms that are words in lower case

for _line in _COUNTRIES.strip().splitlines():
    _code, _name, _others = _line.split("|")
    COUNTRY_BY_CODE[_code] = _name
    for _spelling in [_name, *[o for o in _others.split(",") if o]]:
        COUNTRY_NAMES[_spelling.lower()] = _name

US_STATE_BY_CODE: dict[str, str] = {}
US_STATE_NAMES: dict[str, str] = {}
for _pair in _US_STATES.split():
    _code, _name = _pair.split("|")
    US_STATE_BY_CODE[_code] = _name.replace("_", " ")
    US_STATE_NAMES[_name.replace("_", " ").lower()] = _code

_POSTCODE = re.compile(r"\b(?:[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}|[A-Z]\d[A-Z]\s?\d[A-Z]\d|\d{4}\s?[A-Z]{2}|[A-Z]{0,2}-?\d{3,6}(?:-\d{3,4})?)\b")


def country_name(text: str, allow_code: bool = False) -> str | None:
    """The country a piece of text names, or None. ``allow_code`` accepts ISO codes (JSON-LD)."""
    stripped = text.strip().strip(".,;")
    if stripped in UPPERCASE_ONLY:
        return COUNTRY_NAMES[stripped.lower()]
    if stripped.lower() in COUNTRY_NAMES and stripped.upper() not in UPPERCASE_ONLY:
        return COUNTRY_NAMES[stripped.lower()]
    if allow_code and stripped.upper() in COUNTRY_BY_CODE and len(stripped) == 2:
        return COUNTRY_BY_CODE[stripped.upper()]
    return None


US_STATE_CODES_THAT_ARE_ALSO_COUNTRY_CODES = frozenset(
    "AL AR AZ CA CO DE GA ID IL IN KY LA MA MD ME MN MO MS MT NC NE PA SC SD TN VA".split())
AMBIGUOUS_STATE_NAMES = frozenset({"georgia"})        # also a country
_ZIP = re.compile(r"\s+\d{5}(?:-\d{4})?$")


def us_state(text: str) -> str | None:
    """'CA', 'CA 94105' or 'California' -> the state code; anything else -> None.
    Says what a token could be; whether it states the country is decided by the caller."""
    stripped = _ZIP.sub("", text.strip().strip(".,;"))
    if stripped in US_STATE_BY_CODE:
        return stripped
    return US_STATE_NAMES.get(stripped.lower())


def states_the_united_states(text: str) -> bool:
    """True for a state with a ZIP code, or a state name that is not also a country."""
    token = text.strip().strip(".,;")
    if us_state(token) is None:
        return False
    if _ZIP.search(token):
        return True
    return token.lower() in US_STATE_NAMES and token.lower() not in AMBIGUOUS_STATE_NAMES


def strip_postcode(text: str) -> str:
    return re.sub(r"\s+", " ", _POSTCODE.sub("", text)).strip(" ,")


def _looks_like_city(text: str) -> bool:
    words = text.split()
    return 0 < len(words) <= 4 and all(word[0].isupper() or word.lower() in ("de", "la", "am", "of", "upon", "on")
                                       for word in words) and not any(ch.isdigit() for ch in text)


# "2800 Kongens Lyngby Denmark": postcode, city, country, written without commas
_POSTCODE_CITY_COUNTRY = re.compile(
    r"(?:^|\s)\d{4,5}\s+(?P<city>(?:[A-Z][\w.'-]*\s+){0,2}[A-Z][\w.'-]*)\s+(?P<country>"
    + "|".join(sorted((re.escape(name) for name in {n for n in COUNTRY_BY_CODE.values()}), key=len, reverse=True))
    + r")\s*\.?$")


def parse_place(text: str) -> tuple[str | None, str | None]:
    """Read 'City, Country', 'City, ST 12345' or a full comma-separated address.

    Returns (city, country); either may be None. See the module docstring for
    what counts as stating a country.
    """
    parts = [part.strip() for part in re.split(r"[,\n|•·]+", text) if part.strip()]
    country = None
    index = len(parts)                       # position of the country or region part
    for position in range(len(parts) - 1, -1, -1):
        candidate = strip_postcode(parts[position]) or parts[position]
        found = country_name(candidate)
        if found:
            country, index = found, position
            break
    if country == "United States" and index >= 1 and us_state(parts[index - 1]):
        index -= 1                           # "Austin, TX, USA": the city is before the state
    elif country is None and parts:
        unpunctuated = _POSTCODE_CITY_COUNTRY.search(text.strip())
        if unpunctuated and re.search(r"\d", text.strip()[:unpunctuated.start() + 1]):
            # a street number before the postcode: "© 2026 Acme Denmark" is a year, not an address
            return unpunctuated.group("city"), unpunctuated.group("country")
        last = parts[-1].strip(".;")
        if states_the_united_states(last):
            country, index = "United States", len(parts) - 1
        elif len(last) == 2 and last.isupper():
            index = len(parts) - 1           # a bare code: a region or a country
            if last not in US_STATE_BY_CODE and last in COUNTRY_BY_CODE:
                country = COUNTRY_BY_CODE[last]
        elif last.lower() in AMBIGUOUS_STATE_NAMES:
            index = len(parts) - 1
        else:
            return None, None
    city = None
    if 1 <= index <= len(parts):
        candidate = strip_postcode(parts[index - 1])
        if _looks_like_city(candidate):
            city = candidate
    if country is None and city is None:
        return None, None
    return city, country
