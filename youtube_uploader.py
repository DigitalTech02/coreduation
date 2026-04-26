"""YouTube auto-upload via Google Data API v3.

Uploads a finished video with:
  * title from ``script.suggested_youtube_title`` or ``script.video_title``
  * description with auto-generated chapters from per-scene start times
  * tags from ``script.suggested_youtube_tags``
  * optional custom thumbnail (PNG/JPG)

Requires::

    pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib

Set up OAuth once:
  1. Create a Google Cloud project & enable YouTube Data API v3
  2. Download the OAuth client secret JSON to ``./client_secret.json``
  3. The first run opens a browser for consent → token cached in
     ``./youtube_token.json`` for subsequent runs.

This module is fully optional — calling :func:`upload_to_youtube` when the
config flag or dependencies are missing returns ``None`` and logs a notice.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Iterable

logger = logging.getLogger(__name__)

_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _enabled() -> bool:
    try:
        from config import ENABLE_YOUTUBE_UPLOAD
        return bool(ENABLE_YOUTUBE_UPLOAD)
    except Exception:
        return False


def _format_chapter_time(seconds: float) -> str:
    """Format seconds as ``H:MM:SS`` (always include hours per YouTube spec)."""
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}"


def build_chapters(
    scene_titles: Iterable[str],
    scene_durations: Iterable[float],
    intro_offset: float = 0.0,
) -> str:
    """Return a YouTube-style chapter list.

    The first chapter must start at 0:00:00 and chapters must be strictly
    increasing for YouTube to recognize them.
    """
    titles = list(scene_titles)
    durations = list(scene_durations)
    if not titles:
        return ""

    chapters: list[str] = []
    start = 0.0
    chapters.append(f"{_format_chapter_time(start)} Intro")
    start += max(intro_offset, 1.0)

    for title, dur in zip(titles, durations):
        chapters.append(f"{_format_chapter_time(start)} {title}")
        start += max(float(dur), 1.0)

    return "\n".join(chapters)


def build_description(
    base_description: str,
    chapters: str,
    hashtags: Iterable[str] | None = None,
    extra_links: str = "",
) -> str:
    parts: list[str] = []
    if base_description.strip():
        parts.append(base_description.strip())
    if chapters:
        parts.append("Chapters:\n" + chapters)
    if extra_links.strip():
        parts.append(extra_links.strip())
    if hashtags:
        tag_line = " ".join(f"#{t.strip().lstrip('#').replace(' ', '')}" for t in hashtags if t.strip())
        if tag_line:
            parts.append(tag_line)
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def _get_service():
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError:
        logger.warning(
            "YouTube upload skipped: google-api-python-client + auth libs not installed. "
            "Install with: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib"
        )
        return None

    token_path = Path(os.getenv("YOUTUBE_TOKEN_FILE", "youtube_token.json"))
    secret_path = Path(os.getenv("YOUTUBE_CLIENT_SECRET", "client_secret.json"))

    creds = None
    if token_path.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_path), _SCOPES)
        except Exception as e:
            logger.warning("Could not load cached YouTube token: %s", e)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                logger.warning("YouTube token refresh failed: %s", e)
                creds = None
        if not creds:
            if not secret_path.exists():
                logger.error(
                    "YouTube upload requires OAuth client secret at %s. "
                    "Download from Google Cloud Console.", secret_path,
                )
                return None
            flow = InstalledAppFlow.from_client_secrets_file(str(secret_path), _SCOPES)
            creds = flow.run_local_server(port=0)

        try:
            token_path.write_text(creds.to_json(), encoding="utf-8")
        except Exception as e:
            logger.debug("Could not persist YouTube token: %s", e)

    return build("youtube", "v3", credentials=creds)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def upload_to_youtube(
    video_path: str | Path,
    *,
    title: str,
    description: str,
    tags: Iterable[str] | None = None,
    category_id: str = "27",
    privacy_status: str = "private",
    thumbnail_path: str | Path | None = None,
    made_for_kids: bool = False,
) -> dict | None:
    """Upload ``video_path`` to YouTube and return the API response, or ``None``."""
    if not _enabled():
        logger.info("YouTube upload disabled via ENABLE_YOUTUBE_UPLOAD=false; skipping")
        return None

    video_path = Path(video_path)
    if not video_path.exists():
        logger.error("YouTube upload aborted: %s does not exist", video_path)
        return None

    service = _get_service()
    if service is None:
        return None

    try:
        from googleapiclient.http import MediaFileUpload
    except ImportError:
        logger.warning("MediaFileUpload not available; aborting YouTube upload")
        return None

    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": list(tags or [])[:30],
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": made_for_kids,
        },
    }

    media = MediaFileUpload(
        str(video_path), mimetype="video/mp4", resumable=True, chunksize=8 * 1024 * 1024,
    )
    request = service.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    last_progress = 0
    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                pct = int(status.progress() * 100)
                if pct - last_progress >= 10:
                    logger.info("YouTube upload progress: %d%%", pct)
                    last_progress = pct
        except Exception as e:
            logger.error("YouTube upload chunk error: %s", e)
            return None

    video_id = response.get("id")
    logger.info("YouTube upload complete: https://youtu.be/%s", video_id)

    if thumbnail_path:
        try:
            tp = Path(thumbnail_path)
            if tp.exists():
                service.thumbnails().set(
                    videoId=video_id,
                    media_body=MediaFileUpload(str(tp), mimetype="image/png"),
                ).execute()
                logger.info("YouTube custom thumbnail uploaded")
        except Exception as e:
            logger.warning("Thumbnail upload failed: %s", e)

    return response


def upload_video(final_path: str | Path, script, run_dir: str | Path | None = None) -> dict | None:
    """Convenience wrapper: pull title/desc/tags/thumbnail from the enriched script."""
    if not _enabled():
        return None

    title = (
        getattr(script, "suggested_youtube_title", "")
        or getattr(script, "video_title", "")
        or getattr(script, "topic", "Untitled")
    )
    base_desc = (
        getattr(script, "suggested_youtube_description", "")
        or getattr(script, "video_hook", "")
        or ""
    )

    scenes = getattr(script, "scenes", []) or []
    chapter_titles = [s.title for s in scenes]
    chapter_durations = [
        (s.audio_duration or s.estimated_duration or 5.0) for s in scenes
    ]

    try:
        from config import ENABLE_REMOTION_CHROME, REMOTION_INTRO_DURATION
        intro_offset = float(REMOTION_INTRO_DURATION) if ENABLE_REMOTION_CHROME else 3.0
    except Exception:
        intro_offset = 3.0

    chapters = build_chapters(chapter_titles, chapter_durations, intro_offset=intro_offset)
    tags = list(getattr(script, "suggested_youtube_tags", []) or [])
    description = build_description(base_desc, chapters, hashtags=tags[:5])

    privacy = "private"
    try:
        from config import YOUTUBE_PRIVACY
        privacy = YOUTUBE_PRIVACY
    except Exception:
        pass

    thumb = None
    if run_dir:
        candidate = Path(run_dir) / "thumbnail.jpg"
        if candidate.exists():
            thumb = candidate

    return upload_to_youtube(
        final_path,
        title=title,
        description=description,
        tags=tags,
        privacy_status=privacy,
        thumbnail_path=thumb,
    )
