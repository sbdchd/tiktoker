from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated
from urllib.parse import parse_qs, urlparse

import typer
from structlog.stdlib import get_logger

from tiktoker.db import DB, PostCreateParams
from tiktoker.http import download_image
from tiktoker.tiktok import TikTok

app = typer.Typer()

DEFAULT_SQLITE_PATH = "tiktok-scraper.db"


@app.command()
def export_favorites_metadata(
    session_id: Annotated[
        str,
        typer.Option(help="session_id taken from the web version of tiktok's cookies"),
    ],
    path_sqlite: Annotated[
        str,
        typer.Option("--sqlite-path", help="path to save the sqlite database on disk"),
    ] = DEFAULT_SQLITE_PATH,
    path_video_urls: Annotated[
        str,
        typer.Option("--video-urls-path", help="path to save the tiktok video urls"),
    ] = "tiktok-video-urls.txt",
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
    Path(path_video_urls).write_text("\n".join(urls))
    log.info(
        "urls saved",
        urls_count=len(urls),
        video_urls_path=path_video_urls,
    )
    print(  # noqa: T201
        f"""
Next Steps:

1. Download videos (and audio for slideshows)

    yt-dlp -o "tiktok-videos/tiktok@%(uploader)s:%(id)s:%(title).100B.%(ext)s" -a {path_video_urls}

2. Download images for slideshows

    tiktoker export-slideshow-images --export-id={exp.export_id}
"""
    )


def is_expired_url(url: str) -> bool:
    query_params = parse_qs(urlparse(url).query)
    expires_at = datetime.fromtimestamp(int(query_params["x-expires"][0]), tz=UTC)
    return expires_at < datetime.now(tz=UTC)


@app.command()
def export_slideshow_images(
    export_id: Annotated[int, typer.Option(help="id of the export_id")],
    path_sqlite: Annotated[
        str,
        typer.Option("--sqlite-path", help="path to save the sqlite database on disk"),
    ] = DEFAULT_SQLITE_PATH,
    path_slideshow_dir_path: Annotated[
        str,
        typer.Option("--image-dir-path", help="path to save the images"),
    ] = "tiktok-images",
    is_dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="skip downloading, instead print urls"),
    ] = False,
) -> None:
    logger = get_logger()
    logger.info("starting...")
    db = DB.create(path=path_sqlite, log=logger)
    for post in db.posts.slideshows(export_id=export_id):
        image_count = len(post.images)
        padding = len(str(image_count))
        for idx, url in enumerate(post.images, start=1):
            log = logger.bind(url=url, post_id=post.id, author=post.author)
            if is_expired_url(url):
                log.warning("skipping expired url")
                continue
            if is_dry_run:
                log.info("would download")
                continue
            log.info("downloading")
            res = download_image(url=url)

            dir = Path(path_slideshow_dir_path).resolve()
            dir.mkdir(parents=True, exist_ok=True)
            filename = f"tiktok@{post.author}:{post.id}:slide-{idx:0{padding}}-of-{image_count}:{post.desc[:80]}{res.extension}"
            (dir / filename).write_bytes(res.content)


if __name__ == "__main__":
    app()
