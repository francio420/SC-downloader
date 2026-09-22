#!/usr/bin/env python3
"""
SC Downloader - StreamingCommunity Downloader con Ricerca Integrata
Scarica video da StreamingCommunity con interfaccia grafica tkinter.
"""

import glob
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk
from urllib.parse import urljoin, urlparse, parse_qs, urlencode, urlunparse

try:
    from curl_cffi import requests as curl_requests
except ImportError:
    print("Errore: curl_cffi non installato. Esegui: pip install curl_cffi")
    sys.exit(1)

# ─── Costanti ────────────────────────────────────────────────────────────────

BASE_URL = "https://streamingcommunityz.tax"
CDN_URL = "https://cdn.streamingcommunityz.tax"
HISTORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".sc_history.json")
SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".sc_settings.json")
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


# ─── StreamingCommunityAPI ───────────────────────────────────────────────────

class StreamingCommunityAPI:
    """Comunicazione con StreamingCommunity parsing data-page HTML."""

    def __init__(self):
        self.session = curl_requests.Session(impersonate="chrome")

    def _headers(self):
        return {
            "User-Agent": USER_AGENT,
            "Referer": f"{BASE_URL}/",
        }

    def _parse_data_page(self, html):
        """Estrae il JSON dal data-page attribute di Inertia.js."""
        m = re.search(r'data-page="([^"]+)"', html)
        if not m:
            return None
        return json.loads(m.group(1).replace("&quot;", '"').replace("&amp;", "&"))

    def search(self, query, page=1):
        """Cerca titoli. Restituisce lista di dict con id, name, type, score, slug, seasons_count."""
        params = {"q": query, "page": page}
        resp = self.session.get(f"{BASE_URL}/it/search", headers=self._headers(), params=params)
        data = self._parse_data_page(resp.text)
        if not data:
            return [], 0
        titles = data.get("props", {}).get("titles", [])
        total = data.get("props", {}).get("totalCount", 0)
        results = []
        for t in titles:
            results.append({
                "id": t["id"],
                "name": t["name"],
                "slug": t["slug"],
                "type": t.get("type", "tv"),
                "score": t.get("score", "N/A"),
                "seasons_count": t.get("seasons_count", 0),
                "sub_ita": t.get("sub_ita", 0),
                "last_air_date": t.get("last_air_date"),
                "images": t.get("images", []),
            })
        return results, total

    def get_title(self, title_id, slug):
        """Ottiene dettagli titolo con lista stagioni e episodi della prima stagione."""
        url = f"{BASE_URL}/it/titles/{title_id}-{slug}"
        resp = self.session.get(url, headers=self._headers())
        data = self._parse_data_page(resp.text)
        if not data:
            return None
        props = data.get("props", {})
        title = props.get("title", {})
        loaded_season = props.get("loadedSeason", {})
        seasons = title.get("seasons", [])
        episodes = loaded_season.get("episodes", [])
        return {
            "id": title.get("id", title_id),
            "name": title.get("name", ""),
            "slug": title.get("slug", slug),
            "seasons": seasons,
            "loaded_season_number": loaded_season.get("number", 1),
            "episodes": episodes,
        }

    def get_season(self, title_id, slug, season_number):
        """Ottiene episodi di una stagione specifica."""
        url = f"{BASE_URL}/it/titles/{title_id}-{slug}/season-{season_number}"
        resp = self.session.get(url, headers=self._headers())
        data = self._parse_data_page(resp.text)
        if not data:
            return []
        loaded_season = data.get("props", {}).get("loadedSeason", {})
        return loaded_season.get("episodes", [])


# ─── ScrapeEngine ────────────────────────────────────────────────────────────

class ScrapeEngine:
    """Estrazione URL M3U8 da vixcloud.co."""

    def __init__(self, session=None):
        self.session = session or curl_requests.Session(impersonate="chrome")

    def build_m3u8(self, title_id, episode_id):
        """Costruisce l'URL M3U8 partendo dal title_id e episode_id."""
        # Step 1: Fetch the iframe page to get the vixcloud embed URL
        iframe_url = f"{BASE_URL}/it/iframe/{title_id}?episode_id={episode_id}"
        resp_html = self.session.get(
            iframe_url,
            headers={"User-Agent": USER_AGENT, "Referer": f"{BASE_URL}/it/watch/{title_id}"},
        )

        vix_match = re.search(r'src="(https://vixcloud\.co/embed[^"]+)"', resp_html.text)
        if not vix_match:
            raise Exception("Impossibile trovare l'embed vixcloud.co")

        vix_url = vix_match.group(1).replace("&amp;", "&")

        # Step 2: Fetch the vixcloud embed page to get playlist info
        resp_vix = self.session.get(
            vix_url,
            headers={"User-Agent": USER_AGENT, "Referer": f"{BASE_URL}/"},
        )

        if resp_vix.status_code != 200:
            raise Exception(f"Errore vixcloud: HTTP {resp_vix.status_code}")

        content = resp_vix.text

        token_match = re.search(r"'token':\s*'([^']+)'", content)
        expires_match = re.search(r"'expires':\s*'([^']+)'", content)
        url_match = re.search(r"url:\s*'(https?://[^']+)'", content)
        fhd_match = re.search(r"canPlayFHD\s*=\s*(true|false)", content)

        if not all([token_match, expires_match, url_match]):
            raise Exception("Impossibile estrarre token/url da vixcloud")

        token = token_match.group(1)
        expires = expires_match.group(1)
        playlist_url = url_match.group(1)
        can_fhd = fhd_match.group(1) == "true" if fhd_match else False

        parsed = urlparse(playlist_url)
        params = parse_qs(parsed.query, keep_blank_values=True)
        params["token"] = [token]
        params["expires"] = [expires]
        if can_fhd:
            params["h"] = ["1"]
        flat_params = "&".join(f"{k}={v[0]}" for k, v in params.items())
        sep = "&" if parsed.query else "?"
        m3u8_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}{sep}{flat_params}"

        return m3u8_url


