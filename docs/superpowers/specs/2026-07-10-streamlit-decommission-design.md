# Streamlit Decommission Design

## Goal

Complete the React/FastAPI production cutover by removing the deprecated Streamlit runtime from the distributable project while preserving historical design records.

## Scope and boundaries

The active application is the FastAPI process on port 8000. In production, it serves the built React single-page application from `frontend/dist`; before that bundle exists in local development, the root endpoint continues to return the existing API guidance response.

Remove the legacy `web/` implementation and tests that only exercise it. Remove Streamlit from declared and locked Python dependencies and from the dependency attribution that pertains to that removed runtime. No FastAPI route or React source changes are required for this cleanup.

Historical records remain untouched: `docs/superpowers/specs/` and `docs/plans/` may refer to Streamlit as part of their contemporaneous decision history. The final source scan distinguishes these records from active code, packaging, configuration, and user documentation.

## Runtime and launchers

All supported launch paths start the same FastAPI server on port 8000 and direct users to `http://localhost:8000` (or `http://127.0.0.1:8000` on Windows). Launchers retain their existing prerequisite and configuration-file setup behavior. The Docker quick-start output names port 8000 as the single Web UI/API service; Docker Compose retains the one API service plus its setup-only init service.

The Windows portable package contains one primary launcher rather than a separate Streamlit web launcher. Its packaged readme describes configuration through the React workbench and resolves port conflicts as an API server concern.

## Documentation

Update active Chinese and English project documentation, installation and quick-start pages, architecture descriptions, and Windows packaging documentation to name the React workbench served by FastAPI at port 8000. Commands use `uv run python api/app.py` (with host/port options when a non-loopback interface is needed). Directory layouts no longer list `web/` and instead list `frontend/`.

## Validation

The regression suite verifies API functionality after removing Streamlit sources. Validation includes a fresh `uv lock` after editing `pyproject.toml`, frontend type-check and production build, Python tests and Ruff, Compose configuration validation, and a live FastAPI smoke check for both the `/health` endpoint and the built SPA root. A scoped repository scan must find no Streamlit or port-8501 references outside the explicitly preserved historical-record paths.

## Non-goals

- Rewriting historical specifications or migration plans.
- Changing the React workbench or API contracts introduced in the preceding migration.
- Removing generic asynchronous helpers or pipeline code that remains independently used outside `web/`.
