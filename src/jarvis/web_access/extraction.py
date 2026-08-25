"""Bounded, deterministic, non-executing text extraction."""

from __future__ import annotations

import re
from html.parser import HTMLParser

from .contract import MAX_EXTRACTED_TEXT_CHARS, WebAccessError


_WHITESPACE = re.compile(r"\s+")
_BLOCK_TAGS = frozenset(
    {"address", "article", "aside", "blockquote", "br", "div", "footer", "h1", "h2", "h3", "h4", "h5", "h6", "header", "li", "main", "nav", "p", "pre", "section", "table", "td", "th", "tr"}
)
_SKIP_TAGS = frozenset({"script", "style", "noscript", "template", "svg", "canvas"})


class _ReadableHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._parts: list[str] = []
        self._title_parts: list[str] = []
        self._in_title = False

    def handle_starttag(self, tag: str, attrs) -> None:
        normalized = tag.lower()
        if normalized in _SKIP_TAGS:
            self._skip_depth += 1
        if self._skip_depth == 0 and normalized in _BLOCK_TAGS:
            self._parts.append("\n")
        if self._skip_depth == 0 and normalized == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.lower()
        if normalized in _SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
            return
        if self._skip_depth == 0 and normalized in _BLOCK_TAGS:
            self._parts.append("\n")
        if normalized == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._skip_depth or not data:
            return
        self._parts.append(data)
        if self._in_title:
            self._title_parts.append(data)

    def result(self) -> tuple[str | None, str, bool]:
        title = _WHITESPACE.sub(" ", " ".join(self._title_parts)).strip() or None
        content = _WHITESPACE.sub(" ", " ".join(self._parts)).strip()
        truncated = len(content) > MAX_EXTRACTED_TEXT_CHARS
        return title, content[:MAX_EXTRACTED_TEXT_CHARS], truncated


def decode_text(body: bytes, content_type: str) -> str:
    charset = "utf-8"
    for parameter in content_type.split(";")[1:]:
        name, separator, value = parameter.strip().partition("=")
        if separator and name.lower() == "charset":
            candidate = value.strip('"\'').lower()
            if candidate in {"utf-8", "utf8", "us-ascii", "ascii"}:
                charset = "utf-8" if candidate in {"utf-8", "utf8"} else "ascii"
            else:
                raise WebAccessError("unsupported_mime")
    try:
        return body.decode(charset, errors="strict")
    except UnicodeDecodeError:
        raise WebAccessError("unsupported_mime") from None


def extract_readable(body: bytes, content_type: str) -> tuple[str | None, str, bool]:
    mime = content_type.split(";", 1)[0].strip().lower()
    text = decode_text(body, content_type)
    if mime in {"text/html", "application/xhtml+xml"}:
        parser = _ReadableHTMLParser()
        try:
            parser.feed(text)
            parser.close()
        except (ValueError, RecursionError):
            raise WebAccessError("unsupported_mime") from None
        return parser.result()
    normalized = text.strip()
    truncated = len(normalized) > MAX_EXTRACTED_TEXT_CHARS
    return None, normalized[:MAX_EXTRACTED_TEXT_CHARS], truncated