# ─── DownloadManager ─────────────────────────────────────────────────────────

class DownloadManager:
    """Gestisce la coda di download con threading."""

    def __init__(self, output_folder, progress_callback=None, status_callback=None, finished_callback=None):
        self.output_folder = output_folder
        self.progress_callback = progress_callback or (lambda *a: None)
        self.status_callback = status_callback or (lambda *a: None)
        self.finished_callback = finished_callback or (lambda *a: None)
        self.queue = []
        self.current_index = -1
        self.is_downloading = False
        self._stop_flag = False
        self._current_processes = []
        self.api = StreamingCommunityAPI()
        self.scrape = ScrapeEngine(session=self.api.session)
        self.history = HistoryManager()

    def kill_current(self):
        """Termina immediatamente il download in corso (video e audio scaricati
        in parallelo, e i loro eventuali processi figli come ffmpeg), evitando
        che restino orfani in background."""
        self._stop_flag = True
        for process in list(self._current_processes):
            if process and process.poll() is None:
                try:
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                except (ProcessLookupError, PermissionError, OSError):
                    process.kill()

    def add(self, item):
        """Aggiunge un episodio alla coda. item = {title_name, season, episode, episode_name, scws_id, duration}"""
        item["status"] = "in_coda"
        item["progress"] = 0
        item["video_progress"] = 0
        item["audio_progress"] = 0
        item["audio_started"] = False
        self.queue.append(item)

    def remove(self, index):
        if 0 <= index < len(self.queue):
            if index == self.current_index:
                self._stop_flag = True
            self.queue.pop(index)
            if self.current_index >= len(self.queue):
                self.current_index = len(self.queue) - 1

    def clear(self):
        self._stop_flag = True
        self.queue.clear()
        self.current_index = -1

    def start_all(self):
        if self.is_downloading:
            return
        self.is_downloading = True
        self._stop_flag = False
        thread = threading.Thread(target=self._download_loop, daemon=True)
        thread.start()

    def _download_loop(self):
        total = len(self.queue)
        for i, item in enumerate(self.queue):
            if self._stop_flag:
                break
            if item["status"] == "completato":
                continue
            self.current_index = i
            item["status"] = "in_corso"
            self.status_callback(
                f"Episodio {i + 1}/{total} - {item['title_name']} S{item['season']:02d}E{item['episode']:02d}..."
            )
            self.progress_callback(self._overall_progress())
            try:
                self._download_one(item)
                if self._stop_flag:
                    # Interrotto dall'utente: non e' completato, va ripreso
                    # in un successivo avvio invece di essere segnato come
                    # scaricato con successo.
                    item["status"] = "in_coda"
                    item["progress"] = 0
                    item["size_mb"] = 0
                else:
                    item["status"] = "completato"
                    item["progress"] = 100
                    self.history.add({
                        "title": item["title_name"],
                        "season": item["season"],
                        "episode": item["episode"],
                        "episode_name": item.get("episode_name", ""),
                        "filename": item.get("filename", ""),
                        "size_mb": item.get("size_mb", 0),
                        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    })
            except Exception as e:
                item["status"] = "errore"
                item["error"] = str(e)
                self.status_callback(f"Errore: {e}")
            self.progress_callback(self._overall_progress())
        self.is_downloading = False
        self.current_index = -1
        self.finished_callback()

    def _overall_progress(self):
        """Percentuale complessiva su tutti gli elementi in coda."""
        if not self.queue:
            return 0
        return sum(i.get("progress", 0) for i in self.queue) / len(self.queue)

    @staticmethod
    def _resolve_dir(parent, name):
        """Riusa una sottocartella di 'parent' gia' esistente con lo stesso nome
        (case-insensitive) invece di crearne una nuova; altrimenti la crea."""
        try:
            for entry in os.listdir(parent):
                if entry.lower() == name.lower() and os.path.isdir(os.path.join(parent, entry)):
                    return os.path.join(parent, entry)
        except OSError:
            pass
        path = os.path.join(parent, name)
        os.makedirs(path, exist_ok=True)
        return path

    def _download_one(self, item):
        m3u8_url = self.scrape.build_m3u8(item["title_id"], item["episode_id"])

        safe_name = re.sub(r'[<>:"/\\|?*]', '_', item["title_name"])
        filename = f"{safe_name}_S{item['season']:02d}E{item['episode']:02d}"
        item["filename"] = filename

        # Cartella <output>/<Serie>/<Stagione NN>/, sempre, cosi' la struttura
        # resta coerente anche scaricando le stagioni in sessioni separate
        # (altrimenti scaricare una stagione alla volta non creerebbe mai la
        # sottocartella, mescolando le stagioni nella cartella della serie).
        # Riusa cartelle gia' esistenti (case-insensitive) invece di duplicarle.
        dest_dir = self._resolve_dir(self.output_folder, safe_name)
        dest_dir = self._resolve_dir(dest_dir, f"Stagione {item['season']:02d}")

        def disk_size_mb():
            """Somma la dimensione reale su disco dei file di questo episodio
            (i .part di video e audio in scaricamento, o il file finale dopo
            il merge). E' l'unica fonte di verita' per il peso: niente stime
            "~" che possono sovra/sottostimare il totale."""
            total = 0
            for path in glob.glob(os.path.join(dest_dir, filename + "*")):
                try:
                    total += os.path.getsize(path)
                except OSError:
                    pass
            return total / (1024 * 1024)

        base_args = [
            sys.executable, "-u", "-m", "yt_dlp",
            "--newline",
            "--referer", "https://vixcloud.co/",
            "--add-header", "Origin:https://vixcloud.co",
            "--impersonate", "chrome",
            "--hls-prefer-native",
            "--concurrent-fragments", "8",
        ]
        streams = {
            "video": {
                "template": os.path.join(dest_dir, f"{filename}.video.%(ext)s"),
                "format": "bestvideo",
            },
            "audio": {
                "template": os.path.join(dest_dir, f"{filename}.audio.%(ext)s"),
                "format": "bestaudio",
            },
        }

        popen_kwargs = dict(
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            encoding="utf-8", errors="replace", bufsize=1,
            start_new_session=True,  # permette di terminare anche i figli (es. ffmpeg) come gruppo
        )
        for key, s in streams.items():
            cmd = base_args + ["-f", s["format"], "-o", s["template"], m3u8_url]
            s["process"] = subprocess.Popen(cmd, **popen_kwargs)

        self._current_processes = [s["process"] for s in streams.values()]
        item["audio_started"] = True  # video e audio partono insieme

        def reader(key, process):
            """Legge l'output di un singolo stream (video o audio) e ne
            aggiorna la percentuale/velocita' in modo indipendente
            dall'altro, dato che ora scaricano in parallelo."""
            for line in process.stdout:
                if self._stop_flag:
                    break

                pkey = f"{key}_progress"
                frag_match = re.search(r"\(frag\s+(\d+)/(\d+)\)", line)
                if frag_match:
                    n, m = int(frag_match.group(1)), int(frag_match.group(2))
                    if m > 0:
                        item[pkey] = max(item.get(pkey, 0), min(100.0, n / m * 100))
                else:
                    pct_match = re.search(r"\[download\]\s+([\d.]+)%", line)
                    if pct_match:
                        item[pkey] = max(item.get(pkey, 0), min(100.0, float(pct_match.group(1))))

                speed_match = re.search(r"at\s+([\d.]+)\s*([KMG])i?B/s", line)
                if speed_match:
                    value, unit = float(speed_match.group(1)), speed_match.group(2)
                    scale = {"K": 1 / 1024, "M": 1, "G": 1024}[unit]
                    item[f"{key}_speed_mb_s"] = value * scale

                # Fallback per il raro caso in cui yt-dlp deleghi questo
                # stream a ffmpeg (es. crypto non disponibile): usa il tempo
                # processato rispetto alla durata nota dell'episodio.
                time_match = re.search(r"time=(\d+):(\d{2}):(\d{2})\.\d+", line)
                if time_match and item.get("duration"):
                    h, m2, s2 = (int(g) for g in time_match.groups())
                    total_seconds = item["duration"] * 60
                    if total_seconds > 0:
                        candidate = min(99.0, (h * 3600 + m2 * 60 + s2) / total_seconds * 100)
                        item[pkey] = max(item.get(pkey, 0), candidate)

                item["progress"] = (item.get("video_progress", 0) + item.get("audio_progress", 0)) / 2
                item["speed_mb_s"] = item.get("video_speed_mb_s", 0) + item.get("audio_speed_mb_s", 0)
                self.progress_callback(self._overall_progress())

            process.wait()

        threads = [
            threading.Thread(target=reader, args=(key, s["process"]), daemon=True)
            for key, s in streams.items()
        ]
        for t in threads:
            t.start()

        last_disk_check = 0.0
        while any(t.is_alive() for t in threads):
            if self._stop_flag:
                self.kill_current()
                break
            now = time.monotonic()
            if now - last_disk_check >= 1.0:
                last_disk_check = now
                size_mb = disk_size_mb()
                if size_mb:
                    item["size_mb"] = size_mb
                    self.progress_callback(self._overall_progress())
            time.sleep(0.2)

        for t in threads:
            t.join(timeout=5)

        item["speed_mb_s"] = 0
        self._current_processes = []

        if self._stop_flag:
            return

        video_rc = streams["video"]["process"].returncode
        audio_rc = streams["audio"]["process"].returncode
        if video_rc != 0 or audio_rc != 0:
            raise Exception(f"yt-dlp fallito (video={video_rc}, audio={audio_rc})")

        video_files = glob.glob(os.path.join(dest_dir, f"{filename}.video.*"))
        audio_files = glob.glob(os.path.join(dest_dir, f"{filename}.audio.*"))
        if not video_files or not audio_files:
            raise Exception("File video o audio mancante dopo il download")
        video_file, audio_file = video_files[0], audio_files[0]

        final_path = os.path.join(dest_dir, f"{filename}.mp4")
        merge = subprocess.run(
            ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
             "-i", video_file, "-i", audio_file, "-c", "copy", final_path],
            capture_output=True, text=True,
        )
        if merge.returncode != 0:
            raise Exception(f"ffmpeg merge fallito: {merge.stderr[-300:]}")

        os.remove(video_file)
        os.remove(audio_file)

        size_mb = disk_size_mb()  # ora resta solo il file finale unito
        if size_mb:
            item["size_mb"] = size_mb


