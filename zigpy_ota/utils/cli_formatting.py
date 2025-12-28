"""CLI formatting utilities for colored logging output."""

from __future__ import annotations

import logging

import click


# TODO: See if we want to keep this or use something existing instead?
class ColoredFormatter(logging.Formatter):
    """Custom formatter that adds colors to log messages using click."""

    COLORS = {
        "DEBUG": "cyan",
        "INFO": "blue",
        "WARNING": "yellow",
        "ERROR": "red",
        "CRITICAL": "red",
    }

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record with colored level name."""
        log_color = self.COLORS.get(record.levelname, "white")
        levelname = click.style(f"{record.levelname:8}", fg=log_color, bold=True)
        message = super().format(record)
        # Replace the levelname in the formatted message with the colored version
        return message.replace(record.levelname, levelname, 1)


def setup_logging() -> None:
    """Configure colored logging for the CLI."""
    handler = logging.StreamHandler()
    handler.setFormatter(ColoredFormatter("%(levelname)s: %(message)s"))

    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)
