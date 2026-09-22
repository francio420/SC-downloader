# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A single-file Python/Tkinter desktop app (`sc_downloader.py`) that searches StreamingCommunity and downloads
episodes/movies via scraped vixcloud.co HLS streams, using `yt-dlp` + `ffmpeg`. No package structure, no test
suite, no build step — everything lives in one ~1100-line file, organized top-to-bottom as:

`StreamingCommunityAPI` → `ScrapeEngine` → `DownloadManager` → `HistoryManager` → `FolderBrowserDialog` → `ScDownloaderApp` (the Tk root) → `main()`.

## Commands

```bash
# first-time setup (Arch/CachyOS has no system pip; a venv is required)
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt

# run
./.venv/bin/python sc_downloader.py

# quick syntax/lint check (no formal linter configured in this repo)
./.venv/bin/python -c "import ast; ast.parse(open('sc_downloader.py').read())"
./.venv/bin/pip install pyflakes && ./.venv/bin/python -m pyflakes sc_downloader.py  # then pip uninstall pyflakes
```

`ffmpeg` must be on system `PATH` (not pip-installable). `.venv/` is gitignored — recreate it, don't assume it exists.

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
`--hls-prefer-native --concurrent-fragments 8`), and once both exit 0, muxes them itself with a plain
`ffmpeg -c copy`. Requires `--impersonate chrome` (curl_cffi/yt-dlp TLS impersonation) to get past vixcloud's
fingerprinting.

**`pycryptodomex` is a load-bearing dependency, not optional.** This site's HLS segments are AES-encrypted.
Without `pycryptodomex` installed, `yt-dlp` can't decrypt them natively and *silently* falls back to using
`ffmpeg` as an external downloader — which fetches fragments sequentially instead of with
`--concurrent-fragments`, and shows completely different progress-line text (`time=`/`size=...KiB` instead of
`[download] N% ... (frag X/Y)`). Confirmed ~9x throughput difference in testing. If progress parsing or
download speed regresses mysteriously, check this dependency first before touching the regexes.

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

**Threading model**: Tk main thread, one `_download_loop` background thread for the queue, and two `reader`
threads per active episode (one per subprocess' stdout). Any GUI widget mutation from a background thread goes
through `self.after(0, ...)` — never touch a widget directly from `_download_loop`/`reader`/the search threads.

**Output layout is always `<output_folder>/<Series Name>/Stagione NN/`**, even for a single-season queue —
this is intentional so downloading seasons across separate sessions doesn't split a series across a flat
folder and nested ones. `DownloadManager._resolve_dir()` reuses an existing folder case-insensitively instead
of creating a duplicate with different casing.

**Two on-disk state files live next to the script** (both gitignored, both optional/self-healing if deleted):
`.sc_history.json` (completed-download history — still written by `HistoryManager`/`DownloadManager.add()` even
though the UI panel for it was removed) and `.sc_settings.json` (last-used output folder, read on startup).

**GUI notes**: single dark (Catppuccin-ish) Tk window via `ttk.Style`. The whole layout is wrapped in a
scrollable `Canvas` (`ScDownloaderApp._build_ui`) because tiling window managers can size the window shorter
than its natural content height, clipping the bottom controls — this is a real, previously-reported failure
mode, not defensive boilerplate. `FolderBrowserDialog` is a themed custom folder picker replacing the native
OS dialog (which doesn't match the app's theme and can't be restyled from Tkinter).
