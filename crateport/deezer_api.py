"""Deezer REST API client with transparent local caching.

Public API endpoints do *not* require authentication.
Authenticated endpoints (create/modify playlists) need an OAuth access token
obtained via the :mod:`auth` module.

Reference: https://developers.deezer.com/api
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

import requests
from sqlalchemy.orm import Session

from .artist_resolver import resolve_artist
from .database import get_session, is_fresh
from .models import (Album, Artist, Track, artist_search_results,
                     artist_top_tracks)

logger = logging.getLogger(__name__)

_BASE = "https://api.deezer.com"
_DEFAULT_TOP_LIMIT = 100
_RATE_LIMIT_DELAY = 0.3  # seconds between requests to stay well under limits


class DeezerAPIError(Exception):
    """Raised when the Deezer API returns an error payload."""


class DeezerTimeoutError(Exception):
    """Raised when the Deezer API times out."""


class DeezerClient:
    """Thin wrapper around the Deezer REST API with SQLAlchemy caching."""

    def __init__(self, access_token: str | None = None) -> None:
        self._token = access_token
        self._session = requests.Session()
        self._session.headers["Accept"] = "application/json"

    # ------------------------------------------------------------------
    # Low-level HTTP helpers
    # ------------------------------------------------------------------

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """Perform a GET request and return the parsed JSON body."""
        url = f"{_BASE}{path}"
        p: dict[str, Any] = params or {}
        if self._token:
            p["access_token"] = self._token
        logger.debug("GET %s %s", url, p)
        time.sleep(_RATE_LIMIT_DELAY)
        try:
            resp = self._session.get(url, params=p, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict) and "error" in data:
                err = data["error"]
                raise DeezerAPIError(
                    f"{err.get('type', 'Error')} {err.get('code')}: {err.get('message')}"
                )
            return data
        except (requests.Timeout, requests.ConnectionError) as exc:
            logger.warning("Deezer API timeout/connection error for %s: %s", url, exc)
            raise DeezerTimeoutError(f"Timeout/connection error: {exc}") from exc
        except requests.RequestException as exc:
            logger.warning("Deezer API error for %s: %s", url, exc)
            raise DeezerAPIError(f"Request error: {exc}") from exc

    def _post(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = f"{_BASE}{path}"
        p: dict[str, Any] = params or {}
        if self._token:
            p["access_token"] = self._token
        logger.debug("POST %s %s", url, p)
        try:
            resp = self._session.post(url, params=p, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict) and "error" in data:
                err = data["error"]
                raise DeezerAPIError(
                    f"{err.get('type', 'Error')} {err.get('code')}: {err.get('message')}"
                )
            return data
        except (requests.Timeout, requests.ConnectionError) as exc:
            logger.warning("Deezer API timeout/connection error for %s: %s", url, exc)
            raise DeezerTimeoutError(f"Timeout/connection error: {exc}") from exc
        except requests.RequestException as exc:
            logger.warning("Deezer API error for %s: %s", url, exc)
            raise DeezerAPIError(f"Request error: {exc}") from exc

    # ------------------------------------------------------------------
    # Artist
    # ------------------------------------------------------------------

    def search_artist(  # pylint: disable=too-many-return-statements
        self, name: str, interactive: bool = False
    ) -> Artist | None:
        """Return the best-matching :class:`~models.Artist` for *name*.

        Results are cached by artist ID; a fresh cached entry is returned
        without hitting the API.

        When multiple artists match the exact name:
        - If *interactive* is False (default): selects the one with the most
          fans (highest popularity).
        - If *interactive* is True: prompts the user to choose.

        Parameters
        ----------
        name:
            The artist name to search for.
        interactive:
            If True, prompts the user when multiple exact matches exist.
            If False, automatically selects the most popular.
        """
        with get_session() as db:
            # Check if we have cached search results
            cached_candidates = _get_cached_artist_ids_for_search(db, name)

            # If single cached match and not interactive: use directly
            if cached_candidates and len(cached_candidates) == 1 and not interactive:
                artist = db.get(Artist, cached_candidates[0]["id"])
                if artist and is_fresh(artist.cached_at):
                    logger.debug(
                        "Cache hit (single match): artist %r (id=%s)",
                        name,
                        cached_candidates[0]["id"],
                    )
                    return artist

            # If multiple cached + interactive: ask again (user might want different one)
            if cached_candidates and len(cached_candidates) > 1 and interactive:
                logger.debug("Cache hit (multiple matches): showing choices again")
                chosen = resolve_artist(
                    name, cached_candidates, always_select_first=False
                )
                if chosen is None:
                    logger.info("User skipped artist selection for %r", name)
                    return None
                artist = db.get(Artist, chosen["id"])
                if artist:
                    logger.debug("Cache hit (user selected): artist %r", name)
                    return artist

            # Not in cache, stale, or need fresh data: query API
            try:
                data = self._get("/search/artist", {"q": name, "limit": 5})
            except DeezerTimeoutError:
                logger.warning("Deezer timeout while searching for artist: %r", name)
                # Fall back to first cached artist on timeout
                if cached_candidates:
                    artist = db.get(Artist, cached_candidates[0]["id"])
                    if artist:
                        logger.debug("Timeout fallback: using cached artist %r", name)
                        return artist
                return None
            except DeezerAPIError:
                return None

            items = data.get("data", [])
            if not items:
                logger.warning("No artist found for %r", name)
                return None

            # Find all exact name matches (case-insensitive)
            q = name.casefold()
            exact_matches = [
                item for item in items if item.get("name", "").casefold() == q
            ]

            # If no exact matches, try fuzzy matching with decreasing thresholds
            if not exact_matches:
                logger.debug("No exact match for %r, trying fuzzy matching", name)
                fuzzy_90 = _fuzzy_match(items, name, key="name", threshold=0.90)
                fuzzy_80 = _fuzzy_match(items, name, key="name", threshold=0.80)

                if fuzzy_90:
                    logger.info(
                        "Found fuzzy match (90%%) for %r: %r",
                        name,
                        fuzzy_90.get("name"),
                    )
                    exact_matches = [fuzzy_90]
                elif fuzzy_80:
                    logger.info(
                        "Found fuzzy match (80%%) for %r: %r",
                        name,
                        fuzzy_80.get("name"),
                    )
                    exact_matches = [fuzzy_80]
                else:
                    logger.warning(
                        "No artist match (exact or fuzzy) for %r (candidates: %s)",
                        name,
                        [i.get("name") for i in items],
                    )
                    return None

            # Enrich matches with full artist data (incl. nb_fan)
            enriched_matches = []
            for match in exact_matches:
                full_data = self._get(f"/artist/{match['id']}")
                enriched_matches.append(full_data)
                # Cache all matches for future reference
                _cache_artist_search_result(db, name, full_data["id"])

            # Choose the best match
            if len(enriched_matches) == 1:
                best = enriched_matches[0]
                # If this was a fuzzy match, ask user for confirmation
                if enriched_matches[0].get("name", "").casefold() != name.casefold():
                    import click

                    msg = (
                        f"Did you mean '{enriched_matches[0].get('name')}'? "
                        f"[y/n, default=y]: "
                    )
                    confirmed = click.confirm(msg, default=True)
                    if not confirmed:
                        logger.info("User rejected fuzzy match for %r", name)
                        return None
                logger.debug("Selected artist: %r", name)
            else:
                # Multiple matches: ask user (if interactive) or auto-select
                best = resolve_artist(
                    name,
                    enriched_matches,
                    always_select_first=not interactive,
                )
                if best is None:
                    logger.info("User skipped artist selection for %r", name)
                    return None

            artist = _upsert_artist(db, best)
            db.commit()
            return artist

    def get_artist_top_tracks(
        self, artist_id: int, limit: int = _DEFAULT_TOP_LIMIT
    ) -> list[Track]:
        """Return (and cache) the top *limit* tracks for the given artist."""
        with get_session() as db:
            artist: Artist | None = db.get(Artist, artist_id)
            if artist and is_fresh(artist.cached_at):
                existing = (
                    db.query(Track)
                    .join(artist_top_tracks, Track.id == artist_top_tracks.c.track_id)
                    .filter(artist_top_tracks.c.artist_id == artist_id)
                    .limit(limit)
                    .all()
                )
                # Only accept the cache when it holds at least as many tracks as
                # requested.  A previous run with a smaller --limit stores fewer
                # rows; in that case we fall through and re-query the API.
                if len(existing) >= limit:
                    logger.debug("Cache hit: top tracks for artist %s", artist_id)
                    return existing

            try:
                data = self._get(f"/artist/{artist_id}/top", {"limit": limit})
            except (DeezerTimeoutError, DeezerAPIError) as exc:
                logger.warning(
                    "Deezer API error fetching top tracks for artist %s: %s",
                    artist_id,
                    exc,
                )
                return []

            items = data.get("data", [])
            tracks: list[Track] = []
            for item in items:
                track = _upsert_track(db, item)
                tracks.append(track)
                # Ensure the association row exists
                exists = db.execute(
                    artist_top_tracks.select().where(
                        artist_top_tracks.c.artist_id == artist_id,
                        artist_top_tracks.c.track_id == track.id,
                    )
                ).first()
                if not exists:
                    db.execute(
                        artist_top_tracks.insert().values(
                            artist_id=artist_id, track_id=track.id
                        )
                    )
        # Session is closed; enrich in separate per-track sessions
        tracks = self.enrich_isrcs(tracks)
        return tracks

    # ------------------------------------------------------------------
    # Album
    # ------------------------------------------------------------------

    def search_album(self, title: str, artist: str | None = None) -> Album | None:
        """Return the best-matching :class:`~models.Album` for *title*."""
        query = f'album:"{title}"'
        if artist:
            query += f' artist:"{artist}"'

        with get_session() as db:
            # Check cache first
            q = db.query(Album).filter(Album.title.ilike(title))
            if artist:
                q = q.join(Artist, Album.artist_id == Artist.id).filter(
                    Artist.name.ilike(artist)
                )
            cached = q.first()
            if cached and is_fresh(cached.cached_at):
                logger.debug("Cache hit: album %r", title)
                return cached

            try:
                data = self._get("/search/album", {"q": query, "limit": 5})
            except (DeezerTimeoutError, DeezerAPIError) as exc:
                logger.warning(
                    "Deezer API error searching for album %r: %s", title, exc
                )
                return None

            items = data.get("data", [])
            if not items:
                logger.warning("No album found for %r", title)
                return None

            best = _best_match(items, title, key="title")
            if best is None:
                logger.warning(
                    "No exact album match for %r (candidates: %s)",
                    title,
                    [i.get("title") for i in items],
                )
                return None
            album = _upsert_album(db, best)
            return album

    def get_album_tracks(self, album_id: int) -> list[Track]:
        """Return (and cache) all tracks for the given album."""
        with get_session() as db:
            album: Album | None = db.get(Album, album_id)
            if album and is_fresh(album.cached_at):
                existing = db.query(Track).filter(Track.album_id == album_id).all()
                if existing:
                    logger.debug("Cache hit: tracks for album %s", album_id)
                    return existing

            try:
                data = self._get(f"/album/{album_id}/tracks")
            except (DeezerTimeoutError, DeezerAPIError) as exc:
                logger.warning(
                    "Deezer API error fetching album tracks for album %s: %s",
                    album_id,
                    exc,
                )
                return []

            items = data.get("data", [])
            tracks = [_upsert_track(db, item, album_id=album_id) for item in items]
        # Session is closed; enrich in separate per-track sessions
        tracks = self.enrich_isrcs(tracks)
        return tracks

    # ------------------------------------------------------------------
    # Track (full object)
    # ------------------------------------------------------------------

    def get_track(self, track_id: int) -> Track | None:
        """Return the full track object for *track_id*, including ISRC.

        Skips the API call when the cached record already has an ISRC.
        """
        with get_session() as db:
            cached: Track | None = db.get(Track, track_id)
            if cached and cached.isrc and is_fresh(cached.cached_at):
                logger.debug("Cache hit (isrc): track %s", track_id)
                return cached

            try:
                data = self._get(f"/track/{track_id}")
            except (DeezerTimeoutError, DeezerAPIError) as exc:
                logger.warning("Deezer API error fetching track %s: %s", track_id, exc)
                return None

            track = _upsert_track(db, data)
            return track

    def enrich_isrcs(self, tracks: list[Track]) -> list[Track]:
        """Fetch full track details for every track that is missing an ISRC.

        Tracks that already have an ISRC are returned unchanged without any
        API call.  Updated :class:`~models.Track` instances are returned in
        the same order.
        """
        enriched: list[Track] = []
        for track in tracks:
            if track.isrc:
                enriched.append(track)
            else:
                full = self.get_track(track.id)
                enriched.append(full if full is not None else track)
        return enriched

    # ------------------------------------------------------------------
    # Track search
    # ------------------------------------------------------------------

    def get_track_by_isrc(self, isrc: str) -> Track | None:
        """Look up a Deezer track directly by ISRC.

        Uses the ``/track/isrc/{isrc}`` endpoint which is an exact lookup.
        Returns ``None`` when the ISRC is not in Deezer's catalogue.
        """
        with get_session() as db:
            cached = db.query(Track).filter(Track.isrc == isrc).first()
            if cached and is_fresh(cached.cached_at):
                logger.debug("Cache hit (isrc lookup): %s", isrc)
                return cached
        try:
            data = self._get(f"/track/isrc/{isrc}")
        except DeezerTimeoutError:
            logger.debug("Deezer timeout for ISRC %s", isrc)
            return None
        except DeezerAPIError as exc:
            logger.debug("ISRC %s not found on Deezer: %s", isrc, exc)
            return None
        if not isinstance(data, dict) or "id" not in data:
            return None
        with get_session() as db:
            track = _upsert_track(db, data)
        return track

    def search_track_candidates(
        self,
        title: str,
        artist: str | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Return up to *limit* raw Deezer search results for *title* / *artist*.

        Unlike :meth:`search_track`, nothing is persisted and no "best match"
        heuristic is applied, so the caller can do interactive disambiguation.
        Each result dict contains at minimum: ``id``, ``title``, ``artist``
        (nested dict with ``name``), ``album`` (nested dict with ``title``).
        The ``isrc`` key is **absent** from bulk search results; call
        :meth:`get_track` on the chosen ID to retrieve a full ISRC.
        """
        query = f'track:"{title}"'
        if artist:
            query += f' artist:"{artist}"'
        try:
            data = self._get("/search/track", {"q": query, "limit": limit})
        except (DeezerTimeoutError, DeezerAPIError) as exc:
            logger.warning("Deezer API error searching for track %r: %s", title, exc)
            return []
        return data.get("data", [])

    def search_track(
        self,
        title: str,
        artist: str | None = None,
        album: str | None = None,
        isrc: str | None = None,
    ) -> Track | None:
        """Return the best-matching :class:`~models.Track`."""
        with get_session() as db:
            # ISRC is a perfect identifier – check cache first
            if isrc:
                cached = db.query(Track).filter(Track.isrc == isrc).first()
                if cached and is_fresh(cached.cached_at):
                    return cached

            query = f'track:"{title}"'
            if artist:
                query += f' artist:"{artist}"'
            if album:
                query += f' album:"{album}"'

            try:
                data = self._get("/search/track", {"q": query, "limit": 5})
            except (DeezerTimeoutError, DeezerAPIError) as exc:
                logger.warning(
                    "Deezer API error searching for track %r: %s", title, exc
                )
                return None

            items = data.get("data", [])
            if not items:
                logger.warning("No track found for %r (artist=%r)", title, artist)
                return None

            best = _best_match(items, title, key="title")
            if best is None:
                logger.warning(
                    "No exact track match for %r (candidates: %s)",
                    title,
                    [i.get("title") for i in items],
                )
                return None
            track = _upsert_track(db, best)
        # Session is closed; enrich if ISRC missing
        if not track.isrc:
            track = self.get_track(track.id) or track
        return track

    # ------------------------------------------------------------------
    # Playlist management (requires auth)
    # ------------------------------------------------------------------

    def create_playlist(self, user_id: int | str, title: str) -> int | None:
        """Create a new Deezer playlist and return its ID, or None on error."""
        try:
            data = self._post(f"/user/{user_id}/playlists", {"title": title})
            return int(data["id"])
        except (DeezerTimeoutError, DeezerAPIError) as exc:
            logger.warning(
                "Deezer API error creating playlist for user %s: %s", user_id, exc
            )
            return None

    def add_tracks_to_playlist(self, playlist_id: int, track_ids: list[int]) -> bool:
        """Add tracks to a Deezer playlist (max 1000 IDs per call)."""
        try:
            songs = ",".join(str(t) for t in track_ids)
            self._post(f"/playlist/{playlist_id}/tracks", {"songs": songs})
            return True
        except (DeezerTimeoutError, DeezerAPIError) as exc:
            logger.warning(
                "Deezer API error adding tracks to playlist %s: %s", playlist_id, exc
            )
            return False

    def update_playlist(
        self,
        playlist_id: int,
        *,
        description: str | None = None,
        public: bool | None = None,
    ) -> bool:
        """Update playlist metadata."""
        try:
            params: dict[str, Any] = {}
            if description is not None:
                params["description"] = description
            if public is not None:
                params["public"] = 1 if public else 0
            if params:
                self._post(f"/playlist/{playlist_id}", params)
            return True
        except (DeezerTimeoutError, DeezerAPIError) as exc:
            logger.warning(
                "Deezer API error updating playlist %s: %s", playlist_id, exc
            )
            return False

    def get_me(self) -> dict[str, Any] | None:
        """Return the authenticated user's profile, or None on error."""
        try:
            return self._get("/user/me")
        except (DeezerTimeoutError, DeezerAPIError) as exc:
            logger.warning("Deezer API error fetching user profile: %s", exc)
            return None


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _best_match(items: list[dict], query: str, *, key: str) -> dict | None:
    """Return the item whose *key* field best matches *query* (case-insensitive).

    Returns the first exact (case-insensitive) match, or ``None`` when no
    candidate matches.  The previous behaviour of falling back to ``items[0]``
    caused unrelated artists/tracks to silently pollute generated playlists
    whenever the searched name was not present in the result set.
    """
    q = query.casefold()
    for item in items:
        if item.get(key, "").casefold() == q:
            return item
    return None


