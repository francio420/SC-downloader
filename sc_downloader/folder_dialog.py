import os
import tkinter as tk
from tkinter import ttk

from . import theme as T
from .widgets import Button, draw_icon

# ─── FolderBrowserDialog ─────────────────────────────────────────────────────


class FolderBrowserDialog:
    """Selettore di cartelle con lo stesso tema scuro del resto dell'app,
    al posto del dialogo nativo del sistema operativo."""

    def __init__(self, parent, start_dir):
        self.result = None
        self.current_dir = start_dir

        self.top = tk.Toplevel(parent)
        self.top.title("Scegli cartella di destinazione")
        self.top.configure(bg=T.BG)
        self.top.geometry("620x480")
        self.top.minsize(460, 320)
        self.top.transient(parent)

        head = tk.Frame(self.top, bg=T.BG)
        head.pack(fill="x", padx=16, pady=(16, 10))
        Button(head, icon="back", command=self._go_up, height=36).pack(side="left", padx=(0, 8))
        self.path_var = tk.StringVar()
        path_entry = ttk.Entry(head, textvariable=self.path_var, font=T.font(10))
        path_entry.pack(side="left", fill="x", expand=True)
        path_entry.bind("<Return>", self._go_to_typed_path)

        list_frame = tk.Frame(self.top, bg=T.SURFACE, highlightthickness=1, highlightbackground=T.BORDER)
        list_frame.pack(fill="both", expand=True, padx=16)
        list_scroll = ttk.Scrollbar(list_frame)
        list_scroll.pack(side="right", fill="y")
        self.listbox = tk.Listbox(
            list_frame, bg=T.SURFACE, fg=T.TEXT,
            selectbackground=T.blend(T.ACCENT, T.SURFACE, 0.7), selectforeground=T.TEXT,
            font=T.font(10), activestyle="none", borderwidth=0, highlightthickness=0,
            yscrollcommand=list_scroll.set,
        )
        self.listbox.pack(side="left", fill="both", expand=True, padx=6, pady=6)
        list_scroll.config(command=self.listbox.yview)
        self.listbox.bind("<Double-Button-1>", self._on_double_click)
        self.listbox.bind("<Return>", self._on_double_click)

        foot = tk.Frame(self.top, bg=T.BG)
        foot.pack(fill="x", padx=16, pady=16)
        icon = tk.Canvas(foot, width=22, height=22, bg=T.BG, highlightthickness=0)
        draw_icon(icon, "folder", 11, 11, 18, T.MUTED)
        icon.pack(side="left")
        tk.Label(foot, text="Doppio clic per entrare in una cartella", bg=T.BG, fg=T.SUBTLE,
                 font=T.font(9)).pack(side="left", padx=6)
        Button(foot, "Usa questa cartella", icon="check", variant="primary", command=self._confirm,
               height=38).pack(side="right")
        Button(foot, "Annulla", variant="flat", command=self._cancel, height=38).pack(side="right", padx=8)

        self.top.protocol("WM_DELETE_WINDOW", self._cancel)
        self.top.bind("<Escape>", lambda e: self._cancel())
        self._refresh(start_dir)
        self.top.wait_visibility()
        self.top.grab_set()

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
            self.listbox.insert("end", f"  {name}")

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
        name = self.listbox.get(sel[0])[2:]
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
