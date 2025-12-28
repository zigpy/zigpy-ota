"""Shared utilities for markdown generation."""

from __future__ import annotations


def format_hex_dec(value: int, hex_width: str) -> str:
    """Format an integer as both hexadecimal and decimal for markdown."""
    return f"`0x{value:{hex_width}}` ({value})"


def format_list_or_str(value: tuple[str, ...] | list[str] | str) -> str:
    """Format a tuple, list, or string value for markdown display."""
    return ", ".join(value) if isinstance(value, (list, tuple)) else value
