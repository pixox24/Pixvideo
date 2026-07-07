from web.state.quick_create_draft import sync_widget_to_draft, update_quick_create_draft


def test_update_quick_create_draft_skips_none_and_copies_values(monkeypatch):
    session_state = {}
    monkeypatch.setattr("web.state.quick_create_draft.st.session_state", session_state)

    source = {"items": ["a"]}
    update_quick_create_draft({"mode": "generate", "unused": None, "nested": source})
    source["items"].append("b")

    assert session_state["quick_create_draft"] == {
        "mode": "generate",
        "nested": {"items": ["a"]},
    }


def test_sync_widget_to_draft_copies_streamlit_widget_value(monkeypatch):
    session_state = {"quick_create_title": "draft title"}
    monkeypatch.setattr("web.state.quick_create_draft.st.session_state", session_state)

    sync_widget_to_draft("title", "quick_create_title")

    assert session_state["quick_create_draft"]["title"] == "draft title"
