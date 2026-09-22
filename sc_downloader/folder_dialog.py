import os
import tkinter as tk
from tkinter import ttk

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
