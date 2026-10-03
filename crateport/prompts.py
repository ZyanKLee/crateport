"""Shared interactive prompts for user choice disambiguation."""

from __future__ import annotations

import click


def prompt_for_index(
    item_count: int,
    prompt_text: str = "Pick number, Enter=1, s=skip",
) -> int | None:
    """Repeatedly prompt user to pick an index from 1 to item_count.

    Returns the 0-based index (n - 1), or None if user enters 's' (skip).
    Loops until a valid choice is made.

    Parameters
    ----------
    item_count:
        Number of items to choose from (1-based display to user).
    prompt_text:
        The prompt message to show.

    Returns
    -------
    int or None
        0-based index if user picks a valid number (1 to item_count),
        or None if user skips (enters 's').
    """
    while True:
        raw = click.prompt(prompt_text, default="1", show_default=False).strip().lower()
        if raw == "s":
            return None
        try:
            n = int(raw)
            if 1 <= n <= item_count:
                return n - 1
        except ValueError:
            pass
        click.echo("  Invalid choice, try again.")
