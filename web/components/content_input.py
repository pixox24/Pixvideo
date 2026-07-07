# Copyright (C) 2025 AIDC-AI
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Content input components for web UI (left column)
"""

import streamlit as st

from pixelle_video.config import config_manager
from web.i18n import tr
from web.state.quick_create_draft import (
    draft_value,
    sync_widget_to_draft,
    update_quick_create_draft,
)
from web.utils.async_helpers import get_project_version


def render_content_input():
    """Render content input section (left column) with batch support"""
    with st.container(border=True):
        st.markdown(f"**{tr('section.content_input')}**")
        
        # ====================================================================
        # Step 1: Batch mode toggle (highest priority)
        # ====================================================================
        batch_mode = st.checkbox(
            tr("batch.mode_label"),
            value=draft_value("batch_mode", False),
            help=tr("batch.mode_help"),
            key="quick_create_batch_mode",
            on_change=sync_widget_to_draft,
            args=("batch_mode", "quick_create_batch_mode"),
        )
        
        if not batch_mode:
            # ================================================================
            # Single task mode (original logic, unchanged)
            # ================================================================
            # Processing mode selection
            mode = st.radio(
                "Processing Mode",
                ["generate", "fixed"],
                horizontal=True,
                format_func=lambda x: tr(f"mode.{x}"),
                index=0 if draft_value("mode", "generate") == "generate" else 1,
                label_visibility="collapsed",
                key="quick_create_mode",
                on_change=sync_widget_to_draft,
                args=("mode", "quick_create_mode"),
            )
            
            # Text input (unified for both modes)
            text_placeholder = tr("input.topic_placeholder") if mode == "generate" else tr("input.content_placeholder")
            text_height = 120 if mode == "generate" else 200
            text_help = tr("input.text_help_generate") if mode == "generate" else tr("input.text_help_fixed")
            
            text = st.text_area(
                tr("input.text"),
                value=draft_value("text", ""),
                placeholder=text_placeholder,
                height=text_height,
                help=text_help,
                key="quick_create_text",
                on_change=sync_widget_to_draft,
                args=("text", "quick_create_text"),
            )
            
            # Split mode selector (only show in fixed mode)
            if mode == "fixed":
                split_mode_options = {
                    "paragraph": tr("split.mode_paragraph"),
                    "line": tr("split.mode_line"),
                    "sentence": tr("split.mode_sentence"),
                }
                split_mode = st.selectbox(
                    tr("split.mode_label"),
                    options=list(split_mode_options.keys()),
                    format_func=lambda x: split_mode_options[x],
                    index=list(split_mode_options.keys()).index(
                        draft_value("split_mode", "paragraph")
                    ),
                    help=tr("split.mode_help"),
                    key="quick_create_split_mode",
                    on_change=sync_widget_to_draft,
                    args=("split_mode", "quick_create_split_mode"),
                )
            else:
                split_mode = "paragraph"  # Default for generate mode (not used)
            
            # Title input (optional for both modes)
            title = st.text_input(
                tr("input.title"),
                value=draft_value("title", ""),
                placeholder=tr("input.title_placeholder"),
                help=tr("input.title_help"),
                key="quick_create_title",
                on_change=sync_widget_to_draft,
                args=("title", "quick_create_title"),
            )
            
            # Number of scenes (only show in generate mode)
            if mode == "generate":
                n_scenes = st.slider(
                    tr("video.frames"),
                    min_value=3,
                    max_value=30,
                    value=draft_value("n_scenes", 5),
                    help=tr("video.frames_help"),
                    label_visibility="collapsed",
                    key="quick_create_n_scenes",
                    on_change=sync_widget_to_draft,
                    args=("n_scenes", "quick_create_n_scenes"),
                )
                st.caption(tr("video.frames_label", n=n_scenes))
            else:
                # Fixed mode: n_scenes is ignored, set default value
                n_scenes = 5
                st.info(tr("video.frames_fixed_mode_hint"))
            
            params = {
                "batch_mode": False,
                "mode": mode,
                "text": text,
                "title": title,
                "n_scenes": n_scenes,
                "split_mode": split_mode
            }
            update_quick_create_draft(params)
            return params
        
        else:
            # ================================================================
            # Batch mode (simplified YAGNI version)
            # ================================================================
            st.markdown(f"**{tr('batch.section_title')}**")
            
            # Batch rules info
            st.info(f"""
