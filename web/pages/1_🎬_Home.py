# Copyright (C) 2025 AIDC-AI
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0

"""Home page - Command Studio video generation interface."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

_script_dir = Path(__file__).resolve().parent
_project_root = _script_dir.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from web.components.faq import render_faq_sidebar
from web.components.header import render_header
from web.components.settings import render_advanced_settings
from web.components.theme import render_command_studio_theme, render_studio_sidebar
from web.state.session import get_pixelle_video, init_i18n, init_session_state

st.set_page_config(
    page_title="Home - Pixelle-Video",
    page_icon="PV",
    layout="wide",
    initial_sidebar_state="collapsed",
)


def main() -> None:
    """Render the main Studio workspace."""
    init_session_state()
    init_i18n()
    render_command_studio_theme()

    from web.pipelines import get_all_pipeline_uis

    pipelines = get_all_pipeline_uis()
    pipeline_by_name = {pipeline.name: pipeline for pipeline in pipelines}

    left_col, main_col = st.columns([0.16, 0.84], gap="medium")

    with left_col:
        with st.container(border=True):
            selected_pipeline_name = render_studio_sidebar(
                pipelines,
                st.session_state.get("studio_selected_pipeline", "quick_create"),
            )

    with main_col:
        render_header()
        render_faq_sidebar()

        pixelle_video = get_pixelle_video()

        with st.expander("System Configuration", expanded=False):
            render_advanced_settings()

        selected_pipeline = pipeline_by_name.get(selected_pipeline_name) or pipelines[0]
        st.markdown(
            f"""
            <div class="studio-workbench-title">
              <div>
                <strong>{selected_pipeline.display_name}</strong>
                <span>{selected_pipeline.description or "Production workspace"}</span>
              </div>
              <span>Live workspace</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        selected_pipeline.render(pixelle_video)


if __name__ == "__main__":
    main()
