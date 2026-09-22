import tkinter as tk
from tkinter import ttk

# ─── SettingsDialog ──────────────────────────────────────────────────────────


class SettingsDialog:
    """Finestra impostazioni per i parametri di download, nello stesso tema
    scuro del resto dell'app."""

    def __init__(self, parent, max_parallel_episodes, concurrent_fragments):
        self.result = None

        self.top = tk.Toplevel(parent)
        self.top.title("Impostazioni")
        self.top.configure(bg="#1e1e2e")
        self.top.resizable(False, False)
        self.top.transient(parent)
        self.top.grab_set()

        body = ttk.Frame(self.top)
        body.pack(fill="both", expand=True, padx=15, pady=15)

        ttk.Label(body, text="Episodi in parallelo", font=("Segoe UI", 10, "bold")).grid(
            row=0, column=0, sticky="w", pady=(0, 2))
        ttk.Label(
            body, text="Quanti episodi scaricare contemporaneamente (ognuno con\n"
                        "video e audio gia' paralleli tra loro). Valori alti possono\n"
                        "non aumentare la velocita' reale e rischiano di far\n"
                        "limitare le connessioni dal sito.",
            foreground="#a6adc8", justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(0, 5))
        self.parallel_var = tk.IntVar(value=max_parallel_episodes)
        ttk.Spinbox(body, from_=1, to=5, textvariable=self.parallel_var, width=5).grid(
            row=2, column=0, sticky="w", pady=(0, 15))

        ttk.Label(body, text="Frammenti concorrenti per stream", font=("Segoe UI", 10, "bold")).grid(
            row=3, column=0, sticky="w", pady=(0, 2))
        ttk.Label(
            body, text="Connessioni parallele usate da yt-dlp per scaricare i\n"
                        "frammenti di ogni singolo stream video/audio.",
            foreground="#a6adc8", justify="left",
        ).grid(row=4, column=0, sticky="w", pady=(0, 5))
        self.fragments_var = tk.IntVar(value=concurrent_fragments)
        ttk.Spinbox(body, from_=1, to=16, textvariable=self.fragments_var, width=5).grid(
            row=5, column=0, sticky="w", pady=(0, 15))

        btn_frame = ttk.Frame(body)
        btn_frame.grid(row=6, column=0, sticky="e")
        ttk.Button(btn_frame, text="Annulla", command=self._cancel).pack(side="right")
        ttk.Button(btn_frame, text="Salva", style="Accent.TButton", command=self._save).pack(
            side="right", padx=(0, 5))

        self.top.protocol("WM_DELETE_WINDOW", self._cancel)

    def _save(self):
        self.result = {
            "max_parallel_episodes": max(1, self.parallel_var.get()),
            "concurrent_fragments": max(1, self.fragments_var.get()),
        }
        self.top.destroy()

    def _cancel(self):
        self.result = None
        self.top.destroy()

    def show(self):
        self.top.wait_window()
        return self.result
