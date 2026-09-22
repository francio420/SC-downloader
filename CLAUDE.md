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
    folder_dialog.py             # FolderBrowserDialog
    settings_dialog.py           # SettingsDialog (parallel episodes / concurrent fragments)
    app.py                       # ScDownloaderApp (the Tk root) + main()
```

`sc_downloader/` was split out of a single ~1150-line `sc_downloader.py` along its existing class boundaries —
one module per class, no deeper nesting (no `gui/`/`core/` subpackages). Keep new code in the matching module
rather than reintroducing a monolith; only `app.py` should import Tkinter widgets from outside `folder_dialog.py`.

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

`ffmpeg` must be on system `PATH` (not pip-installable). `.venv/` is gitignored — recreate it, don't assume it
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

**Threading model**: Tk main thread; one `_download_loop` background thread owning a `ThreadPoolExecutor`
(size `max_parallel_episodes`) whose workers each run one episode's `_download_one`; and two `reader` threads
per *currently downloading* episode (one per subprocess' stdout) — so up to `2 * max_parallel_episodes` reader
threads at once. Any GUI widget mutation from a background thread goes through `self.after(0, ...)` — never
touch a widget directly from `_download_loop`/`worker`/`reader`/the search threads.

**Output layout is always `<output_folder>/<Series Name>/Stagione NN/`**, even for a single-season queue —
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

**GUI notes**: single dark (Catppuccin-ish) Tk window via `ttk.Style`. A `tk.Menu` menu bar (`_build_menu`)
holds "Impostazioni", opening `SettingsDialog` — on Linux this renders *inside* the window below the title bar,
not in a desktop-global menu bar (that's a macOS/Qt-appmenu thing Tk doesn't implement). The whole layout below
it is wrapped in a scrollable `Canvas` (`ScDownloaderApp._build_ui`) because tiling window managers can size
the window shorter than its natural content height, clipping the bottom controls — this is a real,
previously-reported failure mode, not defensive boilerplate. `FolderBrowserDialog` is a themed custom folder
picker replacing the native OS dialog (which doesn't match the app's theme and can't be restyled from
Tkinter).
