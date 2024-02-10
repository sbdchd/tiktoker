import json
import sqlite3
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from structlog.stdlib import BoundLogger


@dataclass(frozen=True, slots=True)
class Export:
    export_id: int
    cursor: int


@dataclass(frozen=True, slots=True)
class ExportTable:
    _conn: sqlite3.Connection
    _log: BoundLogger

    def _get_current(self) -> Export | None:
        cur = self._conn.cursor()
        result = cur.execute(
            """
select id, cursor 
from tiktok_export 
where completed_at is null 
limit 1;
        """
        ).fetchone()
        if result is None:
            return None
        export_id, cursor = result
        return Export(export_id=export_id, cursor=cursor)

    def get(self, *, export_id: int) -> Export | None:
        cur = self._conn.cursor()
        result = cur.execute(
            """
select id, cursor 
from tiktok_export 
where id = :export_id
limit 1;
        """,
            {"export_id": export_id},
        ).fetchone()
        if result is None:
            return None
        export_id, cursor = result
        return Export(export_id=export_id, cursor=cursor)

    def get_most_recent_cursor(self, *, export_id: int) -> int | None:
        cur = self._conn.cursor()
        result = cur.execute(
            """
SELECT
  max(http_request_param_cursor)
FROM
  tiktok_posts
WHERE
  export_id = :export_id
LIMIT 1;
        """,
            {"export_id": export_id},
        ).fetchone()
        if result is None:
            return None
        (cursor,) = result
        return cursor

    def get_or_create(self) -> Export:
        export = self._get_current()
        if export is not None:
            self._log.info(
                "found export in progress",
                export_id=export.export_id,
                cursor=export.cursor,
            )
            return export
        self._log.info("no incomplete export found. creating...")
        cursor = int(time.time())
        cur = self._conn.cursor()
        cur.execute(
            """
insert into tiktok_export(cursor) values (:cursor);
        """,
            {"cursor": cursor},
        )
        self._conn.commit()

        export = self._get_current()
        assert export is not None, "we should have saved a batch right before this"
        self._log.info(
            "created export", export_id=export.export_id, cursor=export.cursor
        )
        return export

    def complete(self, *, export_id: int) -> None:
        cur = self._conn.cursor()
        cur.execute(
            """
update tiktok_export
set completed_at = current_timestamp
where id = :export_id
        """,
            {
                "export_id": export_id,
            },
        )
        self._conn.commit()

    def checkpoint(self, *, export_id: int, cursor: int) -> None:
        cur = self._conn.cursor()
        cur.execute(
            """
update tiktok_export
set cursor = :cursor
where id = :export_id
        """,
            {
                "export_id": export_id,
                "cursor": cursor,
            },
        )
        self._conn.commit()


@dataclass(frozen=True, slots=True)
class PostCreateParams:
    http_request_duration_sec: float
    http_request_param_cursor: int
    http_request_url: str
    http_response_headers_json: dict[str, str]
    export_id: int
    post_json: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "http_request_duration_sec": self.http_request_duration_sec,
            "http_request_param_cursor": self.http_request_param_cursor,
            "http_request_url": self.http_request_url,
            "http_response_headers_json": json.dumps(self.http_response_headers_json),
            "export_id": self.export_id,
            "post_json": json.dumps(self.post_json),
        }


@dataclass(frozen=True, slots=True)
class PostUrl:
    is_video: bool
    url: str


@dataclass(frozen=True, slots=True)
class Slideshow:
    id: str
    author: str
    desc: str
    images: list[str]


@dataclass(frozen=True, slots=True)
class PostTable:
    _conn: sqlite3.Connection

    def create(self, records: Sequence[PostCreateParams]) -> int:
        cur = self._conn.cursor()
        cur.executemany(
            """
insert or ignore into tiktok_posts(
    http_request_duration_sec, 
    http_request_param_cursor, 
    http_request_url,
    http_response_headers_json, 
    export_id,
    post_json
) values (
    :http_request_duration_sec, 
    :http_request_param_cursor, 
    :http_request_url,
    :http_response_headers_json, 
    :export_id, 
    :post_json
)
        """,
            [r.to_dict() for r in records],
        )
        self._conn.commit()
        return cur.rowcount

    def urls(self, export_id: int, *, starting_after: int | None = None) -> list[str]:
        cur = self._conn.cursor()
        cur.execute(
            """
SELECT
	post_id,
	post_author
FROM
	tiktok_posts
WHERE
	export_id = :export_id
	AND (:starting_after is null or http_request_param_cursor > :starting_after)
GROUP BY
	post_id;
        """,
            {"export_id": export_id, "starting_after": starting_after},
        )
        urls = list[str]()
        for post_id, author in cur.fetchall():
            url = f"https://tiktok.com/@{author}/video/{post_id}"
            urls.append(url)
        return urls

    def slideshows(self, export_id: int) -> list[Slideshow]:
        cur = self._conn.cursor()
        cur.execute(
            """
select
	post_id,
    post_author,
    json_extract(post_json, '$.desc'),
    json_extract(post_json, '$.imagePost.images')
from tiktok_posts
where 
    export_id = :export_id
    and not post_is_video;
        """,
            {"export_id": export_id},
        )
        urls = list[Slideshow]()
        for post_id, author, desc, img_data in cur.fetchall():
            images = list[str]()
            for image in json.loads(img_data):
                images.append(image["imageURL"]["urlList"][0])
            urls.append(Slideshow(id=post_id, author=author, desc=desc, images=images))
        return urls


@dataclass(frozen=True, slots=True)
class DB:
    _conn: sqlite3.Connection
    _log: BoundLogger

    @classmethod
    def create(cls, *, path: str, log: BoundLogger) -> "DB":
        conn = sqlite3.connect(path)
        db = DB(conn, log)
        db._create_tables()
        return db

    def _create_tables(self) -> None:
        cur = self._conn.cursor()
        cur.executescript(
            """
create table if not exists tiktok_export (
    id integer primary key,
    completed_at text, -- TODO: only one of the rows should be able to have: completed_at is null
    cursor integer not null,
    created_at text default current_timestamp not null
) strict;

create table if not exists tiktok_posts (
    id integer primary key,

    export_id integer not null,

    http_request_url text not null,
    http_request_duration_sec real not null,
    http_request_param_cursor integer not null,
    http_response_headers_json text not null check (json_valid(http_response_headers_json)),
    
    post_id text generated always AS (json_extract(post_json, '$.id')) virtual,
    post_author text generated always AS (json_extract(post_json, '$.author.uniqueId')) virtual,
    post_is_video integer generated always AS (json_extract(post_json, '$.imagePost') IS NULL) virtual,
    post_created_at integer generated always AS (json_extract(post_json, '$.createTime')) virtual,
    post_json text not null check (json_valid(post_json)),

    created_at text default current_timestamp not null,

    foreign key(export_id) references tiktok_export(id)
) strict;

create unique index if not exists
    unique_videos_per_export on tiktok_posts (export_id, post_id);
        """
        )
        self._conn.commit()

    @property
    def export(self) -> ExportTable:
        return ExportTable(self._conn, self._log)

    @property
    def posts(self) -> PostTable:
        return PostTable(self._conn)