def _fuzzy_match(
    items: list[dict], query: str, *, key: str, threshold: float = 0.9
) -> dict | None:
    """Return the best-matching item using fuzzy string matching.

    Finds the item with the highest similarity to query (case-insensitive).
    Returns the best match only if similarity >= threshold, else None.

    Parameters
    ----------
    items:
        List of dictionaries to search
    query:
        The query string to match
    key:
        The dictionary key to match against
    threshold:
        Minimum similarity (0.0-1.0) to accept a match
    """
    from difflib import SequenceMatcher

    q = query.casefold()
    best_item = None
    best_ratio = 0.0

    for item in items:
        candidate = item.get(key, "").casefold()
        ratio = SequenceMatcher(None, q, candidate).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_item = item

    return best_item if best_ratio >= threshold else None


def _find_artist_by_name(db: Session, name: str) -> Artist | None:
    return db.query(Artist).filter(Artist.name.ilike(name)).first()


def _get_cached_artist_ids_for_search(
    db: Session, search_name: str
) -> list[dict] | None:
    """Return cached artist candidates for a search name with full data.

    Returns list of dicts {id, name, nb_fan, link} or None if cache is stale.
    """
    results = (
        db.query(artist_search_results.c.artist_id)
        .filter(artist_search_results.c.search_name.ilike(search_name))
        .all()
    )
    if not results:
        return None

    artist_ids = [r[0] for r in results]
    # Check if cache is fresh (all from same search)
    if not is_fresh(_get_cache_timestamp(db, search_name, artist_ids[0])):
        return None

    # Get full artist data
    artists = [db.get(Artist, aid) for aid in artist_ids]
    artists = [a for a in artists if a is not None]

    return [
        {
            "id": a.id,
            "name": a.name,
            "nb_fan": a.nb_fan,
            "link": a.link,
        }
        for a in artists
    ]