**{tr('batch.rules_title')}**
- ✅ {tr('batch.rule_1')}
- ✅ {tr('batch.rule_2')}
- ✅ {tr('batch.rule_3')}
            """)
            
            # Batch topics input
            text_input = st.text_area(
                tr("batch.topics_label"),
                value=draft_value("batch_topics_text", ""),
                height=300,
                placeholder=tr("batch.topics_placeholder"),
                help=tr("batch.topics_help"),
                key="quick_create_batch_topics_text",
                on_change=sync_widget_to_draft,
                args=("batch_topics_text", "quick_create_batch_topics_text"),
            )
            
            # Split topics by newline
            if text_input:
                # Simple split by newline, filter empty lines
                topics = [
                    line.strip() 
                    for line in text_input.strip().split('\n') 
                    if line.strip()
                ]
                
                if topics:
                    # Check count limit
                    if len(topics) > 100:
                        st.error(tr("batch.count_error", count=len(topics)))
                        topics = []
                    else:
                        st.success(tr("batch.count_success", count=len(topics)))
                        
                        # Preview topics list
                        with st.expander(tr("batch.preview_title"), expanded=False):
                            for i, topic in enumerate(topics, 1):
                                st.markdown(f"`{i}.` {topic}")
                else:
                    topics = []
            else:
                topics = []
            
            st.markdown("---")
            
            # Title prefix (optional)
            title_prefix = st.text_input(
                tr("batch.title_prefix_label"),
                value=draft_value("title_prefix", ""),
                placeholder=tr("batch.title_prefix_placeholder"),
                help=tr("batch.title_prefix_help"),
                key="quick_create_title_prefix",
                on_change=sync_widget_to_draft,
                args=("title_prefix", "quick_create_title_prefix"),
            )
            
            # Number of scenes (unified for all videos)
            n_scenes = st.slider(
                tr("batch.n_scenes_label"),
                min_value=3,
                max_value=30,
                value=draft_value("n_scenes", 5),
                help=tr("batch.n_scenes_help"),
                key="quick_create_batch_n_scenes",
                on_change=sync_widget_to_draft,
                args=("n_scenes", "quick_create_batch_n_scenes"),
            )
            st.caption(tr("batch.n_scenes_caption", n=n_scenes))
            
            # Config info
            st.info(f"📌 {tr('batch.config_info')}")
            
            params = {
                "batch_mode": True,
                "topics": topics,
                "batch_topics_text": text_input,
                "mode": "generate",  # Fixed to AI generate content
                "title_prefix": title_prefix,
                "n_scenes": n_scenes,
            }
            update_quick_create_draft(params)
            return params


def render_bgm_section(key_prefix=""):
    """Render BGM selection section"""
    with st.container(border=True):
        st.markdown(f"**{tr('section.bgm')}**")
        
        with st.expander(tr("help.feature_description"), expanded=False):
            st.markdown(f"**{tr('help.what')}**")
            st.markdown(tr("bgm.what"))
            st.markdown(f"**{tr('help.how')}**")
            st.markdown(tr("bgm.how"))
        
        # Dynamically scan bgm folder for music files (merged from bgm/ and data/bgm/)
        from pixelle_video.utils.os_util import list_resource_files
        
        try:
            all_files = list_resource_files("bgm")
            # Filter to audio files only
            audio_extensions = ('.mp3', '.wav', '.flac', '.m4a', '.aac', '.ogg')
            bgm_files = sorted([f for f in all_files if f.lower().endswith(audio_extensions)])
        except Exception as e:
            st.warning(f"Failed to load BGM files: {e}")
            bgm_files = []
        
        # Add special "None" option
        bgm_options = [tr("bgm.none")] + bgm_files
        quick_create_config = config_manager.get("quick_create", {})
        saved_bgm_path = quick_create_config.get("bgm_path")
        
        # Default to saved BGM if available, then "default.mp3", otherwise None.
        default_index = 0
        draft_bgm_path = draft_value("bgm_path", saved_bgm_path)
        if draft_bgm_path is None:
            default_index = 0
        elif draft_bgm_path in bgm_files:
            default_index = bgm_options.index(draft_bgm_path)
        elif saved_bgm_path and saved_bgm_path in bgm_files:
            default_index = bgm_options.index(saved_bgm_path)
        elif "default.mp3" in bgm_files:
            default_index = bgm_options.index("default.mp3")
        
        bgm_choice = st.selectbox(
            "BGM",
            bgm_options,
            index=default_index,
            label_visibility="collapsed",
            key=f"{key_prefix}bgm_selector",
            on_change=sync_widget_to_draft,
            args=("bgm_selector", f"{key_prefix}bgm_selector"),
        )
        
        # BGM volume slider (only show when BGM is selected)
        if bgm_choice != tr("bgm.none"):
            saved_bgm_volume = quick_create_config.get("bgm_volume", 0.2)
            bgm_volume = st.slider(
                tr("bgm.volume"),
                min_value=0.0,
                max_value=0.5,
                value=float(draft_value("bgm_volume", saved_bgm_volume)),
                step=0.01,
                format="%.2f",
                key=f"{key_prefix}bgm_volume_slider",
                help=tr("bgm.volume_help"),
                on_change=sync_widget_to_draft,
                args=("bgm_volume", f"{key_prefix}bgm_volume_slider"),
            )
        else:
            bgm_volume = 0.2  # Default value when no BGM selected
        
        # BGM preview button (only if BGM is not "None")
        if bgm_choice != tr("bgm.none"):
            if st.button(tr("bgm.preview"), key=f"{key_prefix}preview_bgm", use_container_width=True):
                from pixelle_video.utils.os_util import get_resource_path, resource_exists
                try:
                    if resource_exists("bgm", bgm_choice):
                        bgm_file_path = get_resource_path("bgm", bgm_choice)
                        st.audio(bgm_file_path)
                    else:
                        st.error(tr("bgm.preview_failed", file=bgm_choice))
                except Exception as e:
                    st.error(f"{tr('bgm.preview_failed', file=bgm_choice)}: {e}")
        
        # Use full filename for bgm_path (including extension)
        bgm_path = None if bgm_choice == tr("bgm.none") else bgm_choice
    
    params = {
        "bgm_path": bgm_path,
        "bgm_volume": bgm_volume
    }
    update_quick_create_draft(params)
    return params


def render_version_info():
    """Render version info and GitHub link"""
    with st.container(border=True):
        st.markdown(f"**{tr('version.title')}**")
        version = get_project_version()
        github_url = "https://github.com/AIDC-AI/Pixelle-Video"
        
        # Version and GitHub link in one line
        github_url = "https://github.com/AIDC-AI/Pixelle-Video"
        badge_url = "https://img.shields.io/github/stars/AIDC-AI/Pixelle-Video"

        st.markdown(
            f'{tr("version.current")}: `{version}` &nbsp;&nbsp; '
            f'<a href="{github_url}" target="_blank">'
            f'<img src="{badge_url}" alt="GitHub stars" style="vertical-align: middle;">'
            f'</a>',
            unsafe_allow_html=True)

