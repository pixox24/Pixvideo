# Copyright (C) 2025 AIDC-AI
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0

"""Header components for the Streamlit web UI."""

from __future__ import annotations

import streamlit as st

from pixelle_video.config import config_manager
from web.i18n import get_available_languages, set_language, tr
from web.utils.streamlit_helpers import safe_rerun


def render_header() -> None:
    """Render the Command Studio top command bar."""
    is_configured = config_manager.validate()
    connection_text = "Connected" if is_configured else "Needs setup"

    st.markdown('<div class="studio-command-bar">', unsafe_allow_html=True)
    col1, col2, col3 = st.columns([3.2, 1.35, 2.25])
    with col1:
        st.markdown(
            f"""
            <div>
              <div class="studio-page-kicker">Command Studio</div>
              <div class="studio-page-title">{tr('app.title')}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col2:
        render_language_selector()
    with col3:
        st.markdown(
            f"""
            <div class="studio-status-group">
              <span class="studio-pill"><span class="studio-dot"></span><strong>{connection_text}</strong></span>
              <span class="studio-pill">Theme&nbsp;<strong>Dark Orange</strong></span>
            </div>
            """,
            unsafe_allow_html=True,
        )
    st.markdown("</div>", unsafe_allow_html=True)


def render_language_selector() -> None:
    """Render the language selector."""
    languages = get_available_languages()
    lang_options = [f"{code} - {name}" for code, name in languages.items()]

    current_lang = st.session_state.get("language", "zh_CN")
    current_index = list(languages.keys()).index(current_lang) if current_lang in languages else 0

    selected = st.selectbox(
        tr("language.select"),
        options=lang_options,
        index=current_index,
        label_visibility="collapsed",
    )

    selected_code = selected.split(" - ")[0]
    if selected_code != current_lang:
        st.session_state.language = selected_code
        set_language(selected_code)
        safe_rerun()
