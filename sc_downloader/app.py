import json
import os
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from .constants import ROOT_DIR, SETTINGS_FILE
from .download_manager import DownloadManager
from .folder_dialog import FolderBrowserDialog
from .settings_dialog import SettingsDialog

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
        settings = self._load_settings()
        self.output_folder = settings["output_folder"]
        self.max_parallel_episodes = settings["max_parallel_episodes"]
        self.concurrent_fragments = settings["concurrent_fragments"]

        self._setup_styles()
        self._build_menu()
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

    def _build_menu(self):
        menubar = tk.Menu(self)
        menubar.add_command(label="Impostazioni", command=self._open_settings)
        self.config(menu=menubar)

    def _open_settings(self):
        result = SettingsDialog(self, self.max_parallel_episodes, self.concurrent_fragments).show()
        if result:
            self.max_parallel_episodes = result["max_parallel_episodes"]
            self.concurrent_fragments = result["concurrent_fragments"]
            self._save_settings()
            if self.download_manager:
                self.download_manager.max_parallel_episodes = self.max_parallel_episodes
                self.download_manager.concurrent_fragments = self.concurrent_fragments

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
            msg = str(e)
            self.after(0, lambda: self.search_status.config(text=f"Errore: {msg}"))
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
            msg = str(e)
            self.after(0, lambda: self.search_status.config(text=f"Errore: {msg}"))

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
            msg = str(e)
            self.after(0, lambda: self.ep_title_label.config(text=f"Errore: {msg}"))

    def _show_title_data(self, data):
        if not data:
            self.ep_title_label.config(text="Errore nel caricamento")
            return
        self.current_title_data = data
        seasons = data.get("seasons", [])
        season_numbers = [str(s["number"]) for s in seasons]
        self.season_combo["values"] = season_numbers
        if season_numbers:
            self.season_var.set(season_numbers[0])  # Seleziona prima stagione
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
            msg = str(e)
            self.after(0, lambda: self.episodes_listbox.insert(0, f"Errore: {msg}"))

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

        # Video e audio sono stream separati scaricati in parallelo, ognuno
        # con la propria percentuale: mostrarli distintamente evita che il
        # progresso sembri "bloccato" quando uno dei due arriva prima al 100%.
        if status == "in_corso":
            text = f"{bar} V:{item.get('video_progress', 0):.0f}% A:{item.get('audio_progress', 0):.0f}%"
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
            self._save_settings()

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
            max_parallel_episodes=self.max_parallel_episodes,
            concurrent_fragments=self.concurrent_fragments,
        )
        self.api = self.download_manager.api


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    app = ScDownloaderApp()
    app._init_download_manager()
    app.mainloop()
