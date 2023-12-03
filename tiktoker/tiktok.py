import time
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import httpx
from structlog.stdlib import BoundLogger, get_logger
from tenacity import retry, retry_if_exception_type, wait_exponential, wait_random

logger = get_logger()


@dataclass(frozen=True, slots=True)
class FetchResult:
    cursor: int
    duration_sec: float
    content: Any
    response_headers: httpx.Headers
    request_headers: httpx.Headers
    request_url: str


@dataclass(frozen=True, slots=True)
class DownloadResult:
    duration_sec: float
    content: Any
    has_more: bool
    cursor: int
    response_headers: httpx.Headers
    request_headers: httpx.Headers
    request_url: str


@retry(
    retry=retry_if_exception_type(httpx.HTTPError),
    wait=wait_exponential(multiplier=1, min=0.5, max=15) + wait_random(0, 2),
    after=lambda x: logger.warning("call failed", attempt=x.attempt_number),
)
def _download_favorites_batch(*, cursor: int, session_id: str) -> DownloadResult:
    headers = {
        "Pragma": "no-cache",
        "Accept": "*/*",
        "Sec-Fetch-Site": "same-origin",
        "Accept-Language": "en-US,en;q=0.9",
        "Sec-Fetch-Mode": "cors",
        "Cache-Control": "no-cache",
        "Host": "www.tiktok.com",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
        "Referer": "https://www.tiktok.com/@thegamesteam",
        "Connection": "keep-alive",
        "Sec-Fetch-Dest": "empty",
    }
    start = time.monotonic()
    params = {
        # NOTE: this is most of the query params
        # I removed: device_id, secUid, verifyFp
        # since they looked secret/sensitive, but it still works.
        # We might be able to remove more values, not sure!
        "WebIdLastTime": "0",
        "aid": "1988",
        "app_language": "en",
        "app_name": "tiktok_web",
        "browser_language": "en-US",
        "browser_name": "Mozilla",
        "browser_online": "true",
        "browser_platform": "MacIntel",
        "browser_version": "5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
        "channel": "tiktok_web",
        "cookie_enabled": "true",
        "count": "30",
        "coverFormat": "0",
        "cursor": cursor,
        "device_platform": "web_pc",
        "focus_state": "false",
        "from_page": "user",
        "history_len": "4",
        "is_fullscreen": "false",
        "is_page_visible": "true",
        "language": "en",
        "os": "mac",
        "priority_region": "US",
        "region": "US",
        "screen_height": "982",
        "screen_width": "1512",
        "tz_name": "America/New_York",
        "webcast_language": "en",
    }

    cookies = {
        # NOTE: there are a lot more values in the web api's cookies, but I
        # removed all of them except sessionid to avoid leaking anything
        # sensitive.
        #
        # If we start hitting auth issues or getting blocked, it would make
        # sense to include all of the cookies here.
        "sessionid": session_id,
    }
    res = httpx.get(
        "https://www.tiktok.com/api/user/collect/item_list/",
        params=params,
        cookies=cookies,
        headers=headers,
    )
    end = time.monotonic()
    duration_sec = end - start
    res.raise_for_status()
    content = res.json()
    return DownloadResult(
        duration_sec=duration_sec,
        content=content,
        has_more=content["hasMore"],
        cursor=content["cursor"],
        response_headers=res.headers,
        request_headers=res.request.headers,
        request_url=str(res.request.url),
    )


@dataclass(frozen=True, slots=True)
class TikTok:
    log: BoundLogger
    session_id: str

    def favorites(self, *, created_before: int) -> Iterator[FetchResult]:
        page = 1
        has_more = True
        while has_more:
            res = _download_favorites_batch(
                cursor=created_before, session_id=self.session_id
            )
            self.log.info(
                "fetched batch",
                cursor=created_before,
                page=page,
                duration_sec=res.duration_sec,
            )
            yield FetchResult(
                cursor=created_before,
                duration_sec=res.duration_sec,
                content=res.content,
                response_headers=res.response_headers,
                request_headers=res.request_headers,
                request_url=res.request_url,
            )
            page += 1
            has_more = res.has_more
            created_before = res.cursor
