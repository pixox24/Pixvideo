# Copyright (C) 2025 AIDC-AI
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0

"""Command Studio theme helpers for the Streamlit UI."""

from __future__ import annotations

import streamlit as st

from pixelle_video.config import config_manager


def render_command_studio_theme() -> None:
    """Inject the dark orange Command Studio visual system."""
    st.markdown(
        """
        <style>
        :root {
          --studio-bg: #070809;
          --studio-surface: #101113;
          --studio-surface-2: #161719;
          --studio-surface-3: #1e1f22;
          --studio-border: rgba(255, 255, 255, 0.11);
          --studio-border-strong: rgba(255, 122, 0, 0.46);
          --studio-text: #f3f4f6;
          --studio-muted: #a4a8b1;
          --studio-dim: #707681;
          --studio-orange: #ff7a00;
          --studio-orange-2: #ff9d2e;
          --studio-green: #55d76a;
          --studio-radius: 8px;
        }

        html, body, [data-testid="stAppViewContainer"], .stApp {
          background: var(--studio-bg);
          color: var(--studio-text);
        }

        [data-testid="stHeader"],
        header[data-testid="stHeader"],
        [data-testid="stToolbar"],
        [data-testid="stDecoration"],
        #MainMenu {
          display: none !important;
          height: 0 !important;
          visibility: hidden !important;
        }

        .block-container {
          max-width: 100%;
          padding: 1.25rem 1.25rem 1.4rem;
        }

        [data-testid="stSidebar"], [data-testid="stSidebarNav"] {
          background: #090a0b;
        }

        h1, h2, h3, h4, h5, h6, p, label, span, div {
          letter-spacing: 0 !important;
        }

        h3 {
          margin: 0;
        }

        .studio-shell {
          min-height: calc(100vh - 2.5rem);
        }

        .studio-sidebar {
          position: sticky;
          top: 1rem;
          height: calc(100vh - 2.4rem);
          display: flex;
          flex-direction: column;
          justify-content: space-between;
          gap: 1rem;
          padding: 1rem 0.85rem;
          border: 1px solid var(--studio-border);
          border-radius: var(--studio-radius);
          background:
            linear-gradient(180deg, rgba(255, 122, 0, 0.06), rgba(255, 122, 0, 0) 24%),
            var(--studio-surface);
        }

        .studio-brand {
          display: flex;
          align-items: center;
          gap: 0.75rem;
          margin-bottom: 1rem;
        }

        .studio-logo {
          display: grid;
          place-items: center;
          width: 2.45rem;
          height: 2.45rem;
          border-radius: 8px;
          color: #101113;
          background: linear-gradient(135deg, var(--studio-orange), var(--studio-orange-2));
          font-weight: 800;
        }

        .studio-brand-title {
          font-size: 1.02rem;
          font-weight: 700;
          color: var(--studio-text);
          line-height: 1.1;
        }

        .studio-brand-subtitle {
          margin-top: 0.15rem;
          color: var(--studio-muted);
          font-size: 0.78rem;
        }

        .studio-side-section-title {
          margin: 1rem 0 0.35rem;
          color: var(--studio-dim);
          font-size: 0.72rem;
          font-weight: 700;
          text-transform: uppercase;
        }

        .studio-credit-card {
          padding: 0.85rem;
          border: 1px solid var(--studio-border);
          border-radius: var(--studio-radius);
          background: rgba(255, 255, 255, 0.035);
        }

        .studio-credit-label {
          color: var(--studio-muted);
          font-size: 0.78rem;
        }

        .studio-credit-value {
          color: var(--studio-orange-2);
          font-size: 1.25rem;
          font-weight: 800;
          margin-top: 0.1rem;
        }

        .studio-command-bar {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 1rem;
          margin-bottom: 1rem;
          padding: 0.8rem 1rem;
          border: 1px solid var(--studio-border);
          border-radius: var(--studio-radius);
          background: rgba(16, 17, 19, 0.92);
        }

        .studio-page-kicker {
          color: var(--studio-orange-2);
          font-size: 0.86rem;
          font-weight: 700;
        }

        .studio-page-title {
          margin-top: 0.15rem;
          color: var(--studio-text);
          font-size: 1.16rem;
          font-weight: 700;
        }

        .studio-status-group {
          display: flex;
          flex-wrap: wrap;
          justify-content: flex-end;
          gap: 0.55rem;
        }

        .studio-pill {
          display: inline-flex;
          align-items: center;
          min-height: 2.15rem;
          padding: 0.35rem 0.7rem;
          border: 1px solid var(--studio-border);
          border-radius: 7px;
          color: var(--studio-muted);
          background: rgba(255, 255, 255, 0.035);
          font-size: 0.82rem;
        }

        .studio-pill strong {
          color: var(--studio-text);
          font-weight: 650;
        }

        .studio-dot {
          width: 0.5rem;
          height: 0.5rem;
          margin-right: 0.45rem;
          border-radius: 999px;
          background: var(--studio-green);
          box-shadow: 0 0 12px rgba(85, 215, 106, 0.55);
        }

        .studio-workbench {
          border: 1px solid var(--studio-border);
          border-radius: var(--studio-radius);
          background: var(--studio-surface);
          overflow: hidden;
        }

        .studio-workbench-title {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 0.8rem 1rem;
          border-bottom: 1px solid var(--studio-border);
          background: rgba(255, 255, 255, 0.025);
        }

        .studio-workbench-title strong {
          color: var(--studio-text);
          font-size: 0.96rem;
        }

        .studio-workbench-title span {
          color: var(--studio-muted);
          font-size: 0.78rem;
        }

        .studio-run-card {
          margin: 0.55rem 0 0.85rem;
          padding: 0.78rem;
          border: 1px solid var(--studio-border);
          border-radius: var(--studio-radius);
          background: rgba(255, 255, 255, 0.025);
        }

        .studio-run-status {
          display: inline-flex;
          align-items: center;
          margin-bottom: 0.65rem;
          color: var(--studio-muted);
          font-size: 0.8rem;
          font-weight: 750;
        }

        .studio-run-status.ready {
          color: var(--studio-green);
        }

        .studio-run-status.pending {
          color: var(--studio-orange-2);
        }

        .studio-run-grid {
          display: grid;
          grid-template-columns: 1fr;
          gap: 0.55rem;
        }

        .studio-run-grid span {
          display: block;
          color: var(--studio-dim);
          font-size: 0.72rem;
        }

        .studio-run-grid strong {
          display: block;
          margin-top: 0.12rem;
          color: var(--studio-text);
          font-size: 0.82rem;
          font-weight: 650;
          word-break: break-word;
        }

        .studio-recent-tasks {
          margin-top: 0.95rem;
          padding-top: 0.85rem;
          border-top: 1px solid var(--studio-border);
        }

        .studio-recent-heading {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 0.55rem;
        }

        .studio-recent-heading strong {
          color: var(--studio-text);
          font-size: 0.88rem;
        }

        .studio-recent-heading a {
          color: var(--studio-orange-2);
          font-size: 0.78rem;
          text-decoration: none;
        }

        .studio-task-row {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 0.65rem;
          padding: 0.58rem 0;
          border-top: 1px solid rgba(255, 255, 255, 0.07);
        }

        .studio-task-row strong {
          display: block;
          max-width: 12rem;
          overflow: hidden;
          color: var(--studio-text);
          font-size: 0.8rem;
          text-overflow: ellipsis;
          white-space: nowrap;
        }

        .studio-task-row span {
          color: var(--studio-dim);
          font-size: 0.72rem;
        }

        .studio-task-row em {
          color: var(--studio-orange-2);
          font-size: 0.72rem;
          font-style: normal;
        }

        .studio-zone-label {
          margin: 0.15rem 0 0.65rem;
          color: var(--studio-muted);
          font-size: 0.75rem;
          font-weight: 700;
          text-transform: uppercase;
        }

        div[data-testid="stVerticalBlockBorderWrapper"] {
          border-color: var(--studio-border) !important;
          border-radius: var(--studio-radius) !important;
          background: var(--studio-surface-2) !important;
          box-shadow: none !important;
        }

        div[data-testid="stVerticalBlockBorderWrapper"]:has(button[kind="primary"]) {
          background: linear-gradient(180deg, rgba(255, 122, 0, 0.08), rgba(255, 122, 0, 0.015)),
            var(--studio-surface-2) !important;
        }

        .stTabs [data-baseweb="tab-list"] {
          gap: 0.35rem;
          border-bottom: 1px solid var(--studio-border);
        }

        .stTabs [data-baseweb="tab"] {
          border-radius: 7px 7px 0 0;
          color: var(--studio-muted);
        }

        .stTabs [aria-selected="true"] {
          color: var(--studio-orange-2) !important;
          border-bottom-color: var(--studio-orange) !important;
        }

        .stRadio [role="radiogroup"] {
          gap: 0.35rem;
        }

        .stRadio label {
          padding: 0.2rem 0.35rem;
          border-radius: 7px;
        }

        .stRadio input[type="radio"] {
          width: 0 !important;
          min-width: 0 !important;
          height: 0 !important;
          margin: 0 !important;
          opacity: 0 !important;
        }

        .stRadio label[data-baseweb="radio"] > div:first-child {
          display: none !important;
        }

        .stRadio label:has(input:checked) {
          color: var(--studio-orange-2) !important;
          background: rgba(255, 122, 0, 0.12);
        }

        [data-testid="stTextArea"] textarea,
        [data-testid="stTextInput"] input,
        [data-testid="stNumberInput"] input,
        [data-baseweb="select"] > div {
          border-color: var(--studio-border) !important;
          border-radius: 7px !important;
          background: #0c0d0e !important;
          color: var(--studio-text) !important;
        }

        [data-testid="stTextArea"] textarea:focus,
        [data-testid="stTextInput"] input:focus {
          border-color: var(--studio-orange) !important;
          box-shadow: 0 0 0 1px rgba(255, 122, 0, 0.45) !important;
        }

        .stButton button,
        .stDownloadButton button,
        [data-testid="stBaseButton-secondary"] {
          border-color: var(--studio-border) !important;
          border-radius: 7px !important;
          color: var(--studio-text) !important;
          background: rgba(255, 255, 255, 0.035) !important;
        }

        .stButton button:hover,
        .stDownloadButton button:hover {
          border-color: var(--studio-border-strong) !important;
          color: var(--studio-orange-2) !important;
        }

        .stButton button[kind="primary"],
        [data-testid="stBaseButton-primary"] {
          border: 0 !important;
          color: #111111 !important;
          background: linear-gradient(135deg, var(--studio-orange), var(--studio-orange-2)) !important;
          font-weight: 800 !important;
        }

        .stSlider [data-baseweb="slider"] > div > div {
          background-color: rgba(255, 122, 0, 0.28);
        }

        .stSlider [role="slider"] {
          background-color: var(--studio-orange) !important;
          box-shadow: 0 0 0 4px rgba(255, 122, 0, 0.16) !important;
        }

        [data-testid="stAlert"] {
          border-radius: var(--studio-radius);
          border-color: var(--studio-border);
          background: rgba(255, 255, 255, 0.045);
        }

        hr {
          border-color: var(--studio-border);
        }

        @media (max-width: 1100px) {
          .studio-sidebar {
            position: static;
            height: auto;
          }

          .studio-command-bar {
            align-items: flex-start;
            flex-direction: column;
          }

          .studio-status-group {
            justify-content: flex-start;
          }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_studio_sidebar(pipelines: list, default_pipeline: str = "quick_create") -> str:
    """Render the Command Studio left rail and return the selected pipeline."""
    validation_label = "Connected" if config_manager.validate() else "Needs setup"
    validation_class = "ok" if config_manager.validate() else "warn"

    st.markdown(
        f"""
        <div class="studio-sidebar-top">
          <div class="studio-brand">
            <div class="studio-logo">PX</div>
            <div>
              <div class="studio-brand-title">Pixelle-Video</div>
              <div class="studio-brand-subtitle">AI Video Production</div>
            </div>
          </div>
          <div class="studio-side-section-title">Workspace</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    pipeline_names = [pipeline.name for pipeline in pipelines]
    if default_pipeline not in pipeline_names:
        default_pipeline = pipeline_names[0]
    selected = st.radio(
        "Workspace",
        pipeline_names,
        index=pipeline_names.index(default_pipeline),
        format_func=lambda name: next(
            pipeline.display_name for pipeline in pipelines if pipeline.name == name
        ),
        key="studio_selected_pipeline",
        label_visibility="collapsed",
    )

    st.markdown('<div class="studio-side-section-title">Utility</div>', unsafe_allow_html=True)
    st.page_link("pages/2_📚_History.py", label="History")
    st.markdown(
        f"""
        <div class="studio-sidebar-bottom">
          <div class="studio-credit-card">
            <div class="studio-credit-label">System</div>
            <div class="studio-credit-value">{validation_label}</div>
            <div class="studio-credit-label {validation_class}">ComfyUI / LLM status</div>
          </div>
          <div style="height: .7rem"></div>
          <div class="studio-credit-card">
            <div class="studio-credit-label">Preset</div>
            <div class="studio-credit-value">Command</div>
            <div class="studio-credit-label">Dark orange studio</div>
          </div>
        </div>
        <style>
          [data-testid="stRadio"] label {{
            min-height: 2.7rem;
            padding: 0.42rem 0.62rem;
            margin-bottom: 0.16rem;
            border: 1px solid transparent;
            border-radius: 8px;
            color: var(--studio-muted) !important;
          }}
          [data-testid="stRadio"] label:has(input:checked) {{
            color: var(--studio-orange-2);
            border-color: rgba(255, 122, 0, 0.22);
            background: linear-gradient(90deg, rgba(255, 122, 0, 0.16), rgba(255, 122, 0, 0.04));
          }}
          .studio-credit-label.ok {{ color: var(--studio-green); }}
          .studio-credit-label.warn {{ color: var(--studio-orange-2); }}
        </style>
        """,
        unsafe_allow_html=True,
    )
    return selected