def _get_cache_timestamp(db: Session, search_name: str, artist_id: int) -> datetime:
    """Get the cache timestamp for a specific search result."""
    result = (
        db.query(artist_search_results.c.cached_at)
        .filter(
            artist_search_results.c.search_name.ilike(search_name),
            artist_search_results.c.artist_id == artist_id,
        )
        .first()
    )
    return result[0] if result else datetime.now(timezone.utc)


def _cache_artist_search_result(db: Session, search_name: str, artist_id: int) -> None:
    """Cache a search result mapping search_name to artist_id.

    Ignores duplicates (same name+id already cached).
    """
    # Check before insert to avoid unique constraint violation
    existing = (
        db.query(artist_search_results.c.artist_id)
        .filter(
            artist_search_results.c.search_name.ilike(search_name),
            artist_search_results.c.artist_id == artist_id,
        )
        .first()
    )
    if not existing:
        db.execute(
            artist_search_results.insert().values(
                search_name=search_name, artist_id=artist_id
            )
        )


def _upsert_artist(db: Session, data: dict) -> Artist:
    artist = Artist(
        id=data["id"],
        name=data["name"],
        picture=data.get("picture_medium") or data.get("picture"),
        nb_fan=data.get("nb_fan"),
        link=data.get("link"),
        cached_at=datetime.now(timezone.utc),
    )
    return db.merge(artist)


