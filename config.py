"""Configuration lookup that never crashes when secrets are missing."""
from __future__ import annotations

import os
from typing import Any


def get_secret(name: str, default: Any = "") -> Any:
    """Environment variable first, then Streamlit secrets. Never raises (e.g. no secrets.toml locally)."""
    value = os.environ.get(name)
    if value not in (None, ""):
        return value
    try:
        import streamlit as st

        if name in st.secrets:
            return st.secrets[name]
    except Exception:  # noqa: BLE001 - secrets backend missing or malformed
        pass
    return default
