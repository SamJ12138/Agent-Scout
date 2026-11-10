"""Reading the list of sites to profile."""

import pytest

from agent_scout.inputs import InputError, load_sites, slugify


def write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_yaml_list_of_mappings_and_strings(tmp_path):
    path = write(tmp_path, "sites.yaml",
                 "- name: Northwind Campaign Pilot (fictional)\n  url: http://127.0.0.1:8001/\n"
                 "- https://www.example.com/product\n")
    sites = load_sites(path)
    assert [(s.slug, s.name, s.url) for s in sites] == [
        ("northwind-campaign-pilot-fictional", "Northwind Campaign Pilot (fictional)", "http://127.0.0.1:8001/"),
        ("example-com", None, "https://www.example.com/product"),
    ]


def test_yaml_mapping_with_sites_key_and_explicit_slug(tmp_path):
    path = write(tmp_path, "sites.yml", "sites:\n  - slug: ex\n    url: https://example.com\n")
    assert load_sites(path)[0].slug == "ex"


def test_text_file_ignores_blank_lines_and_comments(tmp_path):
    path = write(tmp_path, "sites.txt", "# list\n\nhttps://a.example/\n  https://b.example/x  \n")
    assert [s.url for s in load_sites(path)] == ["https://a.example/", "https://b.example/x"]


def test_duplicate_slugs_get_a_suffix(tmp_path):
    path = write(tmp_path, "sites.txt", "https://a.example/\nhttps://a.example/two\n")
    assert [s.slug for s in load_sites(path)] == ["a-example", "a-example-2"]


@pytest.mark.parametrize("text, fragment", [
    ("ftp://a.example/\n", "http"),
    ("not a url\n", "not a url"),
    ("", "no sites"),
])
def test_bad_text_input(tmp_path, text, fragment):
    with pytest.raises(InputError) as err:
        load_sites(write(tmp_path, "sites.txt", text))
    assert fragment in str(err.value)


@pytest.mark.parametrize("text", ["- name: x\n", "sites: 3\n", "- [1, 2]\n", "a: [\n"])
def test_bad_yaml_input(tmp_path, text):
    with pytest.raises(InputError) as err:
        load_sites(write(tmp_path, "sites.yaml", text))
    assert "\n" not in str(err.value)


def test_missing_file(tmp_path):
    with pytest.raises(InputError):
        load_sites(tmp_path / "missing.yaml")


def test_slugify():
    assert slugify("Orbit Fleet Agents (fictional)") == "orbit-fleet-agents-fictional"
    assert slugify("  ") == "site"