def _upsert_album(db: Session, data: dict, artist_id: int | None = None) -> Album:
    if "artist" in data and isinstance(data["artist"], dict):
        art = _upsert_artist(db, data["artist"])
        artist_id = art.id
    album = Album(
        id=data["id"],
        title=data["title"],
        artist_id=artist_id,
        cover=data.get("cover_medium") or data.get("cover"),
        upc=data.get("upc"),
        nb_tracks=data.get("nb_tracks"),
        cached_at=datetime.now(timezone.utc),
    )
    return db.merge(album)


def _upsert_track(db: Session, data: dict, album_id: int | None = None) -> Track:
    # Resolve nested artist/album if present
    art_id: int | None = None
    if "artist" in data and isinstance(data["artist"], dict):
        art = _upsert_artist(db, data["artist"])
        art_id = art.id
    alb_id = album_id
    if alb_id is None and "album" in data and isinstance(data["album"], dict):
        alb = _upsert_album(db, data["album"])
        alb_id = alb.id
    # Preserve a stored ISRC when the incoming data lacks one.
    # Bulk endpoints (/artist/{id}/top, /album/{id}/tracks) omit isrc; the
    # full /track/{id} object includes it.  We must not overwrite a good ISRC
    # with None on a second fetch.
    isrc = data.get("isrc")
    if not isrc:
        existing = db.get(Track, data["id"])
        if existing:
            isrc = existing.isrc
    track = Track(
        id=data["id"],
        title=data["title"],
        artist_id=art_id,
        album_id=alb_id,
        duration=data.get("duration"),
        isrc=isrc,
        rank=data.get("rank"),
        preview=data.get("preview"),
        link=data.get("link"),
        cached_at=datetime.now(timezone.utc),
    )
    return db.merge(track)
