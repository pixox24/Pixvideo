from pixelle_video.models.workbench import (
    AssetSource,
    AssetVersion,
    GenerationKind,
    Project,
    Scene,
)


def test_scene_defaults_to_audio_driven_duration_and_no_current_asset():
    scene = Scene(project_id="p1", position=0, narration="旁白", visual_prompt="画面")

    assert scene.current_version_id is None
    assert scene.duration_mode == "audio"
    assert scene.manual_hold_seconds == 0
    assert scene.status == "pending"


def test_asset_version_keeps_prompt_snapshot_and_source():
    asset = AssetVersion(
        project_id="p1",
        scene_id="s1",
        source=AssetSource.AI,
        relative_path="assets/scenes/s1/versions/v1.png",
        prompt_snapshot="warm cinematic street",
    )

    assert asset.source.value == "ai"
    assert asset.prompt_snapshot == "warm cinematic street"


def test_generation_kind_values_are_stable_for_task_metadata():
    assert {item.value for item in GenerationKind} == {"scene", "image", "tts", "export"}


def test_project_and_scene_ids_are_generated_when_omitted():
    project = Project(title="项目", config={})
    scene = Scene(project_id=project.project_id, position=0, narration="旁白", visual_prompt="画面")

    assert project.project_id
    assert scene.scene_id
    assert project.source == "quick-create"
