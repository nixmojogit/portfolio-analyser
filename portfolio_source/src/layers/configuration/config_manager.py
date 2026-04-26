"""
config_manager.py
Layer      : Configuration
Description: Single source of truth loader. Reads all six YAML config files
             and returns a unified config dict consumed by all other layers.
             All thresholds, weights, and toggles live in YAML — never hardcoded.
"""

from __future__ import annotations
from pathlib import Path
from typing import Any

import yaml

from src.utils.logger import get_logger

log = get_logger(__name__)

CONFIG_DIR = Path("config")

CONFIG_FILES = [
    "system.yaml",
    "portfolio.yaml",
    "goals.yaml",
    "thresholds.yaml",
    "scorecard_weights.yaml",
    "skills.yaml",
]

# Keys that must be present at top level of each config file
REQUIRED_KEYS: dict[str, list[str]] = {
    "system.yaml":           ["app_name", "log_level", "benchmark_index", "risk_free_rate"],
    "portfolio.yaml":        ["holdings"],
    "goals.yaml":            ["active_goals", "target_sector_allocation"],
    "thresholds.yaml":       ["rsi", "beta", "peg_ratio", "promoter_holding_pct"],
    "scorecard_weights.yaml":["overall_score_weights", "recommendation_thresholds"],
    "skills.yaml":           ["skills"],
}

# Keys inside overall_score_weights that must be present
REQUIRED_SCORECARD_KEYS = ["fundamental", "valuation", "technical", "sentiment", "risk"]


# ── Loaders ───────────────────────────────────────────────────────────────────

def load_yaml(filename: str) -> dict[str, Any]:
    """
    Load a single YAML file from the config directory.
    Args:
        filename: YAML filename e.g. 'system.yaml'
    Returns: parsed dict
    Raises: FileNotFoundError if file does not exist
            ValueError if file is empty or not valid YAML
    """
    path = CONFIG_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if data is None:
        raise ValueError(
            f"Config file is empty: {path}. "
            "Run: python generate_configs.py --force"
        )
    if not isinstance(data, dict):
        raise ValueError(f"Config file must be a YAML mapping: {path}")

    return data


def load_config() -> dict[str, Any]:
    """
    Load and merge all YAML configuration files into a single config dict.
    Keys in the merged dict match the filename stem e.g. config['system'],
    config['portfolio'], config['goals'], config['thresholds'],
    config['scorecard_weights'], config['skills'].
    Returns: merged config dict
    Raises: FileNotFoundError / ValueError on any missing or malformed file
    """
    config: dict[str, Any] = {}
    for filename in CONFIG_FILES:
        stem = filename.replace(".yaml", "")
        data = load_yaml(filename)
        config[stem] = data
        log.debug(f"Loaded config: {filename}")

    validate_config(config)
    log.info("All config files loaded and validated.")
    return config


def reload_config() -> dict[str, Any]:
    """
    Reload all config files from disk without restarting the application.
    Useful when the user edits YAML files while the app is running.
    Returns: freshly loaded config dict
    """
    log.info("Reloading config from disk ...")
    return load_config()


# ── Validation ────────────────────────────────────────────────────────────────

def validate_config(config: dict[str, Any]) -> bool:
    """
    Validate completeness and type correctness of the merged config.
    Raises ValueError if required keys are missing or types are wrong.
    Args:
        config: merged config dict from load_config()
    Returns: True if fully valid
    """
    errors: list[str] = []

    # Check required top-level keys per file
    for filename, required in REQUIRED_KEYS.items():
        stem = filename.replace(".yaml", "")
        section = config.get(stem, {})
        for key in required:
            if key not in section:
                errors.append(f"[{filename}] Missing required key: '{key}'")

    # Check scorecard weights sum to 1.0
    weights = config.get("scorecard_weights", {}).get("overall_score_weights", {})
    for key in REQUIRED_SCORECARD_KEYS:
        if key not in weights:
            errors.append(f"[scorecard_weights.yaml] Missing weight: '{key}'")
    if weights:
        total = round(sum(weights.get(k, 0) for k in REQUIRED_SCORECARD_KEYS), 6)
        if abs(total - 1.0) > 0.001:
            errors.append(
                f"[scorecard_weights.yaml] overall_score_weights must sum to 1.0, "
                f"got {total}"
            )

    # Check target sector allocation sums to ~100
    sector_alloc = config.get("goals", {}).get("target_sector_allocation", {})
    if sector_alloc:
        total_alloc = sum(sector_alloc.values())
        if abs(total_alloc - 100) > 1:
            errors.append(
                f"[goals.yaml] target_sector_allocation must sum to 100, "
                f"got {total_alloc}"
            )

    # Check risk_free_rate is a sensible float
    rfr = config.get("system", {}).get("risk_free_rate")
    if rfr is not None and not (0 < rfr < 1):
        errors.append(
            f"[system.yaml] risk_free_rate should be a decimal e.g. 0.065 "
            f"for 6.5%, got {rfr}"
        )

    if errors:
        for e in errors:
            log.error(e)
        raise ValueError(
            f"Config validation failed with {len(errors)} error(s):\n"
            + "\n".join(f"  • {e}" for e in errors)
        )

    return True


# ── Skill helpers ─────────────────────────────────────────────────────────────

def get_skill_config(config: dict[str, Any], skill_id: str) -> dict[str, Any]:
    """
    Return the config block for a specific skill from skills.yaml.
    Args:
        config   : merged config dict
        skill_id : e.g. 'SKILL-D01'
    Returns: dict with keys 'enabled' and 'cache_ttl_hours'
             Returns defaults if skill_id not found.
    """
    skills = config.get("skills", {}).get("skills", {})
    return skills.get(skill_id, {"enabled": True, "cache_ttl_hours": 24})


def is_skill_enabled(config: dict[str, Any], skill_id: str) -> bool:
    """
    Check whether a specific skill is enabled in skills.yaml.
    Defaults to True if skill_id is not found.
    Args:
        config   : merged config dict
        skill_id : e.g. 'SKILL-I18'
    Returns: bool
    """
    return get_skill_config(config, skill_id).get("enabled", True)


def get_skill_ttl(config: dict[str, Any], skill_id: str) -> float | None:
    """
    Return the cache TTL (hours) for a given skill from skills.yaml.
    Returns None if the skill has no cache TTL (computed skills).
    Args:
        config   : merged config dict
        skill_id : e.g. 'SKILL-D01'
    Returns: float (hours) or None
    """
    return get_skill_config(config, skill_id).get("cache_ttl_hours")


# ── Threshold helpers ─────────────────────────────────────────────────────────

def get_threshold(config: dict[str, Any], metric: str) -> dict[str, Any]:
    """
    Return the threshold dict for a specific metric from thresholds.yaml.
    Args:
        config : merged config dict
        metric : metric key e.g. 'rsi', 'peg_ratio', 'beta'
    Returns: threshold dict or empty dict if not found
    """
    return config.get("thresholds", {}).get(metric, {})


def get_recommendation_threshold(config: dict[str, Any], level: str) -> float:
    """
    Return the score threshold for a recommendation level.
    Args:
        config : merged config dict
        level  : 'strong_buy' | 'buy' | 'hold' | 'reduce' | 'exit'
    Returns: score threshold as float
    """
    defaults = {"strong_buy": 75, "buy": 55, "hold": 35, "reduce": 20, "exit": 0}
    thresholds = (
        config.get("scorecard_weights", {})
        .get("recommendation_thresholds", defaults)
    )
    return thresholds.get(level, defaults[level])