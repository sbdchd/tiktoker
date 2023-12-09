from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from structlog.stdlib import get_logger

from tiktoker.db import DB
from tiktoker.http import download_image


def _is_expired_url(url: str) -> bool:
    query_params = parse_qs(urlparse(url).query)
    expires_at = datetime.fromtimestamp(int(query_params["x-expires"][0]), tz=UTC)
    return expires_at < datetime.now(tz=UTC)


def export_slideshow_images(
    export_id: int,
    path_sqlite: str,
    path_slideshow_dir_path: str,
    is_dry_run: bool,
) -> None:
    logger = get_logger()
    logger.info("starting...")
    db = DB.create(path=path_sqlite, log=logger)
    for post in db.posts.slideshows(export_id=export_id):
        image_count = len(post.images)
        padding = len(str(image_count))
        for idx, url in enumerate(post.images, start=1):
            log = logger.bind(url=url, post_id=post.id, author=post.author)
            if _is_expired_url(url):
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
