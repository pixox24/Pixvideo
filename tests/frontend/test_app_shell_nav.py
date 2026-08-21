"""PR-B: App shell navigation labels and soft-dark chrome."""

from pathlib import Path

APP = Path("frontend/src/App.tsx").read_text(encoding="utf-8")
CONSOLE = Path("frontend/src/components/ConsolePanel.tsx").read_text(encoding="utf-8")
TOAST = Path("frontend/src/components/Toast.tsx").read_text(encoding="utf-8")


def test_nav_display_labels_are_creation_oriented():
    assert ">开始创作<" in APP or "开始创作" in APP
    assert ">精修<" in APP or "精修" in APP
    assert ">作品库<" in APP or "作品库" in APP
    assert ">设置<" in APP
    # ActiveTab keys must remain stable
    assert '"quick-create"' in APP
    assert '"project-workbench"' in APP
    assert '"history"' in APP
    assert '"settings"' in APP
    assert '"image-to-video"' in APP
    assert 'navBtn("image-to-video"' in APP
    assert "hidden" in APP.split('navBtn("image-to-video"', 1)[1][:180]


def test_nav_groups_are_create_library_settings():
    nav = APP.split("<nav", 1)[1].split("</nav>", 1)[0]
    create_idx = nav.index("开始创作")
    polish_idx = nav.index("精修")
    i2v_idx = nav.index("图生视频")
    library_idx = nav.index("作品库")
    works_idx = nav.index("作品")
    settings_group_idx = nav.index("设置")
    assert create_idx < polish_idx < i2v_idx < works_idx < library_idx < settings_group_idx
    assert "作品" in nav
    assert "\n                项目\n" not in nav


def test_sidebar_uses_soft_dark_surface_tokens():
    assert "bg-[var(--color-surface-1)]" in APP
    assert "border-[var(--color-border-subtle)]" in APP
    assert "w-60" in APP
    assert "ring-1 ring-amber-500/20" in APP
    assert "statusExpanded" in APP
    assert "useState(false)" in APP  # collapsed by default (includes statusExpanded)


def test_mobile_overlay_uses_backdrop_blur():
    assert "backdrop-blur-sm" in APP


def test_header_status_pills_only_when_services_missing():
    assert "(!hasLlm || !hasImageGeneration)" in APP


def test_console_and_toast_soft_chrome():
    assert "border-[var(--color-border-subtle)]" in CONSOLE
    assert "bg-[var(--color-surface-1)]" in CONSOLE
    assert "shadow-[var(--shadow-soft)]" in TOAST
    assert "最近任务" in CONSOLE
    assert "还没有运行中的任务" in CONSOLE
    assert "text-[8px]" not in CONSOLE
    assert "text-[10px]" not in CONSOLE
    assert "grid-cols-2" not in CONSOLE
    assert "帧分镜" not in CONSOLE
    assert "控制台就绪" not in CONSOLE
    assert "错误日志:" not in CONSOLE
    assert "生成失败" in CONSOLE
    assert "ui-card" in CONSOLE
    assert "formatLiveProgressLabel" in CONSOLE
    assert "getStepStatus" in CONSOLE
