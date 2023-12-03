import mimetypes
from dataclasses import dataclass

import httpx
from structlog.stdlib import get_logger
from tenacity import retry, retry_if_exception_type, wait_exponential, wait_random

logger = get_logger()


@dataclass(frozen=True, slots=True)
class ImageResult:
    content: bytes
    extension: str | None


@retry(
    retry=retry_if_exception_type(httpx.HTTPError),
    wait=wait_exponential(multiplier=1, min=0.5, max=15) + wait_random(0, 2),
    after=lambda x: logger.warning(
        "download image request failed. Retrying...",
        attempt=x.attempt_number,
        exec=x.outcome is not None and x.outcome.exception(),  # pyright: ignore [reportUnknownMemberType]
    ),
)
def download_image(*, url: str) -> ImageResult:
    res = httpx.get(url)
    res.raise_for_status()
    content_type = res.headers["content-type"]
    extension = mimetypes.guess_extension(content_type)

    return ImageResult(extension=extension, content=res.content)
