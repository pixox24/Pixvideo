from api.routers import workbench


def test_segmented_draft_does_not_add_speakable_numbering():
    draft = workbench._format_segmented_draft(["第一段旁白", "第二段旁白"])

    assert draft == "第一段旁白\n\n第二段旁白"
    assert "1." not in draft
    assert "2." not in draft
