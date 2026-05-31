"""
core/validators.py
------------------
Input validation for the Pro Trading Terminal.

Rules:
- No Streamlit imports.
- No network calls.
- No external dependencies beyond stdlib.
- All functions return bool, str, or raise ValueError — never None silently.
- Validation is strict: reject ambiguous input rather than guess.
"""

import re
from typing import Optional

# ── Address patterns ──────────────────────────────────────────────────────────

# Solana: base58, 32–44 characters, excludes 0, O, I, l
_SOLANA_ADDRESS_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")

# EVM (Ethereum/BSC/etc): 0x + 40 hex characters
_EVM_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")

# Supported chains (canonical lowercase names)
_SUPPORTED_CHAINS = {
    "solana", "ethereum", "bsc", "base", "arbitrum", "optimism", "polygon", "avalanche"
}

# Supported market types
_MARKET_TYPES = {"spot", "perp", "futures", "option"}

# Max lengths
_MAX_NOTE_LEN = 1_000
_MAX_SYMBOL_LEN = 20


def is_valid_solana_address(value: object) -> bool:
    """
    Return True if value is a syntactically valid Solana base58 address.

    Does NOT check if the address exists on-chain — that requires a network call.

    Args:
        value: Any object. Non-strings return False.

    Returns:
        True if the string matches Solana address format, False otherwise.

    Examples:
        >>> is_valid_solana_address("GS4CUS5NVQnaR1234567890abcdefghijklmnopqr")
        True
        >>> is_valid_solana_address("0x1234")
        False
        >>> is_valid_solana_address(None)
        False
        >>> is_valid_solana_address("")
        False
    """
    if not isinstance(value, str):
        return False
    return bool(_SOLANA_ADDRESS_RE.match(value.strip()))


def is_valid_evm_address(value: object) -> bool:
    """
    Return True if value is a syntactically valid EVM hex address.

    Accepts both checksummed and lowercase. Does NOT verify checksum.
    Does NOT check on-chain existence.

    Args:
        value: Any object. Non-strings return False.

    Returns:
        True if the string matches 0x + 40 hex chars, False otherwise.

    Examples:
        >>> is_valid_evm_address("0xAbCd1234567890abcdef1234567890abcdef1234")
        True
        >>> is_valid_evm_address("GS4CUS5NVQnaR")
        False
        >>> is_valid_evm_address(None)
        False
    """
    if not isinstance(value, str):
        return False
    return bool(_EVM_ADDRESS_RE.match(value.strip()))


def normalize_chain(value: object) -> str:
    """
    Normalize a chain name to lowercase canonical form.

    Maps common aliases to the canonical name used in SUPPORTED_CHAINS.

    Args:
        value: Chain name string (case-insensitive). Non-strings raise ValueError.

    Returns:
        Lowercase canonical chain name, e.g. "solana", "ethereum".

    Raises:
        ValueError: if value is not a string or chain is not recognized.

    Examples:
        >>> normalize_chain("SOL")
        'solana'
        >>> normalize_chain("ETH")
        'ethereum'
        >>> normalize_chain("Polygon")
        'polygon'
        >>> normalize_chain("unknownchain")  # raises
        Traceback (most recent call last):
            ...
        ValueError: Unrecognized chain: 'unknownchain'
    """
    if not isinstance(value, str):
        raise ValueError(f"Chain name must be a string, got {type(value).__name__}")

    aliases = {
        "sol": "solana",
        "eth": "ethereum",
        "bnb": "bsc",
        "matic": "polygon",
        "avax": "avalanche",
        "arb": "arbitrum",
        "op": "optimism",
    }

    normalized = value.strip().lower()
    normalized = aliases.get(normalized, normalized)

    if normalized not in _SUPPORTED_CHAINS:
        raise ValueError(f"Unrecognized chain: '{value}'")

    return normalized


