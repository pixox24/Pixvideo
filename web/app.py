# Copyright (C) 2025 AIDC-AI
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0

"""Pixelle-Video Streamlit entry point."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

_script_dir = Path(__file__).resolve().parent
_project_root = _script_dir.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

st.set_page_config(
    page_title="Pixelle-Video - AI Video Generator",
    page_icon="PV",
    layout="wide",
    initial_sidebar_state="collapsed",
)


def main() -> None:
    """Run the Streamlit multipage app."""
    home_page = st.Page(
        "pages/1_🎬_Home.py",
        title="Home",
        icon=":material/movie:",
        default=True,
    )

    history_page = st.Page(
        "pages/2_📚_History.py",
        title="History",
        icon=":material/history:",
    )

    pg = st.navigation([home_page, history_page])
    pg.run()


if __name__ == "__main__":
    main()
