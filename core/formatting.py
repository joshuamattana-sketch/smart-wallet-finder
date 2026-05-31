"""
core/formatting.py
------------------
Number, address, and display formatters for the Pro Trading Terminal.

Rules:
- No Streamlit imports.
- No network calls.
- No external dependencies.
- All functions are pure Python.
- Never raise on bad input — return safe defaults.
- These are the canonical formatters. Import from here, not from app.py.
"""

from typing import Union

Number = Union[int, float, str, None]


# ── Type coercions ─────────────────────────────────────────────────────────────

def safe_float(value: object, default: float = 0.0) -> float:
    """
    Coerce any value to float, returning default on failure.

    Never raises. Handles None, empty strings, and non-numeric strings.

    Args:
        value:   Any object to coerce.
        default: Value to return on failure. Default 0.0.

    Returns:
        float

    Examples:
        >>> safe_float("3.14")
        3.14
        >>> safe_float(None)
        0.0
        >>> safe_float("not a number", default=-1.0)
        -1.0
        >>> safe_float("")
        0.0
    """
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def safe_int(value: object, default: int = 0) -> int:
    """
    Coerce any value to int, returning default on failure.

    Handles floats (truncates), strings, and None. Never raises.

    Args:
        value:   Any object to coerce.
        default: Value to return on failure. Default 0.

    Returns:
        int

    Examples:
        >>> safe_int("42")
        42
        >>> safe_int(3.9)
        3
        >>> safe_int(None)
        0
        >>> safe_int("bad", default=-1)
        -1
    """
    if value is None:
        return default
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return default


# ── Address formatting ─────────────────────────────────────────────────────────

def compact_address(value: object, front: int = 6, back: int = 4) -> str:
    """
    Shorten a wallet or token address for display.

    Returns the first `front` and last `back` characters separated by "...".
    If the address is too short to shorten, returns it as-is.

    Args:
        value: Address string. Non-strings are converted via str().
        front: Characters to show at the start. Default 6.
        back:  Characters to show at the end. Default 4.

    Returns:
        Shortened address string, e.g. "GS4CU...QnaR".
        Empty string if value is None or empty.

    Examples:
        >>> compact_address("GS4CUS5NVQnaR1234567890abcdefghijklmnopqr")
        'GS4CUS...opqr'
        >>> compact_address("short")
        'short'
        >>> compact_address(None)
        ''
        >>> compact_address("0xAbCd1234", front=4, back=4)
        '0xAb...1234'
    """
    if value is None:
        return ""
    s = str(value).strip()
    if not s:
        return ""
    min_len = front + back + 3  # 3 for "..."
    if len(s) <= min_len:
        return s
    return f"{s[:front]}...{s[-back:]}"


# ── Currency formatting ────────────────────────────────────────────────────────

def format_usd(value: object) -> str:
    """
    Format a number as a USD currency string.

    Automatically picks the right precision based on magnitude:
    - >= 1000: no decimals, with thousands separator (e.g. "$1,234")
    - >= 1: 2 decimals (e.g. "$3.14")
    - >= 0.01: 4 decimals (e.g. "$0.0032")
    - < 0.01: 8 decimals (e.g. "$0.00000042")

    Handles negatives with leading minus sign.

    Args:
        value: Any numeric value or string. Non-numeric returns "$0.00".

    Returns:
        Formatted USD string.

    Examples:
        >>> format_usd(1234567.89)
        '$1,234,568'
        >>> format_usd(3.14159)
        '$3.14'
        >>> format_usd(0.003456)
        '$0.0035'
        >>> format_usd(0.000000042)
        '$0.00000004'
        >>> format_usd(-150.5)
        '-$150.50'
        >>> format_usd(None)
        '$0.00'
    """
    v = safe_float(value)
    negative = v < 0
    abs_v = abs(v)

    if abs_v >= 1_000:
        formatted = f"${abs_v:,.0f}"
    elif abs_v >= 1:
        formatted = f"${abs_v:.2f}"
    elif abs_v >= 0.01:
        formatted = f"${abs_v:.4f}"
    elif abs_v > 0:
        formatted = f"${abs_v:.8f}"
    else:
        formatted = "$0.00"

    return f"-{formatted}" if negative else formatted


def format_pct(value: object, decimals: int = 1, signed: bool = True) -> str:
    """
    Format a number as a percentage string.

    Args:
        value:    Numeric value representing a percentage (e.g. 12.5 for 12.5%).
        decimals: Decimal places. Default 1.
        signed:   If True, prefix positive values with "+". Default True.

    Returns:
        Formatted percentage string, e.g. "+12.5%", "-3.2%", "0.0%".

    Examples:
        >>> format_pct(12.5)
        '+12.5%'
        >>> format_pct(-3.2)
        '-3.2%'
        >>> format_pct(0.0)
        '+0.0%'
        >>> format_pct(12.5, signed=False)
        '12.5%'
        >>> format_pct(None)
        '+0.0%'
    """
    v = safe_float(value)
    if signed:
        return f"{v:+.{decimals}f}%"
    return f"{v:.{decimals}f}%"


def format_number(value: object, decimals: int = 2) -> str:
    """
    Format a plain number with thousands separators.

    Useful for swap counts, tx counts, and other non-currency numbers.

    Args:
        value:    Any numeric value. Non-numeric returns "0".
        decimals: Decimal places. Default 2. Set to 0 for integers.

    Returns:
        Formatted number string, e.g. "1,234.56", "42", "0.00".

    Examples:
        >>> format_number(1234567.89)
        '1,234,567.89'
        >>> format_number(42, decimals=0)
        '42'
        >>> format_number(None)
        '0.00'
        >>> format_number("bad input")
        '0.00'
    """
    v = safe_float(value)
    return f"{v:,.{decimals}f}"


if __name__ == "__main__":
    assert safe_float("3.14") == 3.14
    assert safe_float(None) == 0.0
    assert safe_float("bad", default=-1.0) == -1.0
    assert safe_int("42") == 42
    assert safe_int(3.9) == 3
    assert safe_int(None) == 0
    assert compact_address("GS4CUS5NVQnaR1234567890abcdefghijklmnopqr") == "GS4CUS...opqr"
    assert compact_address(None) == ""
    assert compact_address("short") == "short"
    assert format_usd(1234567.89) == "$1,234,568"
    assert format_usd(3.14) == "$3.14"
    assert format_usd(None) == "$0.00"
    assert format_usd(-150.5) == "-$150.50"
    assert format_pct(12.5) == "+12.5%"
    assert format_pct(-3.2) == "-3.2%"
    assert format_number(1234567.89) == "1,234,567.89"
    assert format_number(None) == "0.00"
    print("core/formatting.py — all assertions passed.")
