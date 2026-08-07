import pytest

from pixelle_video.service import PixelleVideoCore


@pytest.mark.asyncio
async def test_core_initializes_workbench_services(monkeypatch, tmp_path):
    monkeypatch.setenv("PIXVIDEO_WORKBENCH_DIR", str(tmp_path))
    core = PixelleVideoCore()
    await core.initialize()

    assert core.workbench_repository is not None
    assert core.workbench_media is not None
    assert (tmp_path / "projects").is_dir()
    assert (tmp_path / "workbench.sqlite3").is_file()
    await core.cleanup()
    assert core.workbench_repository is None

