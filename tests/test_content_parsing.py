from src.api.services.content_service import parse_generated_content
from src.models import ContentType


def test_parse_generated_content_extracts_chinese_sections_and_tags():
    result = parse_generated_content(
        "【标题】\nAI 提效清单\n\n【正文】\n第一步：建立流程。\n第二步：复盘结果。\n\n【标签】\nAI 效率, 内容运营",
        ContentType.XIAOHONGSHU,
    )

    assert result.title == "AI 提效清单"
    assert result.content == "第一步：建立流程。\n第二步：复盘结果。"
    assert result.tags == ["AI", "效率", "内容运营"]


def test_parse_generated_content_handles_crlf_video_script_format():
    result = parse_generated_content(
        "【 标题 】\r\n开场脚本\r\n\r\n【 脚本 】\r\n[开场]\r\n介绍主题\r\n",
        ContentType.VIDEO_SCRIPT,
    )

    assert result.title == "开场脚本"
    assert result.content == "[开场]\n介绍主题"
    assert result.tags is None


def test_parse_generated_content_falls_back_to_raw_content_without_sections():
    result = parse_generated_content("直接输出的一段内容", ContentType.WEIBO)

    assert result.title is None
    assert result.content == "直接输出的一段内容"
    assert result.tags is None
