# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Python/Tkinter desktop app that searches StreamingCommunity and downloads episodes/movies via scraped
vixcloud.co HLS streams, using `yt-dlp` + `ffmpeg`. No test suite in this repo (a few pieces are covered by ../SC-ServerforTV's pytest
suite, see below), no build step. Layout:

```
main.py                          # entry point: `python main.py`
pyproject.toml                   # makes `sc_downloader` pip-installable (`pip install -e`); used as a shared
                                 # library by the sibling project ../SC-ServerforTV (headless server, no Tk)
sc_downloader/
    __init__.py                  # verifies curl_cffi/yt-dlp/pycryptodomex are importable in sys.executable
    __main__.py                  # entry point: `python -m sc_downloader`
    constants.py                 # base_url() (dominio variabile, SC_BASE_URL, segue i redirect), USER_AGENT, ROOT_DIR, SETTINGS_FILE, DEBUG_LOG_FILE
    api.py                       # StreamingCommunityAPI (search, get_title incl. cast/directors, get_season,
                                 # get_home/get_latest); every site string is HTML-unescaped on read
    scraper.py                   # ScrapeEngine (build_m3u8 / build_m3u8_info -> (url, can_fhd), m3u8_from_embed)
    download_manager.py          # DownloadManager (the core download/threading logic)
    theme.py                     # palette, font picking, text measuring/ellipsizing, ttk style setup
    images.py                    # ImageLoader (threaded CDN fetch + Pillow processing, Pillow optional)
    widgets.py                   # Canvas-drawn reusable widgets (Button, Chip, ScrollFrame, ProgressRing, ...)
    views.py                     # the pages: SearchView, DetailView, DownloadsView, SettingsView (+ their cards)
    folder_dialog.py             # FolderBrowserDialog
    app.py                       # ScDownloaderApp (the Tk root: nav rail, page switching, queue actions) + main()
    assets/icon.svg, icon.png    # app logo (same as the nav rail logo); PNG is rendered from the SVG with
                                 # `rsvg-convert -w 256 -h 256 icon.svg -o icon.png` (Tk 8.6 can't read SVG)
```

`sc_downloader/` was split out of a single ~1150-line `sc_downloader.py` along its existing class boundaries,
no deeper nesting (no `gui/`/`core/` subpackages). Non-GUI logic (`api`, `scraper`, `download_manager`) never
imports Tkinter; GUI code lives in `theme`/`widgets`/`views`/`folder_dialog`/`app`. Keep new code in the matching
module rather than reintroducing a monolith.

## Commands

```bash
# first-time setup (Arch/CachyOS has no system pip; a venv is required)
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt

# run (both are equivalent)
./.venv/bin/python main.py
./.venv/bin/python -m sc_downloader

# quick syntax/lint check (no formal linter configured in this repo)
./.venv/bin/python -c "import ast; ast.parse(open('main.py').read())"
./.venv/bin/pip install pyflakes && ./.venv/bin/python -m pyflakes main.py sc_downloader/  # then pip uninstall pyflakes
```

`ffmpeg` must be on system `PATH` (not pip-installable). `Pillow` (in `requirements.txt`) is *optional* at
runtime — it only decodes the CDN's `.webp` posters/covers; without it `images.AVAILABLE` is false, the UI draws
placeholders and shows a one-time warning toast. It is deliberately not in `__init__.py`'s hard check. `.venv/` is gitignored — recreate it, don't assume it
exists.

There is no automated test suite in this repo. ../SC-ServerforTV's `tests/` (pytest, installed against this
package in editable mode) cover a few pieces of it: HTML-entity decoding of site text and `_credits` with
`"order": null` (`tests/test_text.py`); when fixing a bug here that the server can hit, add a test there
(`cd ../SC-ServerforTV && ./.venv/bin/python -m pytest`). Otherwise verification has been manual: run the app and exercise it, or
write small standalone scripts that instantiate `DownloadManager`/`StreamingCommunityAPI` directly and print
results (see git history for examples — e.g. probing real `yt-dlp`/`ffmpeg` output formats against a live or
public test HLS URL before wiring a regex to it). Prefer that over assuming an output format.

## Architecture

**Scraping is HTML-parsing, not a JSON API.** `StreamingCommunityAPI` fetches normal HTML pages and pulls JSON
out of the `data-page="..."` attribute (an Inertia.js SPA embeds its page props there). `ScrapeEngine` then does
a second scrape: fetch `/it/iframe/{title_id}`, regex out the vixcloud embed URL (any TLD: `.co` until 2026-10, now `.cc`; Referer/Origin for playlist and
segments follow the playlist host, `player_origin`), fetch that, and regex the
inline `<script>` for `token`/`expires`/playlist `url` to build the final `.m3u8`. Both are brittle to upstream
markup changes by design — there's no stable API contract to rely on.

