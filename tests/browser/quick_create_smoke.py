from pathlib import Path

from playwright.sync_api import sync_playwright

BASE_URL = "http://127.0.0.1:8004"
ARTIFACT_DIR = Path(
    "/Users/huazi/.codex/visualizations/2026/07/10/019f4c48-534b-7cc1-9a38-88f148f4b338/quick-create-p0-p2-qa"
)
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    page = context.new_page()
    console_errors = []
    page_errors = []
    page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
    page.on("pageerror", lambda error: page_errors.append(str(error)))

    page.goto(BASE_URL)
    page.wait_for_load_state("networkidle")

    stage_navigation = page.get_by_role("navigation", name="快捷创作阶段")
    for stage in ["内容", "分镜", "声音与画面", "核对并生成", "进度与结果"]:
        assert stage_navigation.get_by_role("button", name=stage, exact=False).count() == 1

    title = page.locator("#quick-create-title")
    title.fill("浏览器草稿恢复验证")
    page.wait_for_timeout(700)
    assert "草稿已自动保存" in page.locator("body").inner_text()

    batch_button = page.get_by_role("button", name="批量生成", exact=False)
    batch_button.click()
    page.wait_for_timeout(100)
    assert "将创建" in page.locator("body").inner_text()
    assert "个独立视频" in page.locator("body").inner_text()

    generate_button = page.get_by_role("button", name="提交 3 个视频任务")
    assert generate_button.is_disabled()
    page.get_by_text("我已核对以上配置", exact=False).locator("..").get_by_role("checkbox").check()
    assert generate_button.is_enabled()

    page.screenshot(path=str(ARTIFACT_DIR / "desktop-review.png"), full_page=False)
    page.reload()
    page.wait_for_load_state("networkidle")
    assert page.locator("#quick-create-title").input_value() == "浏览器草稿恢复验证"

    mobile = context.new_page()
    mobile.set_viewport_size({"width": 390, "height": 844})
    mobile.goto(BASE_URL)
    mobile.wait_for_load_state("networkidle")
    assert mobile.locator("#quick-create-title").is_visible()
    mobile.get_by_role("button", name="打开导航").click()
    assert mobile.get_by_role("button", name="关闭导航", exact=True).is_visible()
    mobile.get_by_role("button", name="关闭导航", exact=True).click()
    mobile.get_by_role("button", name="打开任务面板").click()
    assert mobile.locator("aside[aria-label='任务运行面板']").is_visible()
    mobile.screenshot(path=str(ARTIFACT_DIR / "mobile-task-drawer.png"), full_page=False)

    assert not console_errors, console_errors
    assert not page_errors, page_errors
    context.close()
    browser.close()

print("quick-create browser smoke passed")
