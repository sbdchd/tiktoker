import sys
import time
from pathlib import Path

from structlog.stdlib import BoundLogger, get_logger

from tiktoker.db import DB, PostCreateParams
from tiktoker.tiktok import TikTok


def export_favorites_metadata(
    *, session_id: str, path_sqlite: str, path_video_urls: str
) -> None:
    logger = get_logger()
    logger.info("starting")
    db = DB.create(path=path_sqlite, log=logger)
    exp = db.export.get_or_create()

    log = logger.bind(export_id=exp.export_id)

    api = TikTok(log, session_id=session_id)
    for fav_batch in api.favorites(created_before=exp.cursor):
        posts = [
            PostCreateParams(
                http_request_duration_sec=fav_batch.duration_sec,
                http_request_url=fav_batch.request_url,
                http_request_param_cursor=fav_batch.cursor,
                export_id=exp.export_id,
                http_response_headers_json=dict(fav_batch.response_headers.items()),
                post_json=post,
            )
            for post in fav_batch.posts
        ]
        db.posts.create(posts)
        db.export.checkpoint(export_id=exp.export_id, cursor=fav_batch.cursor)

    db.export.complete(export_id=exp.export_id)
    log.info("export complete")

    urls = db.posts.urls(export_id=exp.export_id)
    _save_urls(urls, path=path_video_urls, log=log, export_id=exp.export_id)


def export_favorites_metadata_sync_latest(
    *, export_id: int, path_sqlite: str, path_video_urls: str, session_id: str
) -> None:
    logger = get_logger()
    log = logger.bind(export_id=export_id)
    log.info("starting")

    db = DB.create(path=path_sqlite, log=logger)

    exp = db.export.get(export_id=export_id)
    if exp is None:
        log.warning("export not found", export_id=export_id)
        sys.exit(1)

    most_recent_cursor = db.export.get_most_recent_cursor(export_id=export_id)
    if most_recent_cursor is None:
        log.warning("export not found", export_id=export_id)
        sys.exit(1)

    starting_cursor = int(time.time())

    log.info(
        "found cursor",
        most_recent_cursor=most_recent_cursor,
        starting_cursor=starting_cursor,
    )

    api = TikTok(log, session_id=session_id)
    for fav_batch in api.favorites(created_before=starting_cursor):
        posts = [
            PostCreateParams(
                http_request_duration_sec=fav_batch.duration_sec,
                http_request_url=fav_batch.request_url,
                http_request_param_cursor=fav_batch.cursor,
                export_id=exp.export_id,
                http_response_headers_json=dict(fav_batch.response_headers.items()),
                post_json=post,
            )
            for post in fav_batch.posts
        ]
        if fav_batch.cursor <= most_recent_cursor:
            log.info(
                "reached previously exported posts",
                export_id=export_id,
                cursor=fav_batch.cursor,
            )
            break
        posts_created_count = db.posts.create(posts)
        if not posts_created_count:
            log.info("no new posts created")
            break
        log.info("posts created", posts_created_count=posts_created_count)
        db.export.checkpoint(export_id=exp.export_id, cursor=fav_batch.cursor)

    db.export.complete(export_id=exp.export_id)
    log.info("export complete")

    urls = db.posts.urls(export_id=exp.export_id, starting_after=most_recent_cursor)
    _save_urls(urls, path=path_video_urls, log=log, export_id=exp.export_id)


def _save_urls(urls: list[str], *, path: str, log: BoundLogger, export_id: int) -> None:
    Path(path).write_text("\n".join(urls))
    log.info(
        "urls saved",
        urls_count=len(urls),
        video_urls_path=path,
    )
    print(  # noqa: T201
        f"""
Next Steps:

1. Download videos (and audio for slideshows)

    yt-dlp -o "tiktok-videos/tiktok@%(uploader)s:%(id)s:%(title).100B.%(ext)s" -a {path}

2. Download images for slideshows

    tiktoker export-slideshow-images --export-id={export_id}
"""
    )
