"""Reference data for reading addresses: countries and US states.

Used only to recognise a country that a site wrote down (by name, by a common
short form, or as an ISO 3166-1 alpha-2 code in JSON-LD). Nothing here infers
a country from a city name.
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


def us_state(text: str) -> str | None:
    """'CA', 'CA 94105' or 'California' -> the state code; anything else -> None."""
    stripped = re.sub(r"\s+\d{5}(?:-\d{4})?$", "", text.strip().strip(".,;"))
    if stripped in US_STATE_BY_CODE:
        return stripped
    return US_STATE_NAMES.get(stripped.lower())


def strip_postcode(text: str) -> str:
    return re.sub(r"\s+", " ", _POSTCODE.sub("", text)).strip(" ,")


def _looks_like_city(text: str) -> bool:
    words = text.split()
    return 0 < len(words) <= 4 and all(word[0].isupper() or word.lower() in ("de", "la", "am", "of", "upon", "on")
                                       for word in words) and not any(ch.isdigit() for ch in text)


def parse_place(text: str) -> tuple[str | None, str | None]:
    """Read 'City, Country', 'City, ST 12345' or a full comma-separated address.

    Returns (city, country); either may be None. The country is only reported
    when the text names it, or names a US state (which states the country).
    """
    parts = [part.strip() for part in re.split(r"[,\n|•·]+", text) if part.strip()]
    country = None
    index = len(parts)
    for position in range(len(parts) - 1, -1, -1):
        candidate = strip_postcode(parts[position]) or parts[position]
        found = country_name(candidate)
        if found:
            country, index = found, position
            break
    region_index = index - 1
    if region_index >= 0 and us_state(parts[region_index]) and (country in (None, "United States")):
        country = "United States"
        index = region_index
    elif country is None:
        for position in range(len(parts) - 1, 0, -1):
            if us_state(parts[position]) and re.search(r"\d{5}", parts[position]) or parts[position].strip(".") in US_STATE_BY_CODE:
                country, index = "United States", position
                break
    if country is None:
        return None, None
    city = None
    if index - 1 >= 0:
        candidate = strip_postcode(parts[index - 1])
        if _looks_like_city(candidate):
            city = candidate
    return city, country
