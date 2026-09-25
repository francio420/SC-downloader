import math
import tkinter as tk
from tkinter import ttk

from . import theme as T

# Widget disegnati a mano su Canvas: Tk/ttk non offre angoli arrotondati,
# gradienti o anelli di progresso, quindi li costruiamo qui una volta sola.

# ─── Primitive di disegno ────────────────────────────────────────────────────


def rounded_rect(canvas, x1, y1, x2, y2, r, **kw):
    r = max(0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
           x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return canvas.create_polygon(pts, smooth=True, **kw)


def draw_icon(canvas, name, cx, cy, s, color, width=2, tags=()):
    """Icone vettoriali (niente emoji: il loro rendering in Tk varia molto
    tra sistemi e le emoji a colori possono far crashare Tk su X11)."""
    kw = dict(fill=color, width=width, tags=tags, capstyle="round", joinstyle="round")
    if name == "search":
        r = s * 0.3
        canvas.create_oval(cx - s * 0.1 - r, cy - s * 0.1 - r, cx - s * 0.1 + r, cy - s * 0.1 + r,
                           outline=color, width=width, tags=tags)
        canvas.create_line(cx + s * 0.13, cy + s * 0.13, cx + s * 0.4, cy + s * 0.4, **kw)
    elif name == "download":
        canvas.create_line(cx, cy - s * 0.42, cx, cy + s * 0.1, **kw)
        canvas.create_line(cx - s * 0.22, cy - s * 0.12, cx, cy + s * 0.1, cx + s * 0.22, cy - s * 0.12, **kw)
        canvas.create_line(cx - s * 0.4, cy + s * 0.18, cx - s * 0.4, cy + s * 0.4,
                           cx + s * 0.4, cy + s * 0.4, cx + s * 0.4, cy + s * 0.18, **kw)
    elif name == "sliders":
        for dy, knob in ((-0.28, 0.18), (0, -0.2), (0.28, 0.06)):
            y = cy + s * dy
            canvas.create_line(cx - s * 0.42, y, cx + s * 0.42, y, **kw)
            k = s * 0.1
            canvas.create_oval(cx + s * knob - k, y - k, cx + s * knob + k, y + k,
                               fill=canvas.cget("bg"), outline=color, width=width, tags=tags)
    elif name == "back":
        canvas.create_line(cx + s * 0.12, cy - s * 0.3, cx - s * 0.18, cy, cx + s * 0.12, cy + s * 0.3, **kw)
    elif name == "close":
        d = s * 0.28
        canvas.create_line(cx - d, cy - d, cx + d, cy + d, **kw)
        canvas.create_line(cx - d, cy + d, cx + d, cy - d, **kw)
    elif name == "check":
        canvas.create_line(cx - s * 0.3, cy, cx - s * 0.08, cy + s * 0.22, cx + s * 0.32, cy - s * 0.22, **kw)
    elif name == "plus":
        canvas.create_line(cx - s * 0.3, cy, cx + s * 0.3, cy, **kw)
        canvas.create_line(cx, cy - s * 0.3, cx, cy + s * 0.3, **kw)
    elif name == "minus":
        canvas.create_line(cx - s * 0.3, cy, cx + s * 0.3, cy, **kw)
    elif name == "play":
        canvas.create_polygon(cx - s * 0.22, cy - s * 0.3, cx + s * 0.3, cy, cx - s * 0.22, cy + s * 0.3,
                              fill=color, outline=color, width=width, joinstyle="round", tags=tags)
    elif name == "stop":
        d = s * 0.24
        canvas.create_rectangle(cx - d, cy - d, cx + d, cy + d, fill=color, outline=color, width=width, tags=tags)
    elif name == "folder":
        canvas.create_line(cx - s * 0.4, cy + s * 0.32, cx - s * 0.4, cy - s * 0.3, cx - s * 0.1, cy - s * 0.3,
                           cx, cy - s * 0.18, cx + s * 0.4, cy - s * 0.18, cx + s * 0.4, cy + s * 0.32,
                           cx - s * 0.4, cy + s * 0.32, **kw)
    elif name == "trash":
        canvas.create_line(cx - s * 0.36, cy - s * 0.24, cx + s * 0.36, cy - s * 0.24, **kw)
        canvas.create_line(cx - s * 0.26, cy - s * 0.24, cx - s * 0.2, cy + s * 0.38,
                           cx + s * 0.2, cy + s * 0.38, cx + s * 0.26, cy - s * 0.24, **kw)
        canvas.create_line(cx - s * 0.1, cy - s * 0.24, cx - s * 0.08, cy - s * 0.38,
                           cx + s * 0.08, cy - s * 0.38, cx + s * 0.1, cy - s * 0.24, **kw)
    elif name == "star":
        pts = []
        for i in range(10):
            r = s * (0.42 if i % 2 == 0 else 0.18)
            a = -math.pi / 2 + i * math.pi / 5
            pts += [cx + r * math.cos(a), cy + r * math.sin(a)]
        canvas.create_polygon(pts, fill=color, outline="", tags=tags)


def parent_bg(widget):
    try:
        return widget.cget("bg")
    except tk.TclError:
        return T.BG


# ─── Button ──────────────────────────────────────────────────────────────────


class Button(tk.Canvas):
    """Pulsante a pillola con icona opzionale e stato hover/disabilitato."""

    VARIANTS = {
        "primary": (T.ACCENT, T.blend(T.ACCENT, "#ffffff", 0.18), T.ON_ACCENT),
        "danger": (T.DANGER, T.blend(T.DANGER, "#ffffff", 0.18), T.ON_ACCENT),
        "ghost": (T.SURFACE_3, T.blend(T.SURFACE_3, "#ffffff", 0.07), T.TEXT),
        "flat": (None, T.SURFACE_3, T.MUTED),
    }

    def __init__(self, parent, text="", command=None, variant="ghost", icon=None, height=36, font_size=10,
                 padx=16, bg=None):
        self._bg = bg or parent_bg(parent)
        super().__init__(parent, height=height, bg=self._bg, highlightthickness=0, bd=0, cursor="hand2")
        self.command = command
        self.variant = variant
        self.icon = icon
        self.text = text
        self.padx = padx
        self.font = T.font(font_size, "bold")
        self.enabled = True
        self.hover = False
        self._resize()
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self.bind("<ButtonRelease-1>", self._on_click)

    def _resize(self):
        h = int(self["height"])
        width = self.padx * 2 + (T.measure(self.text, self.font) if self.text else 0)
        if self.icon:
            width += int(h * 0.45) + (8 if self.text else 0)
            if not self.text:
                width = h
        self.configure(width=width)
        self._draw()

    def _draw(self):
        self.delete("all")
        w, h = int(self["width"]), int(self["height"])
        base, hover, fg = self.VARIANTS[self.variant]
        fill = hover if self.hover and self.enabled else base
        if not self.enabled:
            fill = T.blend(fill or self._bg, self._bg, 0.55)
            fg = T.blend(fg, self._bg, 0.5)
        if fill:
            rounded_rect(self, 0, 0, w, h, h / 2, fill=fill, outline="")
        x = self.padx if self.text else w / 2
        if self.icon:
            s = h * 0.45
            if self.text:
                draw_icon(self, self.icon, x + s / 2, h / 2, s, fg)
                x += s + 8
            else:
                draw_icon(self, self.icon, w / 2, h / 2, s, fg)
        if self.text:
            self.create_text(x, h / 2, text=self.text, anchor="w", fill=fg, font=self.font)

    def _set_hover(self, value):
        self.hover = value
        self._draw()

    def _on_click(self, event):
        if self.enabled and self.command and 0 <= event.x <= self.winfo_width() and 0 <= event.y <= self.winfo_height():
            self.command()

    def set_enabled(self, enabled):
        self.enabled = enabled
        self.configure(cursor="hand2" if enabled else "arrow")
        self._draw()

    def set_text(self, text):
        self.text = text
        self._resize()

    def set_variant(self, variant, icon=None):
        self.variant = variant
        if icon:
            self.icon = icon
        self._resize()


# ─── Chip ────────────────────────────────────────────────────────────────────


class Chip(tk.Canvas):
    """Pillola selezionabile (stagioni, filtri)."""

    def __init__(self, parent, text, command=None, selected=False, height=30):
        self._bg = parent_bg(parent)
        self.font = T.font(9, "bold")
        super().__init__(parent, height=height, width=T.measure(text, self.font) + 28, bg=self._bg,
                         highlightthickness=0, bd=0, cursor="hand2")
        self.text = text
        self.command = command
        self.selected = selected
        self.hover = False
        self._draw()
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self.bind("<Button-1>", lambda e: self.command and self.command())

    def _draw(self):
        self.delete("all")
        w, h = int(self["width"]), int(self["height"])
        if self.selected:
            fill, fg, outline = T.ACCENT, T.ON_ACCENT, T.ACCENT
        else:
            fill = T.SURFACE_3 if self.hover else T.SURFACE_2
            fg, outline = T.TEXT if self.hover else T.MUTED, T.BORDER
        rounded_rect(self, 1, 1, w - 1, h - 1, h / 2, fill=fill, outline=outline)
        self.create_text(w / 2, h / 2, text=self.text, fill=fg, font=self.font)

    def _set_hover(self, value):
        self.hover = value
        self._draw()

    def set_selected(self, selected):
        self.selected = selected
        self._draw()


# ─── ScrollFrame ─────────────────────────────────────────────────────────────


class ScrollFrame(tk.Frame):
    """Frame scrollabile verticalmente. La rotella viene gestita globalmente
    e instradata al ScrollFrame sotto il puntatore, cosi' funziona anche sopra
    i widget figli (e con piu' ScrollFrame nella stessa finestra)."""

    _wheel_installed = False

    def __init__(self, parent, bg=T.BG):
        super().__init__(parent, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.vbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self._win = self.canvas.create_window(0, 0, window=self.inner, anchor="nw")
        self._bar_visible = False
        self.inner.bind("<Configure>", lambda e: self._update_region())
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        if not ScrollFrame._wheel_installed:
            ScrollFrame._wheel_installed = True
            root = self.winfo_toplevel()
            for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
                root.bind_all(seq, ScrollFrame._on_wheel, add="+")

    def _on_canvas_configure(self, event):
        self.canvas.itemconfigure(self._win, width=event.width)
        self._update_region()

    def _update_region(self):
        self.canvas.configure(scrollregion=(0, 0, self.inner.winfo_reqwidth(), self.inner.winfo_reqheight()))
        overflow = self.inner.winfo_reqheight() > self.canvas.winfo_height() + 1
        if overflow != self._bar_visible:
            self._bar_visible = overflow
            if overflow:
                self.vbar.pack(side="right", fill="y", before=self.canvas)
            else:
                self.vbar.pack_forget()
                self.canvas.yview_moveto(0)

    def scroll_to_top(self):
        self.canvas.yview_moveto(0)

    @staticmethod
    def _on_wheel(event):
        try:
            widget = event.widget.winfo_containing(event.x_root, event.y_root)
        except (KeyError, tk.TclError, AttributeError):
            return
        while widget is not None and not isinstance(widget, ScrollFrame):
            widget = widget.master
        if widget is None or not widget._bar_visible:
            return
        if event.num == 4:
            step = -3
        elif event.num == 5:
            step = 3
        else:
            step = -3 if event.delta > 0 else 3
        widget.canvas.yview_scroll(step, "units")


# ─── Indicatori di progresso ─────────────────────────────────────────────────


class ProgressRing(tk.Canvas):
    """Anello di progresso con gradiente viola→ciano e testo al centro."""

    def __init__(self, parent, size=120, thickness=10, font_size=20, show_label=True):
        super().__init__(parent, width=size, height=size, bg=parent_bg(parent), highlightthickness=0, bd=0)
        self.size = size
        self.thickness = thickness
        self.font_size = font_size
        self.show_label = show_label
        self.value = -1
        self.caption = ""
        self.set(0)

    def set(self, pct, caption=""):
        pct = max(0.0, min(100.0, pct))
        if round(pct, 1) == round(self.value, 1) and caption == self.caption:
            return
        self.value, self.caption = pct, caption
        self.delete("all")
        pad = self.thickness / 2 + 2
        box = (pad, pad, self.size - pad, self.size - pad)
        self.create_oval(*box, outline=T.SURFACE_3, width=self.thickness)
        segments = max(1, int(pct / 100 * 72))
        extent = pct / 100 * 360 / segments
        for i in range(segments if pct > 0 else 0):
            color = T.blend(T.ACCENT, T.ACCENT_2, i / 72)
            self.create_arc(*box, start=90 - i * extent, extent=-(extent + 0.6), style="arc",
                            outline=color, width=self.thickness)
        if self.show_label:
            c = self.size / 2
            dy = self.font_size * 0.35 if caption else 0
            self.create_text(c, c - dy, text=f"{pct:.0f}%", fill=T.TEXT, font=T.font(self.font_size, "bold"))
            if caption:
                self.create_text(c, c + self.font_size * 0.75, text=caption, fill=T.MUTED,
                                 font=T.font(max(7, self.font_size // 3)))


class SlimBar(tk.Canvas):
    """Barra di progresso sottile e arrotondata."""

    def __init__(self, parent, color=T.ACCENT, height=6, track=T.SURFACE_3):
        super().__init__(parent, height=height, bg=parent_bg(parent), highlightthickness=0, bd=0)
        self.color = color
        self.track = track
        self.value = 0
        self.bind("<Configure>", lambda e: self._draw())

    def set(self, pct, color=None):
        if color:
            self.color = color
        self.value = max(0.0, min(100.0, pct))
        self._draw()

    def _draw(self):
        self.delete("all")
        w, h = self.winfo_width(), int(self["height"])
        if w <= 1:
            return
        rounded_rect(self, 0, 0, w, h, h / 2, fill=self.track, outline="")
        fw = w * self.value / 100
        if fw >= 1:
            rounded_rect(self, 0, 0, max(fw, h), h, h / 2, fill=self.color, outline="")


class Sparkline(tk.Canvas):
    """Grafico ad area della velocita' di download negli ultimi N campioni."""

    def __init__(self, parent, samples=90, height=70, color=T.ACCENT_2):
        super().__init__(parent, height=height, bg=parent_bg(parent), highlightthickness=0, bd=0)
        self.samples = [0.0] * samples
        self.color = color
        self.bind("<Configure>", lambda e: self._draw())

    def push(self, value):
        self.samples = self.samples[1:] + [max(0.0, value)]
        self._draw()

    def _draw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w <= 1:
            return
        bg = self.cget("bg")
        peak = max(max(self.samples), 1.0)
        top = 16
        for frac in (0.0, 0.5, 1.0):
            y = top + (h - top - 2) * frac
            self.create_line(0, y, w, y, fill=T.blend(T.BORDER, bg, 0.4), dash=(2, 4))
        step = w / (len(self.samples) - 1)
        pts = [(i * step, h - 2 - (v / peak) * (h - top - 2)) for i, v in enumerate(self.samples)]
        area = [0, h] + [c for p in pts for c in p] + [w, h]
        self.create_polygon(area, fill=T.blend(self.color, bg, 0.82), outline="")
        self.create_line([c for p in pts for c in p], fill=self.color, width=2, joinstyle="round")
        self.create_text(w - 2, 2, anchor="ne", text=f"picco {peak:.1f} MB/s" if max(self.samples) else "",
                         fill=T.SUBTLE, font=T.font(8))


class Spinner(tk.Canvas):
    """Arco rotante per le attese di rete."""

    def __init__(self, parent, size=18, color=T.ACCENT):
        super().__init__(parent, width=size, height=size, bg=parent_bg(parent), highlightthickness=0, bd=0)
        self.size, self.color = size, color
        self._angle = 0
        self._job = None

    def start(self):
        if self._job is None:
            self._tick()

    def stop(self):
        if self._job is not None:
            self.after_cancel(self._job)
            self._job = None
        self.delete("all")

    def _tick(self):
        self.delete("all")
        p = 2
        self.create_arc(p, p, self.size - p, self.size - p, start=self._angle, extent=270, style="arc",
                        outline=self.color, width=2)
        self._angle = (self._angle - 18) % 360
        self._job = self.after(30, self._tick)


# ─── Stepper ─────────────────────────────────────────────────────────────────


class Stepper(tk.Frame):
    """Selettore numerico  [−]  N  [+]."""

    def __init__(self, parent, value, minimum, maximum, command=None):
        super().__init__(parent, bg=parent_bg(parent))
        self.value, self.minimum, self.maximum, self.command = value, minimum, maximum, command
        self.btn_minus = Button(self, icon="minus", command=lambda: self._change(-1), height=34)
        self.btn_minus.pack(side="left")
        self.label = tk.Label(self, text=str(value), width=3, bg=self["bg"], fg=T.TEXT, font=T.font(14, "bold"))
        self.label.pack(side="left", padx=6)
        self.btn_plus = Button(self, icon="plus", command=lambda: self._change(1), height=34)
        self.btn_plus.pack(side="left")
        self._sync()

    def _change(self, delta):
        new = max(self.minimum, min(self.maximum, self.value + delta))
        if new != self.value:
            self.value = new
            self._sync()
            if self.command:
                self.command(new)

    def _sync(self):
        self.label.config(text=str(self.value))
        self.btn_minus.set_enabled(self.value > self.minimum)
        self.btn_plus.set_enabled(self.value < self.maximum)


# ─── SearchBar ───────────────────────────────────────────────────────────────


class SearchBar(tk.Canvas):
    """Campo di ricerca arrotondato con icona, placeholder e spinner."""

    def __init__(self, parent, placeholder, command, height=52):
        self._bg = parent_bg(parent)
        super().__init__(parent, height=height, bg=self._bg, highlightthickness=0, bd=0)
        self.command = command
        self.focused = False
        self.var = tk.StringVar()
        self.entry = tk.Entry(self, textvariable=self.var, bg=T.SURFACE_2, fg=T.TEXT, insertbackground=T.TEXT,
                              relief="flat", bd=0, highlightthickness=0, font=T.font(13),
                              selectbackground=T.ACCENT, selectforeground=T.ON_ACCENT)
        self.placeholder = tk.Label(self, text=placeholder, bg=T.SURFACE_2, fg=T.SUBTLE, font=T.font(13),
                                    cursor="xterm")
        self.spinner = Spinner(self, size=20)
        self.spinner.configure(bg=T.SURFACE_2)
        self._entry_win = self.create_window(0, 0, window=self.entry, anchor="w")
        self._ph_win = self.create_window(0, 0, window=self.placeholder, anchor="w")
        self._spin_win = self.create_window(0, 0, window=self.spinner, anchor="e")
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Button-1>", lambda e: self.entry.focus_set())
        self.placeholder.bind("<Button-1>", lambda e: self.entry.focus_set())
        self.entry.bind("<FocusIn>", lambda e: self._set_focus(True))
        self.entry.bind("<FocusOut>", lambda e: self._set_focus(False))
        self.entry.bind("<Return>", lambda e: self.command(self.get()))
        self.entry.bind("<Escape>", lambda e: self.var.set(""))
        self.var.trace_add("write", lambda *a: self._sync_placeholder())

    def get(self):
        return self.var.get().strip()

    def focus(self):
        self.entry.focus_set()
        self.entry.select_range(0, "end")

    def set_loading(self, loading):
        if loading:
            self.spinner.start()
        else:
            self.spinner.stop()

    def _set_focus(self, value):
        self.focused = value
        self._draw()

    def _sync_placeholder(self):
        self.itemconfigure(self._ph_win, state="hidden" if self.var.get() else "normal")

    def _draw(self):
        self.delete("bg")
        w, h = self.winfo_width(), int(self["height"])
        outline = T.ACCENT if self.focused else T.BORDER
        rounded_rect(self, 1, 1, w - 1, h - 1, 16, fill=T.SURFACE_2, outline=outline, width=2 if self.focused else 1,
                     tags="bg")
        draw_icon(self, "search", 28, h / 2, 20, T.ACCENT if self.focused else T.MUTED, tags="bg")
        self.tag_lower("bg")
        self.coords(self._entry_win, 52, h / 2)
        self.itemconfigure(self._entry_win, width=max(10, w - 52 - 48))
        self.coords(self._ph_win, 52, h / 2)
        self.coords(self._spin_win, w - 16, h / 2)
        self._sync_placeholder()


# ─── Toast ───────────────────────────────────────────────────────────────────


class ToastHost:
    """Notifiche non bloccanti in basso a destra, al posto dei messagebox."""

    COLORS = {"info": T.ACCENT, "success": T.SUCCESS, "warning": T.WARNING, "error": T.DANGER}

    def __init__(self, root):
        self.root = root
        self.toasts = []

    def show(self, text, kind="info", duration=3500):
        color = self.COLORS.get(kind, T.ACCENT)
        frame = tk.Frame(self.root, bg=T.SURFACE_3, highlightthickness=1, highlightbackground=T.BORDER)
        tk.Frame(frame, bg=color, width=4).pack(side="left", fill="y")
        tk.Label(frame, text=text, bg=T.SURFACE_3, fg=T.TEXT, font=T.font(10), justify="left",
                 wraplength=360, padx=14, pady=10).pack(side="left")
        frame.bind("<Button-1>", lambda e: self._dismiss(frame))
        for child in frame.winfo_children():
            child.bind("<Button-1>", lambda e: self._dismiss(frame))
        self.toasts.append(frame)
        self._layout(animate_new=frame)
        self.root.after(duration, lambda: self._dismiss(frame))

    def _layout(self, animate_new=None):
        y = -20
        for frame in reversed(self.toasts):
            frame.update_idletasks()
            if frame is animate_new:
                self._slide(frame, y + 30, y)
            else:
                frame.place(relx=1.0, rely=1.0, x=-20, y=y, anchor="se")
            y -= frame.winfo_reqheight() + 10

    def _slide(self, frame, y_from, y_to, step=0):
        if not frame.winfo_exists():
            return
        t = min(1.0, step / 8)
        ease = 1 - (1 - t) ** 3
        frame.place(relx=1.0, rely=1.0, x=-20, y=y_from + (y_to - y_from) * ease, anchor="se")
        if t < 1:
            self.root.after(16, self._slide, frame, y_from, y_to, step + 1)

    def _dismiss(self, frame):
        if frame in self.toasts:
            self.toasts.remove(frame)
            frame.destroy()
            self._layout()


# ─── Contenitori ─────────────────────────────────────────────────────────────


class Card(tk.Canvas):
    """Pannello con angoli arrotondati; il contenuto va in self.inner e
    l'altezza segue automaticamente quella del contenuto."""

    def __init__(self, parent, padding=20, radius=18, fill=T.SURFACE):
        super().__init__(parent, bg=parent_bg(parent), highlightthickness=0, bd=0, height=10)
        self.padding, self.radius, self.fill = padding, radius, fill
        self.inner = tk.Frame(self, bg=fill)
        self._win = self.create_window(padding, padding, window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda e: self._sync())
        self.bind("<Configure>", lambda e: self._sync())

    def _sync(self):
        w = self.winfo_width()
        h = self.inner.winfo_reqheight() + self.padding * 2
        if int(self["height"]) != h:
            self.configure(height=h)
        self.itemconfigure(self._win, width=max(1, w - self.padding * 2))
        self.delete("bg")
        rounded_rect(self, 1, 1, w - 1, h - 1, self.radius, fill=self.fill, outline=T.BORDER, tags="bg")
        self.tag_lower("bg")


class FlowFrame(tk.Frame):
    """Dispone i figli in righe che vanno a capo (es. molte stagioni)."""

    def __init__(self, parent, gap=8):
        super().__init__(parent, bg=parent_bg(parent), height=1)
        self.gap = gap
        self.bind("<Configure>", lambda e: self.relayout())

    def relayout(self):
        width = self.winfo_width()
        x = y = row_h = 0
        for child in self.winfo_children():
            cw, ch = child.winfo_reqwidth(), child.winfo_reqheight()
            if x and x + cw > width:
                x, y, row_h = 0, y + row_h + self.gap, 0
            child.place(x=x, y=y)
            x += cw + self.gap
            row_h = max(row_h, ch)
        height = max(1, y + row_h)
        if int(self["height"]) != height:
            self.configure(height=height)


class NavButton(tk.Canvas):
    """Voce della barra laterale: icona, etichetta, indicatore e badge."""

    def __init__(self, parent, icon, label, command):
        super().__init__(parent, width=84, height=66, bg=parent_bg(parent), highlightthickness=0, bd=0,
                         cursor="hand2")
        self.icon, self.label, self.command = icon, label, command
        self.active = False
        self.hover = False
        self.badge = 0
        self._draw()
        self.bind("<Enter>", lambda e: self._set("hover", True))
        self.bind("<Leave>", lambda e: self._set("hover", False))
        self.bind("<Button-1>", lambda e: self.command())

    def _set(self, attr, value):
        if getattr(self, attr) != value:
            setattr(self, attr, value)
            self._draw()

    def set_active(self, value):
        self._set("active", value)

    def set_badge(self, value):
        self._set("badge", value)

    def _draw(self):
        self.delete("all")
        bg = self.cget("bg")
        cx = 42
        color = T.ACCENT if self.active else (T.TEXT if self.hover else T.MUTED)
        if self.active or self.hover:
            fill = T.blend(T.ACCENT, bg, 0.78) if self.active else T.SURFACE_3
            rounded_rect(self, cx - 24, 8, cx + 24, 40, 16, fill=fill, outline="")
        if self.active:
            rounded_rect(self, 0, 14, 4, 34, 2, fill=T.ACCENT, outline="")
        draw_icon(self, self.icon, cx, 24, 20, color)
        self.create_text(cx, 54, text=self.label, fill=color, font=T.font(8, "bold"))
        if self.badge:
            text = str(self.badge) if self.badge < 100 else "99+"
            bw = max(18, T.measure(text, T.font(7, "bold")) + 10)
            rounded_rect(self, cx + 8, 3, cx + 8 + bw, 21, 9, fill=T.DANGER, outline=bg, width=2)
            self.create_text(cx + 8 + bw / 2, 12, text=text, fill=T.ON_ACCENT, font=T.font(7, "bold"))
