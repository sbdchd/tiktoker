# tiktoker

> TikTok favorites exporter

## Why?

Save favorited videos so they don't get lost if they end up getting removed from TikTok.

## Usage

1. setup

   ```shell
   git clone https://github.com/sbdchd/tiktoker.git
   cd tiktoker
   poetry config virtualenvs.in-project true
   poetry install
   ```

2. login to tiktok.com and grab your session id cookie value using the dev tools
3. download your favorites metadata

   ```shell
   ./.venv/bin/python -m tiktoker export-favorites-metadata --session-id=$SESSION_ID
   ```

4. download the images for slideshow favorites

   NOTE: `$EXPORT_ID` is printed by the `exports-favorites-metadata` command

   ```shell
   ./.venv/bin/python -m tiktoker export-slideshow-images --export-id=$EXPORT_ID
   ```

5. download the videos (and audio for slideshows) using yt-dlp

   NOTE: `$VIDEO_URL_PATH` is printed by the `export-favorites-metadata` command and defaults to `tiktok-video-urls.txt`

   ```shell
   yt-dlp -o "tiktok-videos/tiktok@%(uploader)s:%(id)s:%(title).100B.%(ext)s" -a $VIDEO_URL_PATH
   ```

6. enjoy your favorites locally!

   All the media and related metadata is saved locally.
   You can peruse the sqlite database for more info on a given video!

## Prior Art / Alternatives

- [tiktok-save](https://github.com/samirelanduk/tiktok-save)
- [myfaveTT](https://chromewebstore.google.com/detail/myfavett-download-all-tik/gmajiifkcmjkehmngbopoobeplhoegad?pli=1)
