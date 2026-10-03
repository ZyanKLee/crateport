"""Playlist generation logic.

Resolves entries from a :class:`~input_parser.ParsedInput` to Deezer
:class:`~models.Track` objects and stores the resulting playlist in the
local database.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from .config import config
from .database import get_session
from .deezer_api import DeezerClient
from .input_parser import InputMode, ParsedInput
from .models import Artist, GeneratedPlaylist, Track, playlist_tracks
from .musicbrainz_api import MusicBrainzClient

logger = logging.getLogger(__name__)


def _artist_name_matches(track: Track, expected: str) -> tuple[bool, str | None]:
    """Return ``(matches, artist_name)`` for the Deezer artist on *track*.

    Uses a short-lived session to resolve the artist name from ``artist_id``
    (the relationship is not available on detached instances).  Returns
    ``(True, None)`` when the artist cannot be determined, so we never
    silently drop a track we can't verify.
    """
    if track.artist_id is None:
        return True, None
    with get_session() as db:
        artist: Artist | None = db.get(Artist, track.artist_id)
        if artist is None:
            return True, None
        name_on_deezer = artist.name.casefold()
        name_expected = expected.casefold()
        # Accept if either string contains the other (handles abbreviations
        # and minor platform name differences, e.g. "dj xxx" vs "dj xxx (official)").
        matches = (
            name_on_deezer == name_expected
            or name_on_deezer in name_expected
            or name_expected in name_on_deezer
        )
        return matches, artist.name


def _artist_name_matches_by_id(artist_id: int | None, expected: str) -> bool:
    """Check if an artist ID matches the expected artist name (case-insensitive).

    Used in fallback search; stricter than _artist_name_matches which is lenient
    when artist cannot be determined (to avoid silently dropping tracks).
    """
    if artist_id is None:
        return False
    with get_session() as db:
        artist: Artist | None = db.get(Artist, artist_id)
        if artist is None:
            return False
        name_on_deezer = artist.name.casefold()
        name_expected = expected.casefold()
        return (
            name_on_deezer == name_expected
            or name_on_deezer in name_expected
            or name_expected in name_on_deezer
        )


def generate_playlist(  # pylint: disable=too-many-arguments,too-many-locals,too-many-branches,too-many-statements,too-many-nested-blocks
    parsed: ParsedInput,
    *,
    client: DeezerClient | None = None,
    mb_client: MusicBrainzClient | None = None,
    name: str = "Generated Playlist",
    description: str = "",
    public: bool = False,
    limit_per_source: int = 10,
    interactive: bool = False,
) -> GeneratedPlaylist:
    """Resolve *parsed* input to tracks and persist a :class:`~models.GeneratedPlaylist`.

    Parameters
    ----------
    parsed:
        Output of :func:`~input_parser.parse_input_file`.
    client:
        A :class:`~deezer_api.DeezerClient` instance.  Created automatically
        when not supplied.
    mb_client:
        A :class:`~musicbrainz_api.MusicBrainzClient` instance used as a
        fallback when Deezer returns no exact artist match.  Created
        automatically when not supplied.
    name:
        Human-readable playlist name stored in the database.
    description:
        Optional playlist description.
    public:
        Whether the playlist should be public on Deezer.
    limit_per_source:
        Maximum number of tracks fetched per artist / album.
    interactive:
        If True, prompts user when multiple artists have the same exact name.
        If False (default), automatically selects the most popular.
    """
    if client is None:
        client = DeezerClient()
    if mb_client is None:
        mb_client = MusicBrainzClient(user_agent=config.musicbrainz_user_agent)

    tracks: list[Track] = []
    seen_ids: set[int] = set()

    def _add(t: Track | None) -> bool:
        if t is not None and t.id not in seen_ids:
            seen_ids.add(t.id)
            tracks.append(t)
            return True
        return False

    # ------------------------------------------------------------------
    if parsed.mode == InputMode.ARTISTS:
        for entry in parsed.artists:
            logger.info("Processing artist: %s", entry.artist)
            artist = client.search_artist(entry.artist, interactive=interactive)
            artist_tracks_count = 0
            if artist is not None:
                top = client.get_artist_top_tracks(
                    artist.id, limit=max(limit_per_source * 3, 50)
                )
                logger.debug(
                    "Fetched %d top tracks for artist %s", len(top), entry.artist
                )
                for t in top:
                    if artist_tracks_count >= limit_per_source:
                        break
                    matches, deezer_artist = _artist_name_matches(t, entry.artist)
                    if not matches:
                        logger.warning(
                            "Skipping track %r: primary Deezer artist is %r, "
                            "expected %r",
                            t.title,
                            deezer_artist,
                            entry.artist,
                        )
                        continue
                    _add(t)
                    artist_tracks_count += 1

                # Fallback: if top tracks filtered too many collaborations, search for more
                if artist_tracks_count < max(1, limit_per_source // 2):
                    logger.info(
                        "Only found %d tracks from %s via top tracks; "
                        "searching for additional tracks",
                        artist_tracks_count,
                        entry.artist,
                    )
                    # Try broader artist search (finds tracks by artist, including features)
                    candidates = client.search_tracks_by_artist(
                        entry.artist, limit=limit_per_source
                    )
                    for candidate in candidates:
                        if candidate["id"] in seen_ids:
                            continue
                        # Check if candidate's primary artist matches
                        candidate_artist_id = candidate.get("artist", {}).get("id")
                        if _artist_name_matches_by_id(
                            candidate_artist_id, entry.artist
                        ):
                            t = client.get_track(candidate["id"])
                            _add(t)
                            artist_tracks_count += 1
                            if artist_tracks_count >= limit_per_source:
                                break

                    # Third fallback: fetch all albums and their tracks
                    if artist_tracks_count < max(1, limit_per_source // 2):
                        logger.info(
                            "Still only %d tracks; fetching all albums for %s",
                            artist_tracks_count,
                            entry.artist,
                        )
                        album_tracks = client.get_artist_all_tracks(
                            artist.id, limit=limit_per_source * 2
                        )
                        for t in album_tracks:
                            if t.id not in seen_ids:
                                matches, _ = _artist_name_matches(t, entry.artist)
                                if matches:
                                    _add(t)
                                    artist_tracks_count += 1
                                    if artist_tracks_count >= limit_per_source:
                                        break

                logger.info(
                    "Found %d tracks for artist: %s", artist_tracks_count, entry.artist
                )
                continue

            # ---- MusicBrainz fallback ----------------------------------------
            logger.info("Falling back to MusicBrainz for artist: %s", entry.artist)
            mb_artist = mb_client.search_artist(entry.artist)
            if mb_artist is None:
                logger.warning(
                    "Artist not found on Deezer or MusicBrainz: %s", entry.artist
                )
                continue

            recordings = mb_client.get_artist_recordings(
                mb_artist["id"], limit=limit_per_source
            )
            if not recordings:
                logger.warning(
                    "No recordings found on MusicBrainz for artist: %s", entry.artist
                )
                continue

            logger.info(
                "MusicBrainz returned %d recordings for %s; resolving via Deezer",
                len(recordings),
                entry.artist,
            )
            mb_tracks_count = 0
            for rec in recordings:
                if mb_tracks_count >= limit_per_source:
                    break
                t: Track | None = None
                isrcs: list[str] = rec.get("isrcs") or []
                if isrcs:
                    # ISRC is an exact identifier — try direct Deezer lookup first
                    t = client.get_track_by_isrc(isrcs[0])
                    if t is not None:
                        matches, deezer_artist = _artist_name_matches(t, entry.artist)
                        if not matches:
                            logger.warning(
                                "MusicBrainz ISRC %s resolved to wrong artist on "
                                "Deezer (%r instead of %r); skipping",
                                isrcs[0],
                                deezer_artist,
                                entry.artist,
                            )
                            t = None
                if t is None:
                    # Fall back to title + artist search on Deezer
                    t = client.search_track(rec["title"], artist=entry.artist)
                if _add(t):
                    mb_tracks_count += 1
            logger.info(
                "Found %d tracks for artist: %s (via MusicBrainz fallback)",
                mb_tracks_count,
                entry.artist,
            )

    elif parsed.mode == InputMode.ALBUMS:
        for entry in parsed.albums:
            logger.info("Processing album: %s – %s", entry.title, entry.artist)
            album = client.search_album(entry.title, artist=entry.artist)
            if album is None:
                logger.warning("Album not found: %s", entry.title)
                continue
            album_tracks_count = 0
            for t in client.get_album_tracks(album.id)[:limit_per_source]:
                if _add(t):
                    album_tracks_count += 1
            logger.info(
                "Found %d tracks for album: %s – %s",
                album_tracks_count,
                entry.title,
                entry.artist,
            )

    elif parsed.mode == InputMode.TRACKS:
        for entry in parsed.tracks:
            logger.info("Processing track: %s", entry.title)
            t = client.search_track(
                entry.title,
                artist=entry.artist or None,
                album=entry.album or None,
                isrc=entry.isrc or None,
            )
            _add(t)

    # ------------------------------------------------------------------
    # Persist playlist to database
    # ------------------------------------------------------------------
    playlist = GeneratedPlaylist(
        name=name,
        description=description,
        public=public,
        created_at=datetime.now(timezone.utc),
    )

    with get_session() as db:
        db.add(playlist)
        db.flush()  # get auto-assigned id
        for position, track in enumerate(tracks):
            # Merge (or re-attach) track to *this* session
            track_in_session = db.merge(track)
            db.execute(
                playlist_tracks.insert().values(
                    playlist_id=playlist.id,
                    track_id=track_in_session.id,
                    position=position,
                )
            )
        db.refresh(playlist)
        # Detach so we can use it outside the session
        db.expunge(playlist)
        for t in tracks:
            try:
                db.expunge(t)
            except Exception:  # pylint: disable=broad-exception-caught
                pass

    logger.info(
        "Playlist %r created with %d tracks (id=%s)", name, len(tracks), playlist.id
    )
    return playlist
