"""Configuration loading and validation."""

import pytest

from agent_scout.config import Config, ConfigError, load_config


def test_defaults_match_the_documented_behaviour():
    cfg = Config()
    assert cfg.page_budget == 6
    assert cfg.delay_seconds == 1.5
    assert cfg.llm.enabled is False


def test_file_values_then_overrides(tmp_path):
    path = tmp_path / "cfg.yaml"
    path.write_text("page_budget: 3\ndelay_seconds: 0.5\nllm:\n  provider: openai-compatible\n  model: m\n",
                    encoding="utf-8")
    cfg = load_config(path, {"delay_seconds": 2.0, "page_budget": None})
    assert cfg.page_budget == 3          # None override means "not given"
    assert cfg.delay_seconds == 2.0
    assert cfg.llm.provider == "openai-compatible"
    assert cfg.llm.model == "m"


@pytest.mark.parametrize("text, fragment", [
    ("page_budget: 0\n", "page_budget"),
    ("delay_seconds: -1\n", "delay_seconds"),
    ("surprise: 1\n", "surprise"),
    ("llm:\n  provider: other\n", "provider"),
    ("llm:\n  api_key: abc\n", "api_key"),
    ("llm:\n  enabled: true\n", "--llm"),
    ("- a\n- b\n", "mapping"),
    ("page_budget: [1\n", "YAML"),
])
def test_invalid_config_is_a_one_line_error(tmp_path, text, fragment):
    path = tmp_path / "cfg.yaml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ConfigError) as err:
        load_config(path)
    assert fragment in str(err.value)
    assert "\n" not in str(err.value)


def test_missing_config_file(tmp_path):
    with pytest.raises(ConfigError):
        load_config(tmp_path / "nope.yaml")


def test_example_config_loads():
    from pathlib import Path
    example = Path(__file__).resolve().parents[1] / "config.example.yaml"
    cfg = load_config(example)
    assert cfg == Config()   # the example documents the defaults
