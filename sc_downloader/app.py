import json
import os
import subprocess
import sys
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor
from tkinter import messagebox

from . import images
from . import theme as T
from .api import StreamingCommunityAPI
from .constants import ROOT_DIR, SETTINGS_FILE
from .download_manager import DownloadManager
from .folder_dialog import FolderBrowserDialog
from .images import ImageLoader
from .views import DetailView, DownloadsView, SearchView, SettingsView
from .widgets import NavButton, ProgressRing, ToastHost, rounded_rect

# ─── ScDownloaderApp ─────────────────────────────────────────────────────────


class ScDownloaderApp(tk.Tk):
    """Finestra principale: barra laterale di navigazione + pagine
    (Scopri → Dettaglio titolo, Download, Impostazioni)."""

    TICK_MS = 300
    ICON_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "icon.png")

    def __init__(self):
        # className determina il WM_CLASS della finestra ("Sc-downloader"),
        # che il .desktop usa (StartupWMClass) per associarle la sua icona.
        super().__init__(className="sc-downloader")
        self.title("SC Downloader")
        try:
            self._icon = tk.PhotoImage(file=self.ICON_FILE)
            self.iconphoto(True, self._icon)
        except tk.TclError:
            pass
        self.geometry("1240x820")
        self.minsize(960, 620)
        T.setup_styles(self)

        settings = self._load_settings()
        self.output_folder = settings["output_folder"]
        self.max_parallel_episodes = settings["max_parallel_episodes"]
        self.concurrent_fragments = settings["concurrent_fragments"]

        self._init_download_manager()
        self.images = ImageLoader(self)
        self.toasts = ToastHost(self)
        self._stopping = False
        self._ticks = 0
        self._last_queued = {}

        self._build_ui()
        self._bind_shortcuts()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.show("search")
        self.after(100, self.views["search"].focus_search)
        if not images.AVAILABLE:
            self.after(800, lambda: self.toast(
                "Pillow non è installato: le copertine non verranno mostrate.\n"
                "Installa le dipendenze con pip install -r requirements.txt", "warning", 7000))
        self._tick()

    # ── Impostazioni su disco ────────────────────────────────────────────────

    def _load_settings(self):
        defaults = {"output_folder": ROOT_DIR, "max_parallel_episodes": 1, "concurrent_fragments": 4}
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
        except (OSError, json.JSONDecodeError):
            saved = {}
        folder = saved.get("output_folder")
        if folder and os.path.isdir(folder):
            defaults["output_folder"] = folder
        for key in ("max_parallel_episodes", "concurrent_fragments"):
            if isinstance(saved.get(key), int) and saved[key] > 0:
                defaults[key] = saved[key]
        return defaults

    def _save_settings(self):
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "output_folder": self.output_folder,
                    "max_parallel_episodes": self.max_parallel_episodes,
                    "concurrent_fragments": self.concurrent_fragments,
                }, f)
        except OSError:
            pass

    def update_settings(self, **values):
        for key, value in values.items():
            setattr(self, key, value)
        self.download_manager.max_parallel_episodes = self.max_parallel_episodes
        self.download_manager.concurrent_fragments = self.concurrent_fragments
        self._save_settings()

    # ── Layout ───────────────────────────────────────────────────────────────

    def _build_ui(self):
        rail = tk.Frame(self, bg=T.SURFACE, width=84)
        rail.pack(side="left", fill="y")
        rail.pack_propagate(False)
        tk.Frame(self, bg=T.BORDER, width=1).pack(side="left", fill="y")

        logo = tk.Canvas(rail, width=84, height=84, bg=T.SURFACE, highlightthickness=0)
        rounded_rect(logo, 20, 20, 64, 64, 14, fill=T.ACCENT, outline="")
        logo.create_polygon(36, 31, 52, 42, 36, 53, fill=T.ON_ACCENT, outline=T.ON_ACCENT, joinstyle="round")
        logo.create_oval(55, 17, 67, 29, fill=T.ACCENT_2, outline=T.SURFACE, width=2)
        logo.pack(pady=(6, 12))

        self.nav = {
            "search": NavButton(rail, "search", "Scopri", lambda: self.show("search")),
            "downloads": NavButton(rail, "download", "Download", lambda: self.show("downloads")),
            "settings": NavButton(rail, "sliders", "Opzioni", lambda: self.show("settings")),
        }
        for button in self.nav.values():
            button.pack(pady=2)

        # Mini anello in fondo alla barra: avanzamento sempre visibile
        self.rail_status = tk.Frame(rail, bg=T.SURFACE, cursor="hand2")
        self.mini_ring = ProgressRing(self.rail_status, size=56, thickness=5, font_size=9)
        self.mini_ring.pack()
        self.mini_speed = tk.Label(self.rail_status, text="", bg=T.SURFACE, fg=T.ACCENT_2, font=T.font(8, "bold"))
        self.mini_speed.pack(pady=(4, 0))
        for widget in (self.rail_status, self.mini_ring, self.mini_speed):
            widget.bind("<Button-1>", lambda e: self.show("downloads"))
        self._rail_status_visible = False

        self.content = tk.Frame(self, bg=T.BG)
        self.content.pack(side="left", fill="both", expand=True)
        self.views = {
            "search": SearchView(self.content, self),
            "detail": DetailView(self.content, self),
            "downloads": DownloadsView(self.content, self),
            "settings": SettingsView(self.content, self),
        }
        self.current_view = None

    def show(self, name):
        if name == self.current_view:
            return
        if self.current_view:
            self.views[self.current_view].pack_forget()
        self.views[name].pack(fill="both", expand=True)
        self.current_view = name
        nav_key = "search" if name == "detail" else name
        for key, button in self.nav.items():
            button.set_active(key == nav_key)
        if name == "settings":
            self.views["settings"].refresh()

    def show_search(self):
        self.show("search")

    def show_detail(self, title):
        self.views["detail"].load(title)
        self.show("detail")

    def toast(self, text, kind="info", duration=3500):
        self.toasts.show(text, kind, duration)

    def run_async(self, fn, on_done, on_error=None):
        """Esegue fn nel pool di rete della UI e riporta il risultato sul
        thread Tk. Il pool ha thread fissi (non uno nuovo per richiesta):
        curl_cffi tiene un handle libcurl per thread, quindi riusare i thread
        riusa anche la connessione HTTPS invece di rifare ogni volta
        l'handshake TLS (~60-100 ms in piu' a richiesta, misurati)."""
        def work():
            try:
                result = fn()
            except Exception as e:
                if on_error:
                    self.after(0, on_error, e)
                return
            self.after(0, on_done, result)

        self._ui_pool.submit(work)

    # ── Scorciatoie ──────────────────────────────────────────────────────────

    def _bind_shortcuts(self):
        def focus_search(event=None):
            if self.current_view != "search":
                self.show("search")
            self.views["search"].focus_search()
            return "break"

        def typing(event):
            return isinstance(event.widget, tk.Entry)

        self.bind_all("<Control-f>", focus_search)
        self.bind_all("<Control-k>", focus_search)
        self.bind_all("<slash>", lambda e: None if typing(e) else focus_search())
        self.bind_all("<Control-o>", lambda e: self.open_folder())
        self.bind_all("<Control-Key-1>", lambda e: self.show("search"))
        self.bind_all("<Control-Key-2>", lambda e: self.show("downloads"))
        self.bind_all("<Control-Key-3>", lambda e: self.show("settings"))
        self.bind_all("<Escape>", lambda e: self.show("search") if self.current_view == "detail" else None)
        self.bind_all("<Control-a>", lambda e: self.views["detail"].select_all()
                      if self.current_view == "detail" and not typing(e) else None)
        self.bind_all("<Return>", lambda e: self.views["detail"].add_selected(False)
                      if self.current_view == "detail" and not typing(e) else None)

    # ── Coda e download ──────────────────────────────────────────────────────

    def _init_download_manager(self):
        self.download_manager = DownloadManager(
            output_folder=self.output_folder,
            status_callback=lambda msg: self.after(0, self._on_status, msg),
            finished_callback=lambda: self.after(0, self._on_download_finished),
            max_parallel_episodes=self.max_parallel_episodes,
            concurrent_fragments=self.concurrent_fragments,
        )
        # Sessione separata da quella dei download: la navigazione nella UI non
        # condivide cookie/connessioni con i download in corso.
        self.api = StreamingCommunityAPI()
        # 2 thread: un caricamento lento non blocca una nuova ricerca.
        self._ui_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ui-net")

    def queued_episodes(self):
        return {(i["title_id"], i["episode_id"]): i["status"] for i in self.download_manager.queue}

    def enqueue(self, items, start_now=False):
        existing = {k for k, status in self.queued_episodes().items() if status != "errore"}
        added = 0
        for item in items:
            if (item["title_id"], item["episode_id"]) in existing:
                continue
            self.download_manager.add(item)
            added += 1
        skipped = len(items) - added
        if added and all(i.get("kind") == "movie" for i in items):
            msg = "Film aggiunto alla coda"
        elif added:
            msg = f"{added} episod{'io aggiunto' if added == 1 else 'i aggiunti'} alla coda"
            if skipped:
                msg += f" ({skipped} già present{'e' if skipped == 1 else 'i'})"
            self.toast(msg, "success")
        elif skipped:
            self.toast("Già presente in coda", "info")
        self.views["downloads"].tick()
        self.views["detail"]._redraw_rows()
        if start_now:
            self.start_download()

    def start_download(self):
        dm = self.download_manager
        if dm.is_downloading:
            return
        if not any(i["status"] in ("in_coda", "errore") for i in dm.queue):
            self.toast("Niente da scaricare: la coda è vuota o già completata", "info")
            return
        dm.output_folder = self.output_folder
        self._stopping = False
        dm.start_all()
        self.toast("Download avviato", "info", 2000)

    def stop_download(self):
        self._stopping = True
        self.download_manager.kill_current()

    def toggle_download(self):
        if self.download_manager.is_downloading:
            self.stop_download()
        else:
            self.start_download()

    def current_speed(self):
        return sum(i.get("speed_mb_s") or 0 for i in self.download_manager.queue if i["status"] == "in_corso")

    def _on_status(self, msg):
        self.views["downloads"].set_status(msg)

    def _on_download_finished(self):
        queue = self.download_manager.queue
        errors = sum(1 for i in queue if i["status"] == "errore")
        if self._stopping:
            self.toast("Download interrotti: i file parziali sono stati eliminati", "warning")
        elif errors:
            self.toast(f"Download terminati con {errors} error{'e' if errors == 1 else 'i'}: "
                       f"dettagli in .sc_debug.log", "error", 6000)
        else:
            self.toast("Tutti i download sono stati completati", "success", 5000)
            self.bell()
        self._stopping = False
        self.views["downloads"].tick()

    def open_folder(self, path=None):
        """Apre la cartella nel file manager di sistema (di default quella di
        destinazione). Se non esiste piu', apre il primo genitore esistente."""
        path = path or self.output_folder
        while path and not os.path.isdir(path):
            parent = os.path.dirname(path)
            if parent == path:
                break
            path = parent
        try:
            if sys.platform == "win32":
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as e:
            self.toast(f"Impossibile aprire la cartella: {e}", "error")

    def choose_folder(self):
        start_dir = self.output_folder if os.path.isdir(self.output_folder) else os.path.expanduser("~")
        folder = FolderBrowserDialog(self, start_dir).show()
        if folder:
            self.output_folder = folder
            self._save_settings()
            self.views["downloads"].update_folder()
            self.views["settings"].refresh()

    # ── Aggiornamento periodico ──────────────────────────────────────────────
    # Invece di ridisegnare a ogni callback di progresso (arrivano fino a ~10
    # volte al secondo per ogni sottoprocesso), la UI legge lo stato della coda
    # a intervalli fissi: costo costante indipendente dal numero di download.

    def _tick(self):
        dm = self.download_manager
        self._ticks += 1
        if self._ticks % max(1, 1000 // self.TICK_MS) == 0:
            self.views["downloads"].spark.push(self.current_speed())
        if self.current_view == "downloads":
            self.views["downloads"].tick()
        pending = sum(1 for i in dm.queue if i["status"] in ("in_coda", "in_corso"))
        self.nav["downloads"].set_badge(pending)
        if dm.queue:
            self.mini_ring.set(dm._overall_progress())
            self.mini_speed.config(text=f"{self.current_speed():.1f} MB/s" if dm.is_downloading else "")
        if bool(dm.queue) != self._rail_status_visible:
            self._rail_status_visible = bool(dm.queue)
            if dm.queue:
                self.rail_status.pack(side="bottom", pady=(0, 16))
            else:
                self.rail_status.pack_forget()
        # Le etichette IN CODA / IN CORSO / SCARICATO del dettaglio cambiano
        # solo con lo stato della coda: si ridisegna solo in quel caso.
        queued = self.queued_episodes()
        if queued != self._last_queued:
            self._last_queued = queued
            self.views["detail"]._redraw_rows()
        self.after(self.TICK_MS, self._tick)

    def _on_close(self):
        if self.download_manager.is_downloading:
            if not messagebox.askyesno(
                "Download in corso",
                "Un download è in corso. Chiudendo il programma verrà interrotto. Continuare?",
            ):
                return
            self.download_manager.kill_current()
        self.destroy()


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    app = ScDownloaderApp()
    app.mainloop()
