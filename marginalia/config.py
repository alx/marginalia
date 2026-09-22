"""Config loading: agents.yaml plus per-machine environment overrides.

The committed agents.yaml is public-safe: host-specific endpoints are
placeholders. Each machine's real values come from the environment
(systemd's EnvironmentFile / .env), which overrides the file:

    MK_HOST=100.x.y.z:8300            -> misskey.host
    LLM_BASE_URL=http://host:8081/v1  -> llm.base_url

Secrets (MK_TOKEN_*, MK_ADMIN_USER_ID) are read from the environment
everywhere else and never touch agents.yaml.
"""
import os
from pathlib import Path

import yaml

# (section, key) -> env var that wins when set
_ENV_OVERRIDES = {
    ("misskey", "host"): "MK_HOST",
    ("llm", "base_url"): "LLM_BASE_URL",
}


def load_config(path="agents.yaml"):
    """Load agents.yaml and apply environment overrides for local endpoints."""
    cfg = yaml.safe_load(Path(path).read_text())
    for (section, key), var in _ENV_OVERRIDES.items():
        val = os.environ.get(var)
        if val:
            cfg.setdefault(section, {})
            cfg[section][key] = val
    return cfg