**Site text arrives HTML-escaped even inside that JSON** (e.g. `"sull&#39;inferno"` in episode names and plots):
`_parse_data_page` runs every string through `_unescape_strings` (recursive `html.unescape`) right after
`json.loads`, so callers get plain text — don't unescape again downstream. **Don't trust field types either**:
`main_actors`/`main_directors` carry `pivot.order`, which can be present but `null` for a whole cast (Marshals,
2026-10-12: sorting on it raised `'<' not supported between NoneType and NoneType` and the server showed the title
as "StreamingCommunity non risponde"). `_credits` sorts non-numeric orders last, keeping the site's order.

**`canPlayFHD`**: the vixcloud embed script says whether the player grants 1080p at that moment; without it the
playlist tops out at 720p. `ScrapeEngine.build_m3u8_info()` returns `(url, can_fhd)` (`build_m3u8()` is the
url-only wrapper) and `_download_one` stores it in `item["can_fhd"]`, so library users know why a download came
out 720p (../SC-ServerforTV re-downloads those later). `m3u8_from_embed(vix_url, referer)` builds the playlist from
any vixcloud embed page, for other sites using the same player (AnimeUnity).

**Video and audio are separate HLS renditions on this CDN**, not a single muxed stream. `DownloadManager`
therefore launches **two parallel `yt-dlp` subprocesses** per episode (`-f bestvideo` / `-f bestaudio`, both with
`--hls-prefer-native --concurrent-fragments N`, `N` = `DownloadManager.concurrent_fragments`, default 4), and
once both exit 0, muxes them itself with a plain `ffmpeg -c copy -movflags +faststart` (`+faststart` puts the
`moov` atom first: Samsung TVs playing these files over HTTP via ../SC-ServerforTV stay stuck loading otherwise).
The merge writes `<file>.mp4.merging` (`-f mp4`, since the extension no longer says it) and `os.replace`s it onto
the final name only on success, so re-downloading an existing file (e.g. in better quality) never loses the old
one on failure. Requires `--impersonate chrome`
(curl_cffi/yt-dlp TLS impersonation) to get past vixcloud's fingerprinting.

**Exception: some titles are served already muxed** (no `EXT-X-MEDIA:TYPE=AUDIO` in the master playlist; seen
on titles whose vixcloud playlist URL carries `?b=1`). There `-f bestvideo`/`-f bestaudio` match nothing, so
`_download_one` first calls `ScrapeEngine.has_separate_audio()` and, when false, runs a single `-f best`
subprocess and just remuxes it to `.mp4` (`audio_progress` mirrors `video_progress`). Related trap in
`build_m3u8`: the playlist URL may already have a query string, and the rebuilt params must always follow
`?` — joining with `&` yields `playlist/ID&b=1&token=...`, which vixcloud answers with 403.

**Multiple episodes can also download in parallel** (`DownloadManager.max_parallel_episodes`, default 1, user
configurable via the Settings dialog): `_download_loop` is a small scheduler that starts one thread per episode
while fewer than `max_parallel_episodes` are running, picking the next one with `_next_item(pending)`. Both
`max_parallel_episodes` and `concurrent_fragments` are re-read every time an episode starts, so changing them
applies at once to the next episodes (lowering the limit never kills running ones); `wake()` makes the loop
re-check immediately instead of within its 0.5 s poll. Items are marked `in_corso` by the scheduler *before*
their thread starts, so `_next_item` can't hand the same one out twice. Because of this,
`self._current_processes` (the list `kill_current()` kills to stop everything) is a **shared, lock-protected**
list (`self._processes_lock`) that every concurrently-running `_download_one` call appends its own subprocesses
into and removes them from when done — never reassign it wholesale, that would clobber other episodes'
processes mid-download. `remove()`-ing a queue item that's currently downloading still stops the *whole* batch
(no per-item cancellation) since processes aren't tracked per item, only in that one shared list.