# ─── HistoryManager ──────────────────────────────────────────────────────────

class HistoryManager:
    """Gestisce la storia dei download in un file JSON."""

    def __init__(self, filepath=HISTORY_FILE):
        self.filepath = filepath
        self.entries = self._load()

    def _load(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return []
        return []

    def _save(self):
        with open(self.filepath, "w", encoding="utf-8") as f:
            json.dump(self.entries, f, ensure_ascii=False, indent=2)

    def add(self, entry):
        self.entries.insert(0, entry)
        self._save()

    def get_all(self):
        return self.entries

    def clear(self):
        self.entries = []
        self._save()


# ─── FolderBrowserDialog ─────────────────────────────────────────────────────

class FolderBrowserDialog:
    """Selettore di cartelle con lo stesso tema scuro del resto dell'app,
    al posto del dialogo nativo del sistema operativo."""

    def __init__(self, parent, start_dir):
        self.result = None
        self.current_dir = start_dir

        self.top = tk.Toplevel(parent)
        self.top.title("Scegli cartella di destinazione")
        self.top.configure(bg="#1e1e2e")
        self.top.geometry("560x420")
        self.top.minsize(420, 300)
        self.top.transient(parent)
        self.top.grab_set()

        path_frame = ttk.Frame(self.top)
        path_frame.pack(fill="x", padx=10, pady=10)
        ttk.Label(path_frame, text="Percorso:").pack(side="left", padx=(0, 5))
        self.path_var = tk.StringVar()
        path_entry = ttk.Entry(path_frame, textvariable=self.path_var)
        path_entry.pack(side="left", fill="x", expand=True)
        path_entry.bind("<Return>", self._go_to_typed_path)

        list_frame = ttk.Frame(self.top)
        list_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        list_scroll = ttk.Scrollbar(list_frame)
        list_scroll.pack(side="right", fill="y")

        self.listbox = tk.Listbox(
            list_frame, bg="#313244", fg="#cdd6f4",
            selectbackground="#585b70", selectforeground="#cdd6f4",
            font=("Segoe UI", 10), activestyle="none", borderwidth=0,
            highlightthickness=1, highlightcolor="#45475a",
            yscrollcommand=list_scroll.set,
        )
        self.listbox.pack(side="left", fill="both", expand=True)
        list_scroll.config(command=self.listbox.yview)
        self.listbox.bind("<Double-Button-1>", self._on_double_click)
        self.listbox.bind("<Return>", self._on_double_click)

        btn_frame = ttk.Frame(self.top)
        btn_frame.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Button(btn_frame, text="Su", command=self._go_up).pack(side="left")
        ttk.Button(btn_frame, text="Annulla", command=self._cancel).pack(side="right")
        ttk.Button(btn_frame, text="Seleziona questa cartella", style="Accent.TButton",
                   command=self._confirm).pack(side="right", padx=5)

        self.top.protocol("WM_DELETE_WINDOW", self._cancel)
        self._refresh(start_dir)

    def _refresh(self, path):
        try:
            subdirs = sorted(
                (e for e in os.listdir(path) if not e.startswith(".") and os.path.isdir(os.path.join(path, e))),
                key=str.lower,
            )
        except OSError:
            subdirs = []
        self.current_dir = path
        self.path_var.set(path)
        self.listbox.delete(0, "end")
        for name in subdirs:
            self.listbox.insert("end", f"📁 {name}")

    def _go_to_typed_path(self, event=None):
        path = self.path_var.get().strip()
        if os.path.isdir(path):
            self._refresh(path)

    def _go_up(self):
        parent = os.path.dirname(self.current_dir.rstrip(os.sep))
        if parent and os.path.isdir(parent):
            self._refresh(parent)

    def _on_double_click(self, event=None):
        sel = self.listbox.curselection()
        if not sel:
            return
        name = self.listbox.get(sel[0])[2:].strip()
        new_path = os.path.join(self.current_dir, name)
        if os.path.isdir(new_path):
            self._refresh(new_path)

    def _confirm(self):
        self.result = self.current_dir
        self.top.destroy()

    def _cancel(self):
        self.result = None
        self.top.destroy()

    def show(self):
        self.top.wait_window()
        return self.result


# ─── ScDownloaderApp ─────────────────────────────────────────────────────────

class ScDownloaderApp(tk.Tk):
    """Interfaccia grafica principale."""

    def __init__(self):
        super().__init__()
        self.title("SC Downloader")
        self.geometry("750x850")
        self.minsize(650, 700)
        self.configure(bg="#1e1e2e")

        self.download_manager = None
        self.api = None
        self.current_results = []
        self.current_title_data = None
        self.queue_row_ids = []
        self.output_folder = self._load_output_folder()

        self._setup_styles()
        self._build_ui()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self):
        if self.download_manager and self.download_manager.is_downloading:
            if not messagebox.askyesno(
                "Download in corso",
                "Un download è in corso. Chiudendo il programma verrà interrotto. Continuare?",
            ):
                return
            self.download_manager.kill_current()
        self.destroy()

    def _load_output_folder(self):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                folder = json.load(f).get("output_folder")
            if folder and os.path.isdir(folder):
                return folder
        except (OSError, json.JSONDecodeError):
            pass
        return os.path.dirname(os.path.abspath(__file__))

    def _save_output_folder(self):
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump({"output_folder": self.output_folder}, f)
        except OSError:
            pass

    def _setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")

        style.configure(".", background="#1e1e2e", foreground="#cdd6f4", font=("Segoe UI", 10))
        style.configure("TFrame", background="#1e1e2e")
        style.configure("TLabel", background="#1e1e2e", foreground="#cdd6f4")
        style.configure("TButton", background="#313244", foreground="#cdd6f4", padding=6)
        style.map("TButton", background=[("active", "#45475a")])
        style.configure("Accent.TButton", background="#89b4fa", foreground="#1e1e2e", padding=8)
        style.map("Accent.TButton", background=[("active", "#74c7ec")])
        style.configure("Danger.TButton", background="#f38ba8", foreground="#1e1e2e", padding=6)
        style.map("Danger.TButton", background=[("active", "#eba0ac")])
        style.configure("TCheckbutton", background="#1e1e2e", foreground="#cdd6f4")
        style.configure("TEntry", fieldbackground="#313244", foreground="#cdd6f4")
        style.configure("TCombobox", fieldbackground="#313244", foreground="#cdd6f4")
        style.configure("Treeview", background="#313244", foreground="#cdd6f4", fieldbackground="#313244", rowheight=28)
        style.configure("Treeview.Heading", background="#45475a", foreground="#cdd6f4")
        style.map("Treeview", background=[("selected", "#585b70")])
        style.configure("Horizontal.TProgressbar", background="#89b4fa", troughcolor="#313244")

    def _build_ui(self):
        # ── Contenitore scrollabile ──
        # Necessario perché con window manager a tiling la finestra puo'
        # essere ridimensionata piu' piccola del contenuto, tagliando i
        # controlli in basso (es. il pulsante "Scarica Tutti").
        canvas = tk.Canvas(self, bg="#1e1e2e", highlightthickness=0)
        canvas.pack(side="left", fill="both", expand=True)

        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        scrollbar.pack(side="right", fill="y")
        canvas.configure(yscrollcommand=scrollbar.set)

        container = ttk.Frame(canvas)
        container_id = canvas.create_window((0, 0), window=container, anchor="nw")

        def _on_container_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_configure(event):
            canvas.itemconfig(container_id, width=event.width)

        container.bind("<Configure>", _on_container_configure)
        canvas.bind("<Configure>", _on_canvas_configure)

        def _on_mousewheel(event):
            if event.num == 4:
                canvas.yview_scroll(-1, "units")
            elif event.num == 5:
                canvas.yview_scroll(1, "units")
            else:
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        canvas.bind_all("<Button-4>", _on_mousewheel)
        canvas.bind_all("<Button-5>", _on_mousewheel)

        # ── Top: Ricerca ──
        search_frame = ttk.Frame(container)
        search_frame.pack(fill="x", padx=10, pady=(10, 5))

        ttk.Label(search_frame, text="Ricerca:").pack(side="left", padx=(0, 5))
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(search_frame, textvariable=self.search_var, width=40)
        self.search_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        self.search_entry.bind("<Return>", lambda e: self._do_search())

        self.btn_search = ttk.Button(search_frame, text="Cerca", command=self._do_search)
        self.btn_search.pack(side="left", padx=(0, 5))

        self.search_status = ttk.Label(search_frame, text="", foreground="#a6adc8")
        self.search_status.pack(side="left", padx=5)

        # ── Risultati ricerca ──
        results_label = ttk.Label(container, text="Risultati Ricerca", font=("Segoe UI", 10, "bold"))
        results_label.pack(anchor="w", padx=10, pady=(5, 2))

        results_frame = ttk.Frame(container)
        results_frame.pack(fill="x", padx=10, pady=(0, 5))

        self.results_listbox = tk.Listbox(
            results_frame, height=5, bg="#313244", fg="#cdd6f4",
            selectbackground="#585b70", selectforeground="#cdd6f4",
            font=("Segoe UI", 10), activestyle="none", borderwidth=0,
            highlightthickness=1, highlightcolor="#45475a",
        )
        self.results_listbox.pack(fill="x")
        self.results_listbox.bind("<Double-Button-1>", lambda e: self._select_title())

        btn_results = ttk.Frame(results_frame)
        btn_results.pack(fill="x", pady=(3, 0))
        ttk.Button(btn_results, text="Seleziona", command=self._select_title).pack(side="left")
        ttk.Button(btn_results, text="Pagina successiva", command=self._next_page).pack(side="right")

        # ── Episodi ──
        episodes_label = ttk.Label(container, text="Episodi", font=("Segoe UI", 10, "bold"))
        episodes_label.pack(anchor="w", padx=10, pady=(5, 2))

        ep_header = ttk.Frame(container)
        ep_header.pack(fill="x", padx=10)
        ttk.Label(ep_header, text="Stagione:").pack(side="left")
        self.season_var = tk.StringVar()
        self.season_combo = ttk.Combobox(ep_header, textvariable=self.season_var, state="readonly", width=5)
        self.season_combo.pack(side="left", padx=5)
        self.season_combo.bind("<<ComboboxSelected>>", lambda e: self._load_season_episodes())

        self.ep_title_label = ttk.Label(ep_header, text="", foreground="#a6adc8")
        self.ep_title_label.pack(side="left", padx=10)

        episodes_frame = ttk.Frame(container)
        episodes_frame.pack(fill="x", padx=10, pady=(0, 3))

        # Scrollbar per episodi
        ep_scroll = ttk.Scrollbar(episodes_frame)
        ep_scroll.pack(side="right", fill="y")

        self.episodes_listbox = tk.Listbox(
            episodes_frame, height=6, bg="#313244", fg="#cdd6f4",
            selectbackground="#585b70", selectforeground="#cdd6f4",
            font=("Segoe UI", 10), activestyle="none", borderwidth=0,
            highlightthickness=1, highlightcolor="#45475a",
            selectmode="extended", yscrollcommand=ep_scroll.set,
        )
        self.episodes_listbox.pack(fill="x")
        ep_scroll.config(command=self.episodes_listbox.yview)

        btn_ep = ttk.Frame(container)
        btn_ep.pack(fill="x", padx=10, pady=(0, 8))
        ttk.Button(btn_ep, text="Aggiungi Selezionati alla Coda", command=self._add_to_queue).pack(side="left")
        ttk.Button(btn_ep, text="Seleziona Tutti", command=self._select_all_episodes).pack(side="left", padx=5)
        ttk.Button(btn_ep, text="Deseleziona Tutti", command=self._deselect_all_episodes).pack(side="left")

        # ── Separatore ──
        ttk.Separator(container, orient="horizontal").pack(fill="x", padx=10, pady=3)

        # ── Coda Download ──
        queue_label = ttk.Label(container, text="Coda Download", font=("Segoe UI", 10, "bold"))
        queue_label.pack(anchor="w", padx=10, pady=(3, 2))

        queue_frame = ttk.Frame(container)
        queue_frame.pack(fill="both", expand=True, padx=10, pady=(0, 3))

        cols = ("titolo", "stato", "progresso")
        self.queue_tree = ttk.Treeview(queue_frame, columns=cols, show="headings", height=5)
        self.queue_tree.heading("titolo", text="Titolo")
        self.queue_tree.heading("stato", text="Stato")
        self.queue_tree.heading("progresso", text="Progresso")
        self.queue_tree.column("titolo", width=280)
        self.queue_tree.column("stato", width=100)
        self.queue_tree.column("progresso", width=290, anchor="center")
        self.queue_tree.pack(side="left", fill="both", expand=True)

        q_scroll = ttk.Scrollbar(queue_frame, orient="vertical", command=self.queue_tree.yview)
        q_scroll.pack(side="right", fill="y")
        self.queue_tree.configure(yscrollcommand=q_scroll.set)

        btn_queue = ttk.Frame(container)
        btn_queue.pack(fill="x", padx=10, pady=(0, 5))
        ttk.Button(btn_queue, text="Rimuovi", command=self._remove_from_queue).pack(side="left")
        ttk.Button(btn_queue, text="Svuota Coda", command=self._clear_queue).pack(side="left", padx=5)

        # ── Controlli ──
        ctrl_frame = ttk.Frame(container)
        ctrl_frame.pack(fill="x", padx=10, pady=(0, 3))

        self.btn_download = ttk.Button(ctrl_frame, text="Scarica Tutti", style="Accent.TButton", command=self._start_download)
        self.btn_download.pack(side="left")

        self.btn_stop = ttk.Button(ctrl_frame, text="Interrompi", style="Danger.TButton", command=self._stop_download, state="disabled")
        self.btn_stop.pack(side="left", padx=5)

        ttk.Label(ctrl_frame, text="Cartella:").pack(side="left", padx=(15, 3))
        self.folder_var = tk.StringVar(value=self.output_folder)
        self.folder_entry = ttk.Entry(ctrl_frame, textvariable=self.folder_var, width=30, state="readonly")
        self.folder_entry.pack(side="left", fill="x", expand=True, padx=(0, 3))
        ttk.Button(ctrl_frame, text="Sfoglia", command=self._browse_folder).pack(side="left")

        # ── Progresso ──
        progress_frame = ttk.Frame(container)
        progress_frame.pack(fill="x", padx=10, pady=(0, 3))

        progress_row = ttk.Frame(progress_frame)
        progress_row.pack(fill="x")

        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(progress_row, variable=self.progress_var, maximum=100, mode="determinate")
        self.progress_bar.pack(side="left", fill="x", expand=True)

        self.overall_pct_label = ttk.Label(progress_row, text="0%", width=5, anchor="e")
        self.overall_pct_label.pack(side="left", padx=(5, 0))

        self.status_label = ttk.Label(progress_frame, text="Pronto", foreground="#a6adc8")
        self.status_label.pack(anchor="w", pady=(2, 0))

    # ── Ricerca ──────────────────────────────────────────────────────────────

    def _do_search(self):
        query = self.search_var.get().strip()
        if not query:
            return
        self.search_status.config(text="Ricerca in corso...")
        self.btn_search.config(state="disabled")
        threading.Thread(target=self._search_thread, args=(query,), daemon=True).start()

    def _search_thread(self, query):
        try:
            results, total = self.api.search(query)
            self.after(0, self._show_results, results, total)
        except Exception as e:
            self.after(0, lambda: self.search_status.config(text=f"Errore: {e}"))
            self.after(0, lambda: self.btn_search.config(state="normal"))

    def _show_results(self, results, total):
        self.current_results = results
        self.current_page = 1
        self.results_listbox.delete(0, "end")
        for r in results:
            tipo = "📺" if r["type"] == "tv" else "🎬"
            score = r.get("score", "N/A")
            seasons = f"  S1-{r['seasons_count']}" if r["type"] == "tv" and r.get("seasons_count", 0) > 0 else ""
            self.results_listbox.insert("end", f"{tipo} {r['name']}  ⭐{score}{seasons}")
        self.search_status.config(text=f"{len(results)} risultati (totale: {total})")
        self.btn_search.config(state="normal")

    def _next_page(self):
        query = self.search_var.get().strip()
        if not query:
            return
        self.current_page = getattr(self, "current_page", 1) + 1
        self.search_status.config(text=f"Pagina {self.current_page}...")
        threading.Thread(target=self._search_page_thread, args=(query, self.current_page), daemon=True).start()

    def _search_page_thread(self, query, page):
        try:
            results, total = self.api.search(query, page)
            self.after(0, self._show_results, results, total)
        except Exception as e:
            self.after(0, lambda: self.search_status.config(text=f"Errore: {e}"))

    # ── Selezione Titolo ─────────────────────────────────────────────────────

    def _select_title(self):
        sel = self.results_listbox.curselection()
        if not sel:
            messagebox.showwarning("Attenzione", "Seleziona un titolo dalla lista")
            return
        idx = sel[0]
        if idx >= len(self.current_results):
            return
        title = self.current_results[idx]
        self.ep_title_label.config(text=f"Caricamento {title['name']}...")
        threading.Thread(target=self._load_title_thread, args=(title,), daemon=True).start()

    def _load_title_thread(self, title):
        try:
            data = self.api.get_title(title["id"], title["slug"])
            self.after(0, self._show_title_data, data)
        except Exception as e:
            self.after(0, lambda: self.ep_title_label.config(text=f"Errore: {e}"))

    def _show_title_data(self, data):
        if not data:
            self.ep_title_label.config(text="Errore nel caricamento")
            return
        self.current_title_data = data
        seasons = data.get("seasons", [])
        season_numbers = [str(s["number"]) for s in seasons]
        self.season_combo["values"] = season_numbers
        if season_numbers:
            self.season_var.set(season_numbers[-1])  # Seleziona ultima stagione
            self._load_season_episodes()
        self.ep_title_label.config(text=data["name"])

    def _load_season_episodes(self):
        if not self.current_title_data:
            return
        season_num = self.season_var.get()
        if not season_num:
            return
        season_num = int(season_num)
        title_id = self.current_title_data["id"]
        slug = self.current_title_data["slug"]

        self.episodes_listbox.delete(0, "end")
        self.episodes_listbox.insert("end", "Caricamento episodi...")
        threading.Thread(target=self._load_season_thread, args=(title_id, slug, season_num), daemon=True).start()

    def _load_season_thread(self, title_id, slug, season_num):
        try:
            episodes = self.api.get_season(title_id, slug, season_num)
            self.after(0, self._show_episodes, episodes, season_num)
        except Exception as e:
            self.after(0, lambda: self.episodes_listbox.insert(0, f"Errore: {e}"))

    def _show_episodes(self, episodes, season_num):
        self.episodes_listbox.delete(0, "end")
        self.current_episodes = episodes
        for ep in episodes:
            name = ep.get("name", "Senza nome")
            num = ep.get("number", "?")
            dur = ep.get("duration", 0)
            parts = []
            if ep.get("dub_ita"):
                parts.append("Dub IT")
            if ep.get("sub_ita"):
                parts.append("Sub IT")
            info = f"  [{', '.join(parts)}]" if parts else ""
            self.episodes_listbox.insert(
                "end",
                f"S{season_num:02d}E{num:02d} - {name} ({dur} min){info}"
            )

    def _select_all_episodes(self):
        self.episodes_listbox.select_set(0, "end")

    def _deselect_all_episodes(self):
        self.episodes_listbox.selection_clear(0, "end")

    # ── Coda Download ────────────────────────────────────────────────────────

    def _add_to_queue(self):
        if not self.current_title_data or not hasattr(self, "current_episodes"):
            return
        sel = self.episodes_listbox.curselection()
        if not sel:
            messagebox.showwarning("Attenzione", "Seleziona almeno un episodio")
            return
        season_num = int(self.season_var.get())
        title_id = self.current_title_data["id"]
        for idx in sel:
            if idx < len(self.current_episodes):
                ep = self.current_episodes[idx]
                self.download_manager.add({
                    "title_name": self.current_title_data["name"],
                    "title_id": title_id,
                    "season": season_num,
                    "episode": ep.get("number", idx + 1),
                    "episode_id": ep.get("id", 0),
                    "episode_name": ep.get("name", ""),
                    "duration": ep.get("duration", 0),
                    "status": "in_coda",
                    "progress": 0,
                })
        self._refresh_queue()

    def _remove_from_queue(self):
        sel = self.queue_tree.selection()
        if not sel:
            return
        for item_id in sel:
            idx = self.queue_tree.index(item_id)
            self.download_manager.remove(idx)
        self._refresh_queue()

    def _clear_queue(self):
        self.download_manager.clear()
        self._refresh_queue()

    STATUS_LABELS = {
        "in_coda": "In coda",
        "in_corso": "In corso...",
        "completato": "Completato",
        "errore": "Errore",
    }

    @staticmethod
    def _mini_progress_bar(item, width=10):
        status = item["status"]
        if status == "completato":
            pct = 100
        elif status == "in_corso":
            pct = item.get("progress", 0)
        else:
            return ""
        filled = int(round(pct / 100 * width))
        bar = "█" * filled + "░" * (width - filled)

        # Video e audio sono stream separati scaricati in sequenza: mostrarli
        # distintamente evita che la percentuale sembri "bloccata" mentre il
        # video e' gia' finito e l'audio sta ancora scaricando.
        if status == "in_corso":
            video_pct = item.get("video_progress", 0)
            if item.get("audio_started"):
                text = f"{bar} V:{video_pct:.0f}% A:{item.get('audio_progress', 0):.0f}%"
            else:
                text = f"{bar} V:{video_pct:.0f}%"
        else:
            text = f"{bar} {pct:.0f}%"

        size_mb = item.get("size_mb", 0)
        speed = item.get("speed_mb_s", 0)
        if size_mb and status == "in_corso" and speed:
            text += f" ({size_mb:.1f} MB, {speed:.1f} MB/s)"
        elif size_mb:
            text += f" ({size_mb:.1f} MB)"
        return text

    def _refresh_queue(self):
        """Ricostruisce l'intera lista (usata quando cambia il numero di elementi)."""
        self.queue_tree.delete(*self.queue_tree.get_children())
        self.queue_row_ids = []
        for item in self.download_manager.queue:
            title = f"{item['title_name']} S{item['season']:02d}E{item['episode']:02d} - {item.get('episode_name', '')}"
            status = self.STATUS_LABELS.get(item["status"], item["status"])
            bar = self._mini_progress_bar(item)
            row_id = self.queue_tree.insert("", "end", values=(title, status, bar))
            self.queue_row_ids.append(row_id)

    def _update_queue_progress(self):
        """Aggiorna stato/barra delle righe esistenti senza ricrearle (niente flicker)."""
        if len(self.queue_row_ids) != len(self.download_manager.queue):
            self._refresh_queue()
            return
        for row_id, item in zip(self.queue_row_ids, self.download_manager.queue):
            status = self.STATUS_LABELS.get(item["status"], item["status"])
            bar = self._mini_progress_bar(item)
            self.queue_tree.set(row_id, "stato", status)
            self.queue_tree.set(row_id, "progresso", bar)

    # ── Download ─────────────────────────────────────────────────────────────

    def _start_download(self):
        if not self.download_manager.queue:
            messagebox.showwarning("Attenzione", "La coda è vuota. Aggiungi episodi prima.")
            return
        has_pending = any(i["status"] in ("in_coda", "errore") for i in self.download_manager.queue)
        if not has_pending:
            messagebox.showinfo("Info", "Tutti gli episodi sono già stati scaricati.")
            return
        self.download_manager.output_folder = self.output_folder
        self.btn_download.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.download_manager.start_all()

    def _stop_download(self):
        self.download_manager.kill_current()
        self.btn_download.config(state="normal")
        self.btn_stop.config(state="disabled")

    def _on_download_finished(self):
        self.after(0, lambda: self.btn_download.config(state="normal"))
        self.after(0, lambda: self.btn_stop.config(state="disabled"))

    # ── Cartella ─────────────────────────────────────────────────────────────

    def _browse_folder(self):
        start_dir = self.output_folder if os.path.isdir(self.output_folder) else os.path.expanduser("~")
        folder = FolderBrowserDialog(self, start_dir).show()
        if folder:
            self.output_folder = folder
            self.folder_var.set(folder)
            self._save_output_folder()

    # ── Callbacks ────────────────────────────────────────────────────────────

    def _progress_callback(self, pct):
        self.after(0, lambda: self.progress_var.set(pct))
        self.after(0, lambda: self.overall_pct_label.config(text=f"{pct:.0f}%"))
        self.after(0, self._update_queue_progress)

    def _status_callback(self, msg):
        self.after(0, lambda: self.status_label.config(text=msg))

    # ── Init Download Manager ────────────────────────────────────────────────

    def _init_download_manager(self):
        self.download_manager = DownloadManager(
            output_folder=self.output_folder,
            progress_callback=self._progress_callback,
            status_callback=self._status_callback,
            finished_callback=self._on_download_finished,
        )
        self.api = self.download_manager.api


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    app = ScDownloaderApp()
    app._init_download_manager()
    app.mainloop()


if __name__ == "__main__":
    main()
