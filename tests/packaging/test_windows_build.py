"""Tests for the Windows portable-package builder."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BUILD_MODULE_PATH = PROJECT_ROOT / "packaging" / "windows" / "build.py"
BUILD_CONFIG_PATH = PROJECT_ROOT / "packaging" / "windows" / "config" / "build_config.yaml"


def load_builder_module():
    spec = spec_from_file_location("pixvideo_windows_build", BUILD_MODULE_PATH)
    assert spec and spec.loader
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_builder(module, project_root: Path):
    builder = module.WindowsPackageBuilder(str(BUILD_CONFIG_PATH), output_dir=str(project_root / "output"))
    builder.project_root = project_root
    return builder


def test_build_frontend_runs_npm_install_and_build(tmp_path, monkeypatch) -> None:
    module = load_builder_module()
    frontend_dir = tmp_path / "frontend"
    frontend_dir.mkdir()
    builder = make_builder(module, tmp_path)
    commands = []

    monkeypatch.setattr(module.shutil, "which", lambda command: "/usr/bin/npm")
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda command, cwd, check: commands.append((command, cwd, check)),
    )

    builder.build_frontend()

    assert commands == [
        (["npm", "ci"], frontend_dir, True),
        (["npm", "run", "build"], frontend_dir, True),
    ]


def test_copy_project_files_keeps_dist_and_excludes_frontend_node_modules(tmp_path) -> None:
    module = load_builder_module()
    frontend_dir = tmp_path / "frontend"
    (frontend_dir / "dist").mkdir(parents=True)
    (frontend_dir / "dist" / "index.html").write_text("<html></html>", encoding="utf-8")
    (frontend_dir / "node_modules").mkdir()
    (frontend_dir / "node_modules" / "package.json").write_text("{}", encoding="utf-8")
    builder = make_builder(module, tmp_path)
    target_dir = tmp_path / "package"

    builder.copy_project_files(target_dir)

    assert (target_dir / "frontend" / "dist" / "index.html").is_file()
    assert not (target_dir / "frontend" / "node_modules").exists()