**Both `curl_cffi`, `yt-dlp` and `pycryptodomex` are load-bearing dependencies, checked at import time in
`sc_downloader/__init__.py`** against `sys.executable` specifically (via `importlib.util.find_spec`), not just
"installed somewhere on the system" — because `yt-dlp` is invoked as `sys.executable -m yt_dlp`
(`download_manager.py`), so it must live in the *same* interpreter running the app. Launching the app with a
different Python than the one dependencies were installed into (e.g. system `python` instead of
`.venv/bin/python`) reproduces this exact failure mode and is the first thing to check if `__init__.py`'s
check somehow doesn't catch it. `pycryptodomex` specifically backs `yt-dlp`'s native AES decryption for this
site's encrypted HLS segments; without it `yt-dlp` *silently* falls back to `ffmpeg` as an external downloader
— fetching fragments sequentially instead of with `--concurrent-fragments`, and emitting a completely
different progress-line format (`time=`/`size=...KiB` instead of `[download] N% ... (frag X/Y)`). Confirmed
~9x throughput difference in testing. If progress parsing or download speed regresses mysteriously, check this
dependency (and which interpreter is running) before touching the regexes.

**Progress/size shown in the UI come from disk, not from yt-dlp's own totals.** yt-dlp's `~estimated total`
size (and therefore its own reported `%`) fluctuates non-monotonically while concurrent fragments arrive out of
order — it can overshoot by 2x and then correct downward. So: percentage is derived from the fragment counter
(`frag N/M`, monotonic because `M` is fixed and `N` only increases), and downloaded size is the real size on
disk (`glob` the destination dir for the episode's filename prefix and sum `os.path.getsize`). Video and audio
progress/speed are tracked as separate fields (`video_progress`/`audio_progress`/`video_speed_mb_s`/
`audio_speed_mb_s`) since they're two independent subprocesses that can finish at different times.

**`DownloadManager` is also used as a library by `../SC-ServerforTV`** (headless server, no Tk). Its hooks
beyond the GUI's: `item_finished_callback(item)` (called from the worker thread right after an item is marked
`completato`; `item["dest_dir"]` + `item["filename"]` + `.mp4` is the file; exceptions in it are swallowed) and
`finished_callback` (batch end). The server overrides `_next_item` to pick `in_coda` items from the live queue
(under its own lock), so items added mid-batch start without waiting for the batch to end, and calls `wake()` after
adding items or changing the limits from its admin settings page. It relies on
`kill_current()` being non-blocking (it waits for `is_downloading` to drop to see partial files cleaned) and on
queue items being plain JSON-serializable dicts (it persists them) — keep those properties when changing this class.
Extension points for other sites with the same player (the server's AnimeUnity queue uses all of them; the desktop
app uses none): `DownloadManager.m3u8_info(item)` returns `(url, can_fhd)` and can be overridden in a subclass;
items may carry `dest_parts` (folder components under `output_folder`, resolved case-insensitively like the rest)
plus `dest_name` (file name without `.mp4`), which take precedence over the Film/Serie TV layout; and `label`,
which `item_label()` returns as-is.

**Process lifecycle**: every `yt-dlp` subprocess is started with `start_new_session=True` so
`DownloadManager.kill_current()` can `os.killpg(...)` the whole process group (including any `ffmpeg` child)
instead of leaving orphaned downloads running after Stop/window-close. `kill_current()` is the single choke
point for stopping — both the Stop button and the window-close handler (with a confirmation dialog if a
download is active) route through it. After a user stop, each interrupted `_download_one` deletes its partial
`<filename>.video.*`/`.audio.*` files (`.part`, `.part-FragN`, `.ytdl`) and removes the destination folders
left empty (`_remove_empty_dirs`, never above `output_folder`), then returns `False` so the worker resets the
item to `in_coda`. `_download_one` returns `True` on success — a stop arriving during the final ffmpeg merge
still yields a complete file, so that item is marked `completato`, not reset.

