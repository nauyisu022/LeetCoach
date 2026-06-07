from __future__ import annotations

import html
import json
import re
import urllib.request
from html.parser import HTMLParser


class _TextExtractor(HTMLParser):
    block_tags = {"p", "div", "pre"}
    list_tags = {"ul", "ol"}

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        attr_map = dict(attrs)
        if tag in self.block_tags or tag in self.list_tags:
            self._blank_line()
        elif tag == "li":
            self.parts.append("\n- ")
        elif tag == "br":
            self.parts.append("\n")
        elif tag == "code":
            self.parts.append("`")
        elif tag == "img":
            src = _normalize_image_src(attr_map.get("src", ""))
            if src:
                alt = _markdown_alt(attr_map.get("alt", "题目图片"))
                self._blank_line()
                self.parts.append(f"\n\n![{alt}]({src})\n\n")
                self._blank_line()

    def handle_endtag(self, tag: str) -> None:
        if tag in self.block_tags or tag in self.list_tags:
            self._blank_line()
        elif tag == "li":
            self.parts.append("\n")
        elif tag == "code":
            self.parts.append("`")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def text(self) -> str:
        raw = html.unescape("".join(self.parts))
        raw = raw.replace("\xa0", " ")
        raw = re.sub(r"[ \t]+", " ", raw)
        raw = re.sub(r"(?<=[\u4e00-\u9fff]) (?=[\u4e00-\u9fff])", "", raw)
        lines = [line.strip() for line in raw.splitlines()]
        compact_lines: list[str] = []
        previous_blank = True
        for line in lines:
            if line:
                compact_lines.append(_format_problem_line(line))
                previous_blank = False
            elif not previous_blank:
                compact_lines.append("")
                previous_blank = True
        return "\n".join(compact_lines).strip()

    def _blank_line(self) -> None:
        self.parts.append("\n\n")


def html_to_text(content: str) -> str:
    parser = _TextExtractor()
    parser.feed(content)
    return parser.text()


def _normalize_image_src(src: str) -> str:
    if not src:
        return ""
    if src.startswith("//"):
        return f"https:{src}"
    if src.startswith("/"):
        return f"https://leetcode.cn{src}"
    return src


def _markdown_alt(alt: str) -> str:
    return html.unescape(alt or "题目图片").replace("[", "(").replace("]", ")")


def _format_problem_line(line: str) -> str:
    if re.fullmatch(r"(示例\s*\d+：|提示：)", line):
        return f"**{line}**"
    match = re.match(r"^(输入|输出|解释|进阶|说明)：\s*(.*)$", line)
    if not match:
        return line
    label, rest = match.groups()
    return f"**{label}：** {rest}".rstrip()


def fetch_chinese_problem(title_slug: str) -> tuple[str | None, str | None]:
    body = json.dumps(
        {
            "query": """
            query questionData($titleSlug: String!) {
              question(titleSlug: $titleSlug) {
                translatedTitle
                translatedContent
              }
            }
            """,
            "variables": {"titleSlug": title_slug},
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        "https://leetcode.cn/graphql/",
        data=body,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0",
        },
    )
    with urllib.request.urlopen(request, timeout=12) as response:
        payload = json.loads(response.read().decode("utf-8"))
    question = payload.get("data", {}).get("question")
    if not question:
        return None, None
    title = question.get("translatedTitle")
    content = question.get("translatedContent")
    return title, html_to_text(content) if content else None


def fetch_chinese_titles(title_slugs: list[str]) -> dict[str, str]:
    if not title_slugs:
        return {}
    query_parts = []
    for index, slug in enumerate(title_slugs):
        query_parts.append(
            f'q{index}: question(titleSlug: {json.dumps(slug)}) {{ translatedTitle }}'
        )
    body = json.dumps({"query": "query {" + "\n".join(query_parts) + "}"}).encode("utf-8")
    request = urllib.request.Request(
        "https://leetcode.cn/graphql/",
        data=body,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0",
        },
    )
    with urllib.request.urlopen(request, timeout=12) as response:
        payload = json.loads(response.read().decode("utf-8"))
    data = payload.get("data", {})
    titles: dict[str, str] = {}
    for index, slug in enumerate(title_slugs):
        title = (data.get(f"q{index}") or {}).get("translatedTitle")
        if title:
            titles[slug] = title
    return titles
