from app.leetcode_cn import html_to_text


def test_html_to_text_removes_extra_blank_lines_and_cjk_spaces():
    html = """
    <p>给定一个整数数组 <code>nums</code> 和一个整数目标值 <code>target</code></p>
    <p>&nbsp;</p>
    <p>示例 1：</p>
    <ul><li>2 &lt;= nums.length &lt;= 104</li><li>只会存在一个有效答案</li></ul>
    """

    text = html_to_text(html)

    assert "\n\n\n" not in text
    assert "整数数组 `nums` 和一个整数目标值 `target`" in text
    assert "**示例 1：**\n\n- 2 <= nums.length <= 104" in text
    assert "- 2 <= nums.length <= 104" in text
    assert "- 只会存在一个有效答案" in text


def test_html_to_text_preserves_problem_images_as_markdown():
    html = '<p>如下图所示：</p><p><img src="//assets.leetcode-cn.com/example.png" alt="示意图"></p>'

    text = html_to_text(html)

    assert "如下图所示：" in text
    assert "![示意图](https://assets.leetcode-cn.com/example.png)" in text


def test_html_to_text_adds_space_after_bold_example_labels():
    html = "<p><strong>输入：</strong>x = 121<br><strong>输出：</strong>true</p>"

    text = html_to_text(html)

    assert "**输入：** x = 121" in text
    assert "**输出：** true" in text


def test_html_to_text_does_not_emit_broken_markdown_for_nested_emphasis():
    html = "<p>找出 <strong>和为目标值 <em><code>target</code></em> 的那</strong> 两个整数。</p>"

    text = html_to_text(html)

    assert "**" not in text
    assert "找出和为目标值 `target` 的那两个整数。" in text
