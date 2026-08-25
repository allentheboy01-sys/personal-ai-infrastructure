import pytest

from jarvis.web_access.contract import MAX_EXTRACTED_TEXT_CHARS, WebAccessError
from jarvis.web_access.extraction import extract_readable


def test_html_extracts_title_and_readable_text_without_script_or_style() -> None:
    body = b"<html><head><title> Test Page </title><style>secret-css</style></head><body><h1>Hello</h1><script>steal()</script><p>World</p></body></html>"
    title, content, truncated = extract_readable(body, "text/html; charset=utf-8")
    assert title == "Test Page"
    assert content == "Test Page Hello World"
    assert "steal" not in content and "secret-css" not in content
    assert truncated is False


def test_malformed_and_large_html_is_deterministically_bounded() -> None:
    body = ("<div>" + "内容 " * 20_000 + "<script>ignored").encode()
    _title, content, truncated = extract_readable(body, "text/html")
    assert len(content) == MAX_EXTRACTED_TEXT_CHARS
    assert truncated is True
    assert "ignored" not in content


@pytest.mark.parametrize("mime", ["text/plain", "text/markdown", "application/json"])
def test_allowed_non_html_text_is_bounded(mime: str) -> None:
    title, content, truncated = extract_readable(b"  hello  ", mime)
    assert (title, content, truncated) == (None, "hello", False)


def test_unknown_charset_fails_closed() -> None:
    with pytest.raises(WebAccessError) as caught:
        extract_readable(b"hello", "text/plain; charset=big5")
    assert caught.value.code == "unsupported_mime"
