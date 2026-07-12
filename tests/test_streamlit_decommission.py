"""Regression checks for removal of the retired web runtime."""

import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_project_has_no_retired_web_runtime() -> None:
    """The retired UI package and its Python dependency must not return."""
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as file:
        project = tomllib.load(file)["project"]

    assert not (PROJECT_ROOT / "web").exists()
    retired_dependency = "stream" + "lit"
    assert all(retired_dependency not in dependency.lower() for dependency in project["dependencies"])