def normalize_symbol(value: object) -> str:
    """
    Normalize a trading symbol to uppercase, stripping whitespace.

    Does not validate if the symbol exists on any exchange.

    Args:
        value: Trading symbol string (e.g. "btcusdt", "BTC/USDT"). Non-strings raise ValueError.

    Returns:
        Uppercase string with whitespace stripped, e.g. "BTCUSDT", "BTC/USDT".

    Raises:
        ValueError: if value is not a string, is empty, or exceeds max length.

    Examples:
        >>> normalize_symbol("btcusdt")
        'BTCUSDT'
        >>> normalize_symbol("  sol/usdt  ")
        'SOL/USDT'
        >>> normalize_symbol("")  # raises
        Traceback (most recent call last):
            ...
        ValueError: Symbol cannot be empty
    """
    if not isinstance(value, str):
        raise ValueError(f"Symbol must be a string, got {type(value).__name__}")

    stripped = value.strip().upper()

    if not stripped:
        raise ValueError("Symbol cannot be empty")
    if len(stripped) > _MAX_SYMBOL_LEN:
        raise ValueError(f"Symbol too long: {len(stripped)} chars (max {_MAX_SYMBOL_LEN})")

    return stripped


def validate_market_type(value: object) -> str:
    """
    Validate and normalize a market type string.

    Args:
        value: Market type string. Case-insensitive.

    Returns:
        Lowercase canonical market type: "spot", "perp", "futures", or "option".

    Raises:
        ValueError: if value is not a recognized market type.

    Examples:
        >>> validate_market_type("Spot")
        'spot'
        >>> validate_market_type("PERP")
        'perp'
        >>> validate_market_type("invalid")  # raises
        Traceback (most recent call last):
            ...
        ValueError: Invalid market type 'invalid'. Must be one of: futures, option, perp, spot
    """
    if not isinstance(value, str):
        raise ValueError(f"Market type must be a string, got {type(value).__name__}")

    normalized = value.strip().lower()

    if normalized not in _MARKET_TYPES:
        valid = ", ".join(sorted(_MARKET_TYPES))
        raise ValueError(f"Invalid market type '{value}'. Must be one of: {valid}")

    return normalized


def sanitize_user_note(value: object, max_len: int = _MAX_NOTE_LEN) -> str:
    """
    Sanitize a user-supplied note for safe storage and display.

    Strips leading/trailing whitespace, collapses excessive newlines,
    and truncates to max_len. Does NOT HTML-escape — use core/security.py
    for that before rendering in HTML.

    Args:
        value:   Any object. None or non-string returns empty string.
        max_len: Maximum character length. Default 1000.

    Returns:
        Cleaned string, at most max_len characters.

    Raises:
        ValueError: if max_len < 1.

    Examples:
        >>> sanitize_user_note("  good note  ")
        'good note'
        >>> sanitize_user_note("line1\\n\\n\\n\\nline2")
        'line1\\n\\nline2'
        >>> sanitize_user_note(None)
        ''
        >>> sanitize_user_note("a" * 2000, max_len=100)
        'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
    """
    if max_len < 1:
        raise ValueError(f"max_len must be >= 1, got {max_len}")
    if value is None or not isinstance(value, str):
        return ""

    # Strip outer whitespace
    text = value.strip()

    # Collapse 3+ consecutive newlines to 2
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Truncate
    return text[:max_len]


if __name__ == "__main__":
    assert is_valid_solana_address("GS4CU5NVQnaRabcdefghJKLMNPQRSTUVWXYZ") is True
    assert is_valid_solana_address("0x1234") is False
    assert is_valid_solana_address(None) is False
    assert is_valid_evm_address("0xAbCd1234567890abcdef1234567890abcdef1234") is True
    assert is_valid_evm_address("notanaddress") is False
    assert normalize_chain("SOL") == "solana"
    assert normalize_chain("ETH") == "ethereum"
    assert normalize_symbol("btcusdt") == "BTCUSDT"
    assert validate_market_type("PERP") == "perp"
    assert sanitize_user_note("  hi  ") == "hi"
    assert sanitize_user_note(None) == ""
    print("core/validators.py — all assertions passed.")
