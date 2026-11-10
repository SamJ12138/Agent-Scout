"""Run settings: defaults, an optional YAML file, then command-line overrides.

The API key for the optional LLM pass is read from the environment only
(AGENT_SCOUT_LLM_API_KEY); it is refused in the config file so that it cannot
be committed by accident.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

import yaml

from . import obs

LLM_PROVIDERS = ("openai-compatible", "anthropic")


class ConfigError(Exception):
    """Invalid configuration. The message is a single line."""


@dataclass
class LLMConfig:
    enabled: bool = False             # set by --llm only, never by the config file
    provider: str | None = None       # openai-compatible | anthropic
    base_url: str | None = None       # e.g. https://api.deepseek.com/v1
    model: str | None = None
    timeout_seconds: float = 60.0
    max_chars_per_site: int = 24000   # cleaned page text sent per site


@dataclass
class Config:
    page_budget: int = 6              # pages fetched per site, homepage included
    delay_seconds: float = 1.5        # minimum gap between requests to one host
    max_crawl_delay_seconds: float = 30.0  # a larger Crawl-delay skips the site
    timeout_seconds: float = 20.0     # per request (connect and read)
    max_body_bytes: int = 5_000_000   # a larger response is a fetch error
    min_visible_chars: int = 200      # less visible text + scripts => needs_rendering
    max_integrations: int = 25
    llm: LLMConfig = field(default_factory=LLMConfig)


def _check(cfg: Config) -> None:
    if not isinstance(cfg.page_budget, int) or isinstance(cfg.page_budget, bool) or cfg.page_budget < 1:
        raise ConfigError("page_budget must be an integer >= 1")
    for name in ("delay_seconds", "max_crawl_delay_seconds"):
        value = getattr(cfg, name)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
            raise ConfigError(f"{name} must be a number >= 0")
    for name in ("timeout_seconds", "max_body_bytes", "min_visible_chars", "max_integrations"):
        value = getattr(cfg, name)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
            raise ConfigError(f"{name} must be a number > 0")
    if cfg.llm.provider is not None and cfg.llm.provider not in LLM_PROVIDERS:
        raise ConfigError(f"llm.provider must be one of: {', '.join(LLM_PROVIDERS)}")


def load_config(path: Path | None = None, overrides: dict[str, Any] | None = None) -> Config:
    """Build a Config. ``overrides`` entries that are None mean "not given"."""
    cfg = Config()
    if path is not None:
        try:
            data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        except OSError as exc:
            obs.emit("input", "fail", error_type="config_unreadable", path=str(path))
            raise ConfigError(f"cannot read config file {path}: {exc.strerror or exc}") from None
        except yaml.YAMLError as exc:
            obs.emit("input", "fail", error_type="config_yaml", path=str(path))
            problem = getattr(exc, "problem", None) or "syntax error"
            raise ConfigError(f"config file {path} is not valid YAML: {problem}") from None
        if data is None:
            data = {}
        if not isinstance(data, dict):
            raise ConfigError(f"config file {path} must contain a mapping of settings")
        known = {f.name for f in fields(Config)}
        for key, value in data.items():
            if key not in known:
                raise ConfigError(f"unknown setting in {path}: {key}")
            if key == "llm":
                _apply_llm(cfg.llm, value, path)
            else:
                setattr(cfg, key, value)
    for key, value in (overrides or {}).items():
        if value is None:
            continue
        if key.startswith("llm_"):
            setattr(cfg.llm, key[4:], value)
        else:
            setattr(cfg, key, value)
    _check(cfg)
    return cfg


def _apply_llm(llm: LLMConfig, data: Any, path: Path) -> None:
    if not isinstance(data, dict):
        raise ConfigError(f"llm in {path} must be a mapping")
    known = {f.name for f in fields(LLMConfig)}
    for key, value in data.items():
        if key == "api_key":
            raise ConfigError("llm.api_key is not read from the config file; set AGENT_SCOUT_LLM_API_KEY")
        if key == "enabled":
            raise ConfigError("llm.enabled is not a config file setting; the LLM pass runs only with --llm")
        if key not in known:
            raise ConfigError(f"unknown setting in {path}: llm.{key}")
        setattr(llm, key, value)
