# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Python/Tkinter desktop app that searches StreamingCommunity and downloads episodes/movies via scraped
vixcloud.co HLS streams, using `yt-dlp` + `ffmpeg`. No test suite, no build step. Layout:

```
main.py                          # entry point: `python main.py`
sc_downloader/
    __init__.py                  # verifies curl_cffi/yt-dlp/pycryptodomex are importable in sys.executable
    __main__.py                  # entry point: `python -m sc_downloader`
    constants.py                 # BASE_URL, USER_AGENT, ROOT_DIR, SETTINGS_FILE, DEBUG_LOG_FILE
    api.py                       # StreamingCommunityAPI
    scraper.py                   # ScrapeEngine
    download_manager.py          # DownloadManager (the core download/threading logic)
    theme.py                     # palette, font picking, text measuring/ellipsizing, ttk style setup
    images.py                    # ImageLoader (threaded CDN fetch + Pillow processing, Pillow optional)
    widgets.py                   # Canvas-drawn reusable widgets (Button, Chip, ScrollFrame, ProgressRing, ...)
    views.py                     # the pages: SearchView, DetailView, DownloadsView, SettingsView (+ their cards)
    folder_dialog.py             # FolderBrowserDialog
    app.py                       # ScDownloaderApp (the Tk root: nav rail, page switching, queue actions) + main()
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

There is no automated test suite. Verification in this repo has been manual: run the app and exercise it, or
write small standalone scripts that instantiate `DownloadManager`/`StreamingCommunityAPI` directly and print
results (see git history for examples — e.g. probing real `yt-dlp`/`ffmpeg` output formats against a live or
public test HLS URL before wiring a regex to it). Prefer that over assuming an output format.

## Architecture

**Scraping is HTML-parsing, not a JSON API.** `StreamingCommunityAPI` fetches normal HTML pages and pulls JSON
out of the `data-page="..."` attribute (an Inertia.js SPA embeds its page props there). `ScrapeEngine` then does
a second scrape: fetch `/it/iframe/{title_id}`, regex out the vixcloud.co embed URL, fetch that, and regex the
inline `<script>` for `token`/`expires`/playlist `url` to build the final `.m3u8`. Both are brittle to upstream
markup changes by design — there's no stable API contract to rely on.

**Video and audio are separate HLS renditions on this CDN**, not a single muxed stream. `DownloadManager`
therefore launches **two parallel `yt-dlp` subprocesses** per episode (`-f bestvideo` / `-f bestaudio`, both with
`--hls-prefer-native --concurrent-fragments N`, `N` = `DownloadManager.concurrent_fragments`, default 4), and
once both exit 0, muxes them itself with a plain `ffmpeg -c copy`. Requires `--impersonate chrome`
(curl_cffi/yt-dlp TLS impersonation) to get past vixcloud's fingerprinting.

**Exception: some titles are served already muxed** (no `EXT-X-MEDIA:TYPE=AUDIO` in the master playlist; seen
on titles whose vixcloud playlist URL carries `?b=1`). There `-f bestvideo`/`-f bestaudio` match nothing, so
`_download_one` first calls `ScrapeEngine.has_separate_audio()` and, when false, runs a single `-f best`
subprocess and just remuxes it to `.mp4` (`audio_progress` mirrors `video_progress`). Related trap in
`build_m3u8`: the playlist URL may already have a query string, and the rebuilt params must always follow
`?` — joining with `&` yields `playlist/ID&b=1&token=...`, which vixcloud answers with 403.

**Multiple episodes can also download in parallel** (`DownloadManager.max_parallel_episodes`, default 1, user
configurable via the Settings dialog): `_download_loop` runs pending queue items through a
`ThreadPoolExecutor(max_workers=max_parallel_episodes)` instead of a sequential loop. Because of this,
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

**Process lifecycle**: every `yt-dlp` subprocess is started with `start_new_session=True` so
`DownloadManager.kill_current()` can `os.killpg(...)` the whole process group (including any `ffmpeg` child)
instead of leaving orphaned downloads running after Stop/window-close. `kill_current()` is the single choke
point for stopping — both the Stop button and the window-close handler (with a confirmation dialog if a
download is active) route through it.

**Threading model**: Tk main thread (plus `ScDownloaderApp.run_async` threads for search/title/season requests
and `ImageLoader`'s pool for images — both hand results back via `after(0, ...)`); one `_download_loop` background thread owning a `ThreadPoolExecutor`
(size `max_parallel_episodes`) whose workers each run one episode's `_download_one`; and two `reader` threads
per *currently downloading* episode (one per subprocess' stdout) — so up to `2 * max_parallel_episodes` reader
threads at once. Any GUI widget mutation from a background thread goes through `self.after(0, ...)` — never
touch a widget directly from `_download_loop`/`worker`/`reader`/the search threads. The UI does **not** redraw on
`progress_callback` (it's left as the default no-op): `ScDownloaderApp._tick` polls `download_manager.queue`
every 300 ms and updates cards/ring/badge/speed graph, so redraw cost is constant regardless of how many
subprocesses report progress.

**Movies** reuse the exact same pipeline: queue items with `kind: "movie"` and `episode_id: None`, for which
`ScrapeEngine.build_m3u8` omits `?episode_id=` from the iframe URL. Movie playlists can carry several audio
renditions (e.g. English + Italian), so the audio format is `bestaudio[language=ita]/bestaudio` rather than
relying on yt-dlp's notion of "best". Use `DownloadManager.item_label()` for any human-readable item name
(status line, debug log) instead of formatting `SxxEyy` directly. Movies are saved flat as
`<output_folder>/Film/<Title (Year)>.mp4`.

**Series output layout is always `<output_folder>/<Series Name>/Stagione NN/`**, even for a single-season queue —
this is intentional so downloading seasons across separate sessions doesn't split a series across a flat
folder and nested ones. `DownloadManager._resolve_dir()` reuses an existing folder case-insensitively instead
of creating a duplicate with different casing.

**On-disk files live at the repo root** (`constants.ROOT_DIR`, i.e. one level above `sc_downloader/`; both
gitignored, both optional/self-healing if deleted): `.sc_settings.json` (last-used output folder,
`max_parallel_episodes`, `concurrent_fragments`, loaded/saved by `ScDownloaderApp._load_settings`/
`_save_settings`) and `.sc_debug.log` (append-only; `DownloadManager._log_failure` writes the exact commands
and full `yt-dlp`/`ffmpeg` output whenever a download fails, so a failure can be diagnosed by reading this file
instead of reproducing it). `ROOT_DIR` is also the default output folder. There's no download-history file —
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
restyled from Tkinter).
