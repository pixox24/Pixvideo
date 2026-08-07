from pathlib import Path


def test_quick_create_allows_100_scenes():
    source = Path(__file__).parents[2] / "frontend" / "src" / "components" / "QuickCreate.tsx"
    assert 'max="100"' in source.read_text(encoding="utf-8")

