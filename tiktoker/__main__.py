from typing import Annotated, Optional

import typer

from tiktoker.commands.export_favorites_metadata import (
    export_favorites_metadata as export_favorites_metadata_,
)
from tiktoker.commands.export_favorites_metadata import (
    export_favorites_metadata_sync_latest,
)
from tiktoker.commands.export_slideshow_images import (
    export_slideshow_images as export_slideshow_images_,
)

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
    since_export_id: Annotated[
        Optional[int],  # noqa: UP007
        typer.Option(
            "--since-export-id", help="only find videos added after the unix timestamp"
        ),
    ] = None,
) -> None:
    if since_export_id is not None:
        export_favorites_metadata_sync_latest(
            export_id=since_export_id,
            path_sqlite=path_sqlite,
            path_video_urls=path_video_urls,
            session_id=session_id,
        )
    else:
        export_favorites_metadata_(
            session_id=session_id,
            path_sqlite=path_sqlite,
            path_video_urls=path_video_urls,
        )


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
    export_slideshow_images_(
        export_id=export_id,
        path_sqlite=path_sqlite,
        path_slideshow_dir_path=path_slideshow_dir_path,
        is_dry_run=is_dry_run,
    )


if __name__ == "__main__":
    app()
