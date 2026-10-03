"""Artist disambiguation when multiple exact name matches exist.

When searching for an artist by name, if multiple artists with the same
exact name (case-insensitive) are found, prompts the user to choose.
"""

from __future__ import annotations

from typing import Any

import click

from .prompts import prompt_for_index


def resolve_artist(
    name: str,
    candidates: list[dict[str, Any]],
    always_select_first: bool = False,
) -> dict[str, Any] | None:
    """Return the chosen artist candidate, or ``None`` if the user skips.

    When there are multiple exact name matches, prompts the user to pick one,
    unless *always_select_first* is ``True`` (in which case returns the most
    popular by fan count).

    Parameters
    ----------
    name:
        The artist name that was searched for.
    candidates:
        List of Deezer search results (from /search/artist endpoint).
    always_select_first:
        If True, automatically selects the most popular (by fan count)
        without prompting.

    Returns
    -------
    dict or None
        The chosen artist dict, or None if the user skips.
    """
    # Filter to exact name matches (case-insensitive)
    q = name.casefold()
    exact_matches = [c for c in candidates if c.get("name", "").casefold() == q]

    if not exact_matches:
        return None

    # Single match — use it
    if len(exact_matches) == 1:
        return exact_matches[0]

    # Multiple matches — disambiguate
    if always_select_first:
        # Pick the one with most fans
        chosen = max(exact_matches, key=lambda x: x.get("nb_fan", 0) or 0)
        click.echo(
            f"  → Auto-selected most popular: {chosen.get('name')} "
            f"({chosen.get('nb_fan', 0)} fans)"
        )
        return chosen

    # Interactive disambiguation
    click.echo(f"  Multiple artists named '{name}' found; pick one:")
    for idx, c in enumerate(exact_matches, 1):
        fans = c.get("nb_fan", 0) or 0
        link = c.get("link", "")
        click.echo(f"    [{idx}] {c.get('name')} – {fans} fans")
        if link:
            click.echo(f"         {link}")

    idx = prompt_for_index(len(exact_matches), "  Pick number, Enter=1, s=skip")
    if idx is not None:
        chosen = exact_matches[idx]
        click.echo(f"  → Selected: {chosen.get('name')}")
        return chosen
    return None