**Threading model**: Tk main thread (plus `ScDownloaderApp._ui_pool`, 2 persistent threads behind `run_async`
for search/title/season requests, and `ImageLoader`'s pool for images — both hand results back via
`after(0, ...)`); one `_download_loop` background thread that starts up to `max_parallel_episodes` worker
threads, each running one episode's `_download_one`; and two `reader` threads
per *currently downloading* episode (one per subprocess' stdout) — so up to `2 * max_parallel_episodes` reader
threads at once. Any GUI widget mutation from a background thread goes through `self.after(0, ...)` — never
touch a widget directly from `_download_loop`/`worker`/`reader`/the search threads. The UI does **not** redraw on
`progress_callback` (it's left as the default no-op): `ScDownloaderApp._tick` polls `download_manager.queue`
every 300 ms and updates cards/ring/badge/speed graph, so redraw cost is constant regardless of how many
subprocesses report progress.

**HTTP sessions**: three separate `curl_cffi` sessions — the UI's own `ScDownloaderApp.api`, the download
manager's `api`/`scrape` pair (shared with its worker threads), and `ImageLoader._session`. curl_cffi's `Session`
keeps one libcurl handle *per thread* (thread-local), which is what makes sharing a session across threads safe
(a single libcurl handle must never be used by two threads at once) — but it also means a brand-new thread gets
a brand-new handle and pays a fresh TLS handshake. That's why UI/image requests run on *persistent* pools rather
than a thread per request (measured: ~205 ms vs 260–335 ms per search; 40 posters 152 ms vs 393 ms).

**Movies** reuse the exact same pipeline: queue items with `kind: "movie"` and `episode_id: None`, for which
`ScrapeEngine.build_m3u8` omits `?episode_id=` from the iframe URL. Movie playlists can carry several audio
renditions (e.g. English + Italian), so the audio format is `bestaudio[language=ita]/bestaudio` rather than
relying on yt-dlp's notion of "best" (used for episodes too). That can't help when there is no Italian at all: a
just-released, not-yet-dubbed episode is a single muxed stream in the original language with Italian subtitles.
The site flags it with `dub_ita=0, sub_ita=1` on the episode (and on the title for movies; `get_title` returns
`dub_ita`/`sub_ita`/`original_language`) — ../SC-ServerforTV refuses to queue those. Use `DownloadManager.item_label()` for any human-readable item name
(status line, debug log) instead of formatting `SxxEyy` directly. Movies are saved flat as
`<output_folder>/Film/<Title (Year)>.mp4`.

**Series output layout is always `<output_folder>/Serie TV/<Series Name>/Stagione NN/`** (parallel to
`Film/`), even for a single-season queue —
this is intentional so downloading seasons across separate sessions doesn't split a series across a flat
folder and nested ones. `DownloadManager._resolve_dir()` reuses an existing folder case-insensitively instead
of creating a duplicate with different casing.

**On-disk files live at the repo root** (`constants.ROOT_DIR`, i.e. one level above `sc_downloader/`; both
gitignored, both optional/self-healing if deleted): `.sc_settings.json` (last-used output folder,
`max_parallel_episodes`, `concurrent_fragments`, loaded/saved by `ScDownloaderApp._load_settings`/
`_save_settings`) and `.sc_debug.log` (append-only; `DownloadManager._log_failure` writes the exact commands
and full `yt-dlp`/`ffmpeg` output whenever a download fails, so a failure can be diagnosed by reading this file
instead of reproducing it). `ROOT_DIR` is also the default output folder. The `SC_DEBUG_LOG` env var, read at import time in
`constants.py`, overrides the log path (used by ../SC-ServerforTV, where `ROOT_DIR` would land in site-packages). There's no download-history file —
that feature (and its UI panel) was removed entirely; nothing tracks past completed downloads.

**GUI notes**: pure Tk, no extra GUI toolkit. Everything with rounded corners, gradients, icons or progress
rings is drawn by hand on `tk.Canvas` (`widgets.py`) — icons are vector-drawn in `draw_icon`, not emoji, since
color-emoji fonts render inconsistently and can crash Tk on X11. Tk has no alpha on widgets, so "transparent"
tints are precomputed with `theme.blend`. Layout: a left nav rail (Scopri / Download / Opzioni, with a pending
badge and a mini progress ring) and one page shown at a time; `DetailView` is a sub-page of Scopri. Settings are a
page (auto-saved on change), not a dialog. Every page that can overflow uses `widgets.ScrollFrame`, because tiling
window managers can size the window shorter than its natural content height, clipping controls — a real,
previously-reported failure mode, not defensive boilerplate. `ScrollFrame` routes the mouse wheel globally to
whichever ScrollFrame is under the pointer. Episode selection, queue and results are keyed by identity: queue
cards track `id(item)` of `download_manager.queue` dicts, and removing an in-progress item confirms and then
calls `kill_current()` (stops the whole batch, see above). For movies `DetailView` hides the season/episode list and the action bar
enqueues the title itself (`get_title` returns `loadedSeason: null` for them). `FolderBrowserDialog` is a
themed custom folder picker replacing the native OS dialog (which doesn't match the app's theme and can't be
restyled from Tkinter). The root is created with `className="sc-downloader"` so the window's WM_CLASS is
`Sc-downloader`, matching `StartupWMClass` in the (gitignored, per-machine) `.desktop` launcher so the desktop
associates the window with the launcher's icon; the window icon itself is set via `iconphoto`.
