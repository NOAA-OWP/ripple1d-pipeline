"""Load pipeline configuration.

Two disjoint key-spaces, merged into one dict:
  - Behavior/tuning:      default_config.yaml, optionally overridden by repo-root config.yaml.
  - Machine/environment:  .env (RP_* vars), overlaid onto the config object.

.env and the YAML never define the same key, so there is no precedence between them.
(config.yaml overriding default_config.yaml is the one intentional override, within
the behavior key-space.) See design_guide.md.
"""

import logging
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from dotenv import find_dotenv, load_dotenv

logger = logging.getLogger(__name__)

_PKG = Path(__file__).resolve().parent
DEFAULTS_PATH = _PKG / "default_config.yaml"
# repo root = package parent; resolves via __file__, not cwd
DEFAULT_USER_CONFIG = _PKG.parent / "config.yaml"


@dataclass(frozen=True)
class EnvVar:
    """How one RP_* environment variable maps into the config object."""

    keys: tuple[str, ...]  # nested config location, e.g. ("paths", "COLLECTIONS_ROOT_DIR")
    cast: Callable[[str], Any] = str
    required: bool = True
    default: Any = None


_ENV_OVERLAY = {
    # Requireds
    "RP_STAC_URL": EnvVar(("endpoints", "STAC_URL")),
    "RP_RIPPLE1D_VERSION": EnvVar(("RIPPLE1D_VERSION",)),
    "RP_COLLECTIONS_ROOT_DIR": EnvVar(("paths", "COLLECTIONS_ROOT_DIR")),
    "RP_NWM_FLOWLINES_PATH": EnvVar(("paths", "NWM_FLOWLINES_PATH")),
    "RP_MONITORING_DB_PATH": EnvVar(("paths", "MONITORING_DB_PATH")),
    "RP_BRIDGE_TILE_INDEX_PATH": EnvVar(("paths", "BRIDGE_TILE_INDEX_PATH")),
    "RP_TERRAIN_SOURCE_URL": EnvVar(("paths", "TERRAIN_SOURCE_URL")),
    "RP_SOURCE_NETWORK": EnvVar(("paths", "SOURCE_NETWORK")),
    "RP_FLOW_FILES_DIR": EnvVar(("flows2fim", "FLOW_FILES_DIR")),
    "RP_QC_TEMPLATE_QGIS_FILE": EnvVar(("qc", "QC_TEMPLATE_QGIS_FILE")),
    # Optionals
    "RP_RIPPLE1D_API_URL": EnvVar(("endpoints", "RIPPLE1D_API_URL"), required=False, default="http://127.0.0.1"),
    "RP_OPTIMUM_PARALLEL_PROCESS_COUNT": EnvVar(
        ("execution", "OPTIMUM_PARALLEL_PROCESS_COUNT"), int, required=False, default=4
    ),
    "RP_FLOWS2FIM_BIN_PATH": EnvVar(("flows2fim", "FLOWS2FIM_BIN_PATH"), required=False, default="flows2fim"),
    "RP_S3_UPLOAD_PREFIX": EnvVar(("paths", "S3_UPLOAD_PREFIX"), required=False, default=""),
    "RP_S3_UPLOAD_FAILED_PREFIX": EnvVar(("paths", "S3_UPLOAD_FAILED_PREFIX"), required=False, default=""),
    "RP_STAC_S3_KEY_PREFIX": EnvVar(("paths", "STAC_S3_KEY_PREFIX"), required=False, default=""),
}


def load_env(override=False):
    """Load .env, located independent of cwd (search up from cwd, else repo root)."""
    load_dotenv(find_dotenv(usecwd=True) or str(_PKG.parent / ".env"), override=override)


def user_config_path() -> Path:
    return Path(os.getenv("RP_CONFIG_PATH", DEFAULT_USER_CONFIG))


def _deep_merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in (over or {}).items():
        out[k] = _deep_merge(out[k], v) if isinstance(out.get(k), dict) and isinstance(v, dict) else v
    return out


def _set_nested(cfg: dict, keys: tuple, value) -> None:
    d = cfg
    for k in keys[:-1]:
        d = d.setdefault(k, {})
    d[keys[-1]] = value


def _overlay_env(cfg: dict) -> dict:
    missing = []
    for env_var, spec in _ENV_OVERLAY.items():
        raw = os.getenv(env_var)
        if raw is None or raw == "":  # unset or empty
            if spec.required:
                missing.append(env_var)
                continue
            value = spec.default
        else:
            try:
                value = spec.cast(raw)
            except (TypeError, ValueError):
                raise ValueError(f"{env_var}={raw!r} is not a valid {spec.cast.__name__}")
        _set_nested(cfg, spec.keys, value)

    if missing:
        raise ValueError(
            "Missing required environment variables (set them in your .env; see example.env): "
            + ", ".join(sorted(missing))
        )
    return cfg


def load_config() -> dict:
    """Return the merged config: defaults <- optional config.yaml <- environment."""
    load_env()
    cfg = yaml.safe_load(DEFAULTS_PATH.read_text()) or {}
    p = user_config_path()
    if p.exists():
        cfg = _deep_merge(cfg, yaml.safe_load(p.read_text()) or {})
        logger.info(f"Config: defaults from {DEFAULTS_PATH} overridden by {p}")
    else:
        logger.info(f"Config: defaults from {DEFAULTS_PATH} only (no user config at {p})")
    return _overlay_env(cfg)
