"""Session-scoped draft state for the Quick Create page."""

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

import streamlit as st

DRAFT_KEY = "quick_create_draft"


def get_quick_create_draft() -> dict[str, Any]:
    """Return the current session draft, creating it when needed."""
    if DRAFT_KEY not in st.session_state:
        st.session_state[DRAFT_KEY] = {}
    return st.session_state[DRAFT_KEY]


def draft_value(key: str, default: Any = None) -> Any:
    """Read a value from the current Quick Create draft."""
    return get_quick_create_draft().get(key, default)


def update_quick_create_draft(updates: Mapping[str, Any]):
    """Merge non-None values into the current Quick Create draft."""
    draft = get_quick_create_draft()
    for key, value in updates.items():
        if value is not None:
            draft[key] = deepcopy(value)


def sync_widget_to_draft(draft_key: str, widget_key: str):
    """Copy a Streamlit widget value into the Quick Create draft."""
    if widget_key in st.session_state:
        update_quick_create_draft({draft_key: st.session_state[widget_key]})
