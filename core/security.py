"""
core/security.py
----------------
Security helpers for the Pro Trading Terminal.

Rules:
- No Streamlit imports.
- No network calls.
- No external dependencies.
- All functions are pure Python.
- Never silent-fail: raise ValueError on invalid input type where appropriate.
"""

import html
import re


def html_escape(value: object) -> str:
    """
    Escape a value for safe inclusion in HTML rendered by Streamlit
    unsafe_allow_html=True blocks.

    Always call this on any user-controlled string before inserting it
    into an f-string that ends up in st.markdown(..., unsafe_allow_html=True).

    Args:
        value: Any value. Will be converted to str first.

    Returns:
        HTML-safe string with &, <, >, ", ' escaped.

    Examples:
        >>> html_escape('<script>alert(1)</script>')
        '&lt;script&gt;alert(1)&lt;/script&gt;'
        >>> html_escape(None)
        ''
        >>> html_escape(42)
        '42'
    """
    if value is None:
        return ""
    return html.escape(str(value), quote=True)


def safe_text(value: object, max_len: int = 500) -> str:
    """
    Convert value to a clean, HTML-safe string truncated to max_len.

    Use for: wallet descriptions, token names, user notes shown in HTML.

    Args:
        value:   Any value. None becomes empty string.
        max_len: Maximum character length before truncation. Default 500.

    Returns:
        HTML-escaped string, max max_len characters, trailing whitespace stripped.

    Raises:
        ValueError: if max_len < 1.

    Examples:
        >>> safe_text("  hello world  ")
        'hello world'
        >>> safe_text("a" * 600, max_len=10)
        'aaaaaaaaaa'
        >>> safe_text(None)
        ''
    """
    if max_len < 1:
        raise ValueError(f"max_len must be >= 1, got {max_len}")
    if value is None:
        return ""
    text = str(value).strip()
    if len(text) > max_len:
        text = text[:max_len]
    return html_escape(text)


def safe_label(value: object, max_len: int = 80) -> str:
    """
    Produce a short, HTML-safe label suitable for badges, headings, pills.

    Strips to max_len, removes newlines and tab characters.

    Args:
        value:   Any value. None becomes empty string.
        max_len: Maximum character length. Default 80.

    Returns:
        Single-line HTML-escaped string.

    Raises:
        ValueError: if max_len < 1.

    Examples:
        >>> safe_label("Alpha Scout XUEB")
        'Alpha Scout XUEB'
        >>> safe_label("line1\\nline2")
        'line1 line2'
        >>> safe_label("a" * 100, max_len=20)
        'aaaaaaaaaaaaaaaaaaaa'
    """
    if max_len < 1:
        raise ValueError(f"max_len must be >= 1, got {max_len}")
    if value is None:
        return ""
    text = re.sub(r"[\r\n\t]+", " ", str(value)).strip()
    if len(text) > max_len:
        text = text[:max_len]
    return html_escape(text)


def mask_secret(value: object, visible_chars: int = 4) -> str:
    """
    Mask a secret string for safe display in logs or UI debug panels.

    Shows the first `visible_chars` characters followed by asterisks.
    Values shorter than visible_chars are fully masked.

    Args:
        value:         The secret string to mask.
        visible_chars: Number of leading characters to show. Default 4.

    Returns:
        Masked string, e.g. "sk-p****" for an OpenAI key.

    Raises:
        ValueError: if visible_chars < 0.

    Examples:
        >>> mask_secret("sk-proj-abc123xyz")
        'sk-p*************'
        >>> mask_secret("short", visible_chars=0)
        '*****'
        >>> mask_secret(None)
        '****'
        >>> mask_secret("")
        ''
    """
    if visible_chars < 0:
        raise ValueError(f"visible_chars must be >= 0, got {visible_chars}")
    if value is None:
        return "****"
    text = str(value)
    if not text:
        return ""
    if len(text) <= visible_chars:
        return "*" * len(text)
    return text[:visible_chars] + "*" * (len(text) - visible_chars)


if __name__ == "__main__":
    # Quick smoke test
    assert html_escape('<b>test</b>') == '&lt;b&gt;test&lt;/b&gt;'
    assert html_escape(None) == ''
    assert safe_text("  hello  ", max_len=3) == 'hel'
    assert safe_label("line1\nline2") == 'line1 line2'
    assert mask_secret("sk-proj-abc123", visible_chars=4) == 'sk-p**********'
    assert mask_secret(None) == '****'
    assert mask_secret("") == ''
    print("core/security.py — all assertions passed.")
