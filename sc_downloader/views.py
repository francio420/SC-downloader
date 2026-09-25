import html
import os
import tkinter as tk
from tkinter import messagebox

from . import __version__
from . import theme as T
from .widgets import (Button, Card, Chip, FlowFrame, ProgressRing, ScrollFrame, SearchBar, Sparkline, Spinner,
                      Stepper, draw_icon, rounded_rect)

# Le quattro pagine dell'app. Tutte leggono lo stato da `app` (ScDownloaderApp)
# e ci passano sopra le azioni; nessuna tocca direttamente i thread di download.

_PLACEHOLDER_COLORS = ["#3b2f7a", "#1f4f66", "#5a2a4f", "#2f5a3e", "#5a3f22", "#2a3a6a", "#4a2a2a"]


def placeholder_color(name):
    return _PLACEHOLDER_COLORS[sum(map(ord, name or "?")) % len(_PLACEHOLDER_COLORS)]


def initials(name):
    words = [w for w in (name or "?").split() if w[:1].isalnum()]
    return "".join(w[0] for w in words[:2]).upper() or "?"


def format_minutes(minutes):
    minutes = int(minutes or 0)
    if minutes < 60:
        return f"{minutes} min"
    return f"{minutes // 60} h {minutes % 60:02d} min"


def format_size(mb):
    return f"{mb / 1024:.2f} GB" if mb >= 1024 else f"{mb:.1f} MB"


def page_header(parent, title, subtitle):
    head = tk.Frame(parent, bg=T.BG)
    tk.Label(head, text=title, bg=T.BG, fg=T.TEXT, font=T.font(24, "bold")).pack(anchor="w")
    tk.Label(head, text=subtitle, bg=T.BG, fg=T.MUTED, font=T.font(10)).pack(anchor="w", pady=(2, 0))
    return head


def empty_state(parent, icon, title, text):
    frame = tk.Frame(parent, bg=T.BG)
    canvas = tk.Canvas(frame, width=120, height=120, bg=T.BG, highlightthickness=0)
    canvas.create_oval(10, 10, 110, 110, fill=T.SURFACE_2, outline=T.BORDER)
    draw_icon(canvas, icon, 60, 60, 44, T.ACCENT, width=3)
    canvas.pack(pady=(0, 18))
    tk.Label(frame, text=title, bg=T.BG, fg=T.TEXT, font=T.font(15, "bold")).pack()
    tk.Label(frame, text=text, bg=T.BG, fg=T.MUTED, font=T.font(10), justify="center").pack(pady=(6, 0))
    return frame


# ─── Scopri (ricerca) ────────────────────────────────────────────────────────


class PosterCard(tk.Canvas):
    W, IMG_H = 160, 240

    def __init__(self, parent, app, title, command):
        super().__init__(parent, width=self.W + 10, height=self.IMG_H + 72, bg=T.BG, highlightthickness=0,
                         bd=0, cursor="hand2")
        self.title = title
        self.photo = None
        self.hover = False
        self._draw()
        url = app.images.url_for(title.get("images"), "poster", "cover_mobile", "cover")
        app.images.load(url, (self.W, self.IMG_H), self._on_image, radius=12)
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self.bind("<Button-1>", lambda e: command(title))

    def _on_image(self, photo):
        if self.winfo_exists():
            self.photo = photo
            self._draw()

    def _set_hover(self, value):
        self.hover = value
        self._draw()

    def _draw(self):
        self.delete("all")
        t = self.title
        x0, y0 = 5, 5 if self.hover else 8
        x1, y1 = x0 + self.W, y0 + self.IMG_H
        if self.hover:
            rounded_rect(self, x0 - 3, y0 - 3, x1 + 3, y1 + 3, 15, fill=T.ACCENT, outline="")
        if self.photo:
            self.create_image(x0, y0, image=self.photo, anchor="nw")
        else:
            rounded_rect(self, x0, y0, x1, y1, 12, fill=placeholder_color(t["name"]), outline="")
            self.create_text((x0 + x1) / 2, (y0 + y1) / 2, text=initials(t["name"]), fill=T.TEXT,
                             font=T.font(30, "bold"))
        # Badge tipo e voto
        kind = "SERIE" if t["type"] == "tv" else "FILM"
        kf = T.font(7, "bold")
        kw = T.measure(kind, kf) + 14
        rounded_rect(self, x0 + 8, y0 + 8, x0 + 8 + kw, y0 + 26, 9, fill=T.blend(T.BG, "#000000", 0.2), outline="")
        self.create_text(x0 + 8 + kw / 2, y0 + 17, text=kind, fill=T.ACCENT_2 if kind == "SERIE" else T.WARNING,
                         font=kf)
        score = t.get("score")
        if score not in (None, "", "N/A"):
            sf = T.font(8, "bold")
            sw = T.measure(str(score), sf) + 30
            rounded_rect(self, x1 - 8 - sw, y0 + 8, x1 - 8, y0 + 26, 9, fill=T.blend(T.BG, "#000000", 0.2),
                         outline="")
            draw_icon(self, "star", x1 - sw + 3, y0 + 17, 12, T.WARNING)
            self.create_text(x1 - 12, y0 + 17, text=str(score), fill=T.TEXT, font=sf, anchor="e")
        # Titolo e sottotitolo
        tf = T.font(10, "bold")
        lines = T.wrap_lines(t["name"], tf, self.W - 4, 2)
        self.create_text(x0 + 2, y1 + 10, text="\n".join(lines), anchor="nw", fill=T.TEXT if not self.hover
                         else T.ACCENT, font=tf)
        year = (t.get("last_air_date") or "")[:4]
        if t["type"] == "tv" and t.get("seasons_count"):
            n = t["seasons_count"]
            extra = f"{n} stagion{'e' if n == 1 else 'i'}"
        else:
            extra = "Film" if t["type"] != "tv" else "Serie TV"
        sub = " · ".join(p for p in (year, extra) if p)
        self.create_text(x0 + 2, y1 + 14 + 18 * len(lines), text=sub, anchor="nw", fill=T.MUTED, font=T.font(9))


class SearchView(tk.Frame):
    GAP = 18

    def __init__(self, parent, app):
        super().__init__(parent, bg=T.BG)
        self.app = app
        self.results, self.cards = [], []
        self.total = self.page = 0
        self.query = ""
        self.filter = "all"
        self._req = 0
        self._cols = 0

        top = tk.Frame(self, bg=T.BG)
        top.pack(fill="x", padx=36, pady=(30, 0))
        page_header(top, "Scopri", "Cerca una serie TV, scegli gli episodi e lasciali scaricare in coda").pack(
            fill="x", pady=(0, 18))
        self.bar = SearchBar(top, "Cerca serie TV e film…", self.search)
        self.bar.pack(fill="x")

        filters = tk.Frame(top, bg=T.BG)
        filters.pack(fill="x", pady=(14, 8))
        self.chips = {}
        for key, label in (("all", "Tutti"), ("tv", "Serie TV"), ("movie", "Film")):
            chip = Chip(filters, label, command=lambda k=key: self.set_filter(k), selected=key == "all")
            chip.pack(side="left", padx=(0, 8))
            self.chips[key] = chip
        self.status = tk.Label(filters, text="", bg=T.BG, fg=T.MUTED, font=T.font(9))
        self.status.pack(side="right")

        self.scroll = ScrollFrame(self)
        self.scroll.pack(fill="both", expand=True, padx=(28, 0), pady=(4, 0))
        self.grid_frame = tk.Frame(self.scroll.inner, bg=T.BG)
        self.more_btn = Button(self.scroll.inner, "Carica altri risultati", command=self.load_more, variant="ghost",
                               icon="plus")
        self.empty = empty_state(self.scroll.inner, "search", "Cosa guardiamo stasera?",
                                 "Scrivi il nome di una serie e premi Invio.\n"
                                 "Scorciatoie: Ctrl+F per cercare, Esc per tornare indietro.")
        self.empty.pack(pady=70)
        self.scroll.canvas.bind("<Configure>", lambda e: self._relayout(), add="+")

    def focus_search(self):
        self.bar.focus()

    def set_filter(self, key):
        self.filter = key
        for k, chip in self.chips.items():
            chip.set_selected(k == key)
        self._relayout(force=True)

    def search(self, query):
        if not query:
            return
        self.query, self.page = query, 1
        self._req += 1
        req = self._req
        self.bar.set_loading(True)
        self.status.config(text="Ricerca in corso…")
        self.app.run_async(lambda: self.app.api.search(query, 1),
                           lambda res: self._on_results(req, res, replace=True),
                           lambda e: self._on_error(req, e))

    def load_more(self):
        if not self.query:
            return
        self.page += 1
        self._req += 1
        req, query, page = self._req, self.query, self.page
        self.more_btn.set_enabled(False)
        self.bar.set_loading(True)
        self.app.run_async(lambda: self.app.api.search(query, page),
                           lambda res: self._on_results(req, res, replace=False),
                           lambda e: self._on_error(req, e))

    def _on_error(self, req, error):
        if req != self._req:
            return
        self.bar.set_loading(False)
        self.more_btn.set_enabled(True)
        self.status.config(text="")
        self.app.toast(f"Ricerca non riuscita: {error}", "error")

    def _on_results(self, req, response, replace):
        if req != self._req:
            return
        results, total = response
        self.app.images.cdn_url = self.app.api.cdn_url
        self.bar.set_loading(False)
        self.more_btn.set_enabled(True)
        if replace:
            for card in self.cards:
                card.destroy()
            self.results, self.cards = [], []
            self.scroll.scroll_to_top()
        known = {r["id"] for r in self.results}
        new = [r for r in results if r["id"] not in known]
        self.results += new
        self.cards += [PosterCard(self.grid_frame, self.app, r, self.app.show_detail) for r in new]
        self.total = total
        self._has_more = bool(new) and len(self.results) < total
        self.status.config(text=f"{len(self.results)} di {total} risultati" if total else "Nessun risultato")
        self._relayout(force=True)

    def _relayout(self, force=False):
        width = self.scroll.canvas.winfo_width()
        cols = max(1, (width - 8) // (PosterCard.W + 10 + self.GAP))
        if cols == self._cols and not force:
            return
        self._cols = cols
        visible = [c for c in self.cards if self.filter == "all" or c.title["type"] == self.filter
                   or (self.filter == "movie" and c.title["type"] != "tv")]
        for card in self.cards:
            card.grid_forget()
        for i, card in enumerate(visible):
            card.grid(row=i // cols, column=i % cols, padx=(0, self.GAP), pady=(0, 10), sticky="n")
        if self.results:
            self.empty.pack_forget()
            self.grid_frame.pack(fill="x", anchor="w")
            if getattr(self, "_has_more", False):
                self.more_btn.pack(pady=(10, 30))
            else:
                self.more_btn.pack_forget()
        elif self.query:
            self.grid_frame.pack_forget()
            self.more_btn.pack_forget()


# ─── Dettaglio titolo ────────────────────────────────────────────────────────


class EpisodeRow(tk.Canvas):
    H = 100
    THUMB = (144, 81)

    def __init__(self, parent, view, index, episode):
        super().__init__(parent, height=self.H, bg=T.BG, highlightthickness=0, bd=0, cursor="hand2")
        self.view, self.index, self.ep = view, index, episode
        self.photo = None
        self.hover = False
        self.bind("<Configure>", lambda e: self.draw())
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self.bind("<Button-1>", lambda e: view.toggle(index, shift=bool(e.state & 0x1)))
        url = view.app.images.url_for(episode.get("images"), "cover")
        view.app.images.load(url, self.THUMB, self._on_image, radius=8, bg=T.SURFACE)

    def _on_image(self, photo):
        if self.winfo_exists():
            self.photo = photo
            self.draw()

    def _set_hover(self, value):
        self.hover = value
        self.draw()

    def draw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.H
        if w <= 1:
            return
        selected = self.index in self.view.selected
        fill = T.blend(T.ACCENT, T.SURFACE, 0.86) if selected else (T.SURFACE_2 if self.hover else T.SURFACE)
        rounded_rect(self, 1, 3, w - 1, h - 3, 14, fill=fill, outline=T.ACCENT if selected else T.BORDER)
        # Checkbox
        cy = h / 2
        if selected:
            self.create_oval(18, cy - 11, 40, cy + 11, fill=T.ACCENT, outline=T.ACCENT)
            draw_icon(self, "check", 29, cy, 16, T.ON_ACCENT, width=2)
        else:
            self.create_oval(18, cy - 11, 40, cy + 11, outline=T.SUBTLE if not self.hover else T.MUTED, width=2)
        # Miniatura
        tx, ty = 54, (h - self.THUMB[1]) / 2
        if self.photo:
            self.create_image(tx, ty, image=self.photo, anchor="nw")
        else:
            rounded_rect(self, tx, ty, tx + self.THUMB[0], ty + self.THUMB[1], 8, fill=T.SURFACE_3, outline="")
            draw_icon(self, "play", tx + self.THUMB[0] / 2, ty + self.THUMB[1] / 2, 22, T.SUBTLE)
        # Testo
        ep = self.ep
        x = tx + self.THUMB[0] + 18
        right_w = 150
        text_w = max(60, w - x - right_w)
        num = f"E{ep.get('number', 0):02d}"
        nf = T.font(11, "bold")
        self.create_text(x, 22, text=num, anchor="nw", fill=T.ACCENT, font=nf)
        name = html.unescape(ep.get("name") or "Senza titolo")
        nx = x + T.measure(num, nf) + 10
        self.create_text(nx, 22, text=T.ellipsize(name, nf, text_w - (nx - x)), anchor="nw", fill=T.TEXT, font=nf)
        plot = html.unescape(ep.get("plot") or "")
        pf = T.font(9)
        self.create_text(x, 46, text="\n".join(T.wrap_lines(plot, pf, text_w, 2)), anchor="nw", fill=T.MUTED,
                         font=pf)
        # Colonna destra: durata, lingue, stato in coda
        rx = w - 20
        self.create_text(rx, 24, text=format_minutes(ep.get("duration")), anchor="ne", fill=T.TEXT,
                         font=T.font(9, "bold"))
        badges = [b for b, on in (("ITA", ep.get("dub_ita")), ("SUB", ep.get("sub_ita"))) if on]
        queued = self.view.queued_status(ep)
        if queued:
            badges.insert(0, queued)
        bx = rx
        for b in badges:
            bf = T.font(7, "bold")
            bw = T.measure(b, bf) + 14
            color = {"IN CODA": T.ACCENT, "SCARICATO": T.SUCCESS, "IN CORSO": T.ACCENT_2}.get(b, T.MUTED)
            rounded_rect(self, bx - bw, 50, bx, 68, 9, fill=T.blend(color, fill, 0.82), outline="")
            self.create_text(bx - bw / 2, 59, text=b, fill=color, font=bf)
            bx -= bw + 6


class DetailView(tk.Frame):
    HERO_H = 290

    def __init__(self, parent, app):
        super().__init__(parent, bg=T.BG)
        self.app = app
        self.summary = self.data = None
        self.season = None
        self.episodes, self.rows = [], []
        self.selected = set()
        self._anchor = None
        self._req = self._season_req = 0
        self.hero_photo = self.poster_photo = None

        top = tk.Frame(self, bg=T.BG)
        top.pack(fill="x", padx=24, pady=(16, 0))
        Button(top, "Scopri", icon="back", command=app.show_search, variant="flat", height=34).pack(side="left")
        self.crumb = tk.Label(top, text="", bg=T.BG, fg=T.SUBTLE, font=T.font(10))
        self.crumb.pack(side="left", padx=4)

        self._build_action_bar()

        self.scroll = ScrollFrame(self)
        self.scroll.pack(fill="both", expand=True)
        self.hero = tk.Canvas(self.scroll.inner, height=self.HERO_H, bg=T.BG, highlightthickness=0, bd=0)
        self.hero.pack(fill="x")
        self.hero.bind("<Configure>", lambda e: self._draw_hero())

        outer = tk.Frame(self.scroll.inner, bg=T.BG)
        outer.pack(fill="x", padx=(32, 24), pady=(12, 28))
        self.notice = tk.Label(outer, text="", bg=T.BG, fg=T.MUTED, font=T.font(10), justify="left")
        self.series_box = body = tk.Frame(outer, bg=T.BG)
        body.pack(fill="x")
        head = tk.Frame(body, bg=T.BG)
        head.pack(fill="x")
        tk.Label(head, text="Stagioni", bg=T.BG, fg=T.TEXT, font=T.font(13, "bold")).pack(side="left")
        self.spinner = Spinner(head)
        self.spinner.pack(side="left", padx=12)
        self.season_flow = FlowFrame(body)
        self.season_flow.pack(fill="x", pady=(10, 22))
        ep_head = tk.Frame(body, bg=T.BG)
        ep_head.pack(fill="x", pady=(0, 8))
        tk.Label(ep_head, text="Episodi", bg=T.BG, fg=T.TEXT, font=T.font(13, "bold")).pack(side="left")
        self.ep_count = tk.Label(ep_head, text="", bg=T.BG, fg=T.MUTED, font=T.font(9))
        self.ep_count.pack(side="left", padx=10)
        tk.Label(ep_head, text="Clic per selezionare · Maiusc+clic per un intervallo · Ctrl+A tutti",
                 bg=T.BG, fg=T.SUBTLE, font=T.font(8)).pack(side="right")
        self.episodes_box = tk.Frame(body, bg=T.BG)
        self.episodes_box.pack(fill="x")

    def _build_action_bar(self):
        self.action_bar = bar = tk.Frame(self, bg=T.SURFACE)
        bar.pack(side="bottom", fill="x")
        tk.Frame(bar, bg=T.BORDER, height=1).pack(fill="x")
        inner = tk.Frame(bar, bg=T.SURFACE)
        inner.pack(fill="x", padx=24, pady=12)
        info = tk.Frame(inner, bg=T.SURFACE)
        info.pack(side="left")
        self.sel_label = tk.Label(info, text="", bg=T.SURFACE, fg=T.TEXT, font=T.font(11, "bold"))
        self.sel_label.pack(anchor="w")
        self.sel_sub = tk.Label(info, text="", bg=T.SURFACE, fg=T.MUTED, font=T.font(9))
        self.sel_sub.pack(anchor="w")
        self.sel_tools = tk.Frame(inner, bg=T.SURFACE)
        self.sel_tools.pack(side="left", padx=(20, 0))
        Button(self.sel_tools, "Tutti", command=self.select_all, variant="flat", height=32).pack(side="left")
        Button(self.sel_tools, "Nessuno", command=self.select_none, variant="flat", height=32).pack(side="left")
        self.btn_now = Button(inner, "Scarica ora", icon="download", command=lambda: self.add_selected(True),
                              variant="primary", height=40)
        self.btn_now.pack(side="right")
        self.btn_queue = Button(inner, "Aggiungi alla coda", icon="plus", command=lambda: self.add_selected(False),
                                height=40)
        self.btn_queue.pack(side="right", padx=10)
        self._update_action_bar()

    # ── Caricamento ──

    def load(self, summary):
        self._req += 1
        req = self._req
        self.summary, self.data, self.season = summary, None, None
        self.movie = False
        self.hero_photo = self.poster_photo = None
        self.crumb.config(text=f"/  {summary['name']}")
        for chip in self.season_flow.winfo_children():
            chip.destroy()
        self._show_episodes([], None)
        self._set_movie_mode(summary.get("type", "tv") != "tv")
        self.scroll.scroll_to_top()
        self._draw_hero()
        self._load_images(summary.get("images"))
        self.spinner.start()
        self.app.run_async(lambda: self.app.api.get_title(summary["id"], summary["slug"]),
                           lambda data: self._on_title(req, data),
                           lambda e: self._on_error(req, e))

    def _on_error(self, req, error):
        if req == self._req:
            self.spinner.stop()
            self.app.toast(f"Caricamento non riuscito: {error}", "error", 6000)

    def _load_images(self, images):
        loader = self.app.images
        req = self._req

        def set_hero(photo):
            if req == self._req:
                self.hero_photo = photo
                self._draw_hero()

        def set_poster(photo):
            if req == self._req:
                self.poster_photo = photo
                self._draw_hero()

        loader.load(loader.url_for(images, "background", "cover"), (1600, self.HERO_H), set_hero, style="hero")
        loader.load(loader.url_for(images, "poster", "cover_mobile"), (150, 225), set_poster, radius=12)

    def _on_title(self, req, data):
        if req != self._req:
            return
        self.spinner.stop()
        if not data:
            self.app.toast("Impossibile leggere i dettagli del titolo", "error")
            return
        self.data = data
        self.app.images.cdn_url = self.app.api.cdn_url
        if not self.hero_photo:
            self._load_images(data.get("images"))
        self._draw_hero()
        if data.get("type", self.summary.get("type")) != "tv" or not data.get("seasons"):
            self._set_movie_mode(True)
            return
        for season in data["seasons"]:
            n = season["number"]
            Chip(self.season_flow, f"Stagione {n}", command=lambda n=n: self.select_season(n)).pack()
        self.season_flow.relayout()
        loaded = data.get("loaded_season_number", 1)
        self._mark_season(loaded)
        self._show_episodes(data.get("episodes", []), loaded)

    def _set_movie_mode(self, movie):
        """I film non hanno stagioni/episodi: niente lista, la barra azioni
        scarica direttamente il titolo."""
        self.movie = movie
        if movie:
            self.series_box.pack_forget()
            self.sel_tools.pack_forget()
            self.notice.config(text=f"Il film verrà salvato in  {os.path.join(self.app.output_folder, 'Film')}")
            self.notice.pack(anchor="w", pady=10)
        else:
            self.notice.pack_forget()
            self.sel_tools.pack(side="left", padx=(20, 0), after=self.sel_label.master)
            self.series_box.pack(fill="x")
        self._update_action_bar()

    def _mark_season(self, number):
        self.season = number
        for chip in self.season_flow.winfo_children():
            chip.set_selected(chip.text == f"Stagione {number}")

    def select_season(self, number):
        if number == self.season or not self.data:
            return
        self._mark_season(number)
        self._season_req += 1
        req = self._season_req
        self.spinner.start()
        data = self.data
        self.app.run_async(lambda: self.app.api.get_season(data["id"], data["slug"], number),
                           lambda eps: self._on_season(req, eps, number),
                           lambda e: self._on_error(self._req, e))

    def _on_season(self, req, episodes, number):
        if req == self._season_req:
            self.spinner.stop()
            self._show_episodes(episodes, number)

    def _show_episodes(self, episodes, season):
        for row in self.rows:
            row.destroy()
        self.episodes, self.rows = episodes, []
        self.selected.clear()
        self._anchor = None
        for i, ep in enumerate(episodes):
            row = EpisodeRow(self.episodes_box, self, i, ep)
            row.pack(fill="x", pady=2)
            self.rows.append(row)
        total = sum(ep.get("duration") or 0 for ep in episodes)
        self.ep_count.config(text=f"{len(episodes)} episodi · {format_minutes(total)}" if episodes else "")
        self._update_action_bar()

    # ── Hero ──

    def _draw_hero(self):
        c = self.hero
        c.delete("all")
        w, h = c.winfo_width(), self.HERO_H
        if w <= 1 or not self.summary:
            return
        info = self.data or self.summary
        if self.hero_photo:
            c.create_image(0, 0, image=self.hero_photo, anchor="nw")
        pw, ph = 150, 225
        px, py = 32, h - ph - 16
        if self.poster_photo:
            c.create_image(px, py, image=self.poster_photo, anchor="nw")
        else:
            rounded_rect(c, px, py, px + pw, py + ph, 12, fill=placeholder_color(info["name"]), outline="")
            c.create_text(px + pw / 2, py + ph / 2, text=initials(info["name"]), fill=T.TEXT, font=T.font(30, "bold"))
        tx = px + pw + 28
        maxw = max(100, w - tx - 32)
        kind = "SERIE TV" if info.get("type", "tv") == "tv" else "FILM"
        c.create_text(tx, py + 4, text=kind, anchor="nw", fill=T.ACCENT_2, font=T.font(9, "bold"))
        tf = T.font(26, "bold")
        c.create_text(tx, py + 22, text=T.ellipsize(info["name"], tf, maxw), anchor="nw", fill=T.TEXT, font=tf)
        # Riga metadati
        y = py + 72
        x = tx
        score = info.get("score")
        mf = T.font(10)
        if score not in (None, "", "N/A"):
            draw_icon(c, "star", x + 7, y + 9, 15, T.WARNING)
            c.create_text(x + 18, y, text=str(score), anchor="nw", fill=T.TEXT, font=T.font(10, "bold"))
            x += 22 + T.measure(str(score), T.font(10, "bold")) + 10
        year = (info.get("release_date") or info.get("last_air_date") or "")[:4]
        seasons = len(info.get("seasons") or []) or info.get("seasons_count") or 0
        parts = [year] if year else []
        if seasons:
            parts.append(f"{seasons} stagion{'e' if seasons == 1 else 'i'}")
        parts += (info.get("genres") or [])[:3]
        c.create_text(x, y, text=T.ellipsize("  ·  ".join(parts), mf, maxw - (x - tx)), anchor="nw",
                      fill=T.MUTED, font=mf)
        plot = info.get("plot") or ""
        if plot:
            pf = T.font(10)
            lines = T.wrap_lines(plot, pf, min(maxw, 780), 4)
            c.create_text(tx, y + 32, text="\n".join(lines), anchor="nw", fill=T.blend(T.TEXT, T.MUTED, 0.35),
                          font=pf)

    # ── Selezione ──

    def queued_status(self, ep):
        if not self.data:
            return None
        status = self.app.queued_episodes().get((self.data["id"], ep.get("id")))
        return {"in_coda": "IN CODA", "in_corso": "IN CORSO", "completato": "SCARICATO"}.get(status)

    def toggle(self, index, shift=False):
        if shift and self._anchor is not None:
            lo, hi = sorted((self._anchor, index))
            target = self._anchor in self.selected
            for i in range(lo, hi + 1):
                (self.selected.add if target else self.selected.discard)(i)
        else:
            self.selected ^= {index}
            self._anchor = index
        self._redraw_rows()

    def select_all(self):
        self.selected = set(range(len(self.episodes)))
        self._redraw_rows()

    def select_none(self):
        self.selected.clear()
        self._redraw_rows()

    def _redraw_rows(self):
        for row in self.rows:
            row.draw()
        self._update_action_bar()

    def _update_action_bar(self):
        if getattr(self, "movie", False):
            info = self.data or self.summary
            status = self.app.queued_episodes().get((info["id"], None)) if self.data else None
            runtime = f"  ·  {format_minutes(info['runtime'])}" if info.get("runtime") else ""
            self.sel_label.config(text=f"Film{runtime}")
            self.sel_sub.config(text={"in_coda": "Già in coda", "in_corso": "Download in corso",
                                      "completato": "Già scaricato"}.get(status, "Film completo, audio italiano"))
            ready = self.data is not None and status not in ("in_coda", "in_corso", "completato")
            self.btn_now.set_enabled(ready)
            self.btn_queue.set_enabled(ready)
            return
        n = len(self.selected)
        if n:
            minutes = sum(self.episodes[i].get("duration") or 0 for i in self.selected)
            self.sel_label.config(text=f"{n} {'episodio selezionato' if n == 1 else 'episodi selezionati'}")
            self.sel_sub.config(text=f"circa {format_minutes(minutes)} di visione")
        else:
            self.sel_label.config(text="Nessun episodio selezionato")
            self.sel_sub.config(text="Scegli una stagione e clicca sugli episodi")
        self.btn_now.set_enabled(bool(n))
        self.btn_queue.set_enabled(bool(n))

    def add_selected(self, start_now):
        if self.movie and self.data:
            year = (self.data.get("release_date") or "")[:4]
            self.app.enqueue([{
                "kind": "movie",
                "title_name": self.data["name"],
                "title_id": self.data["id"],
                "episode_id": None,
                "season": 0,
                "episode": 0,
                "episode_name": "",
                "year": year,
                "duration": self.data.get("runtime") or 0,
            }], start_now)
            return
        if not self.selected or not self.data:
            return
        items = []
        for idx in sorted(self.selected):
            ep = self.episodes[idx]
            items.append({
                "title_name": self.data["name"],
                "title_id": self.data["id"],
                "season": self.season,
                "episode": ep.get("number", idx + 1),
                "episode_id": ep.get("id", 0),
                "episode_name": html.unescape(ep.get("name") or ""),
                "duration": ep.get("duration", 0),
            })
        self.app.enqueue(items, start_now)
        self.select_none()


# ─── Download ────────────────────────────────────────────────────────────────


class QueueCard(tk.Canvas):
    H = 100
    STATUS = {
        "in_coda": ("In coda", T.MUTED),
        "in_corso": ("In corso", T.ACCENT),
        "completato": ("Completato", T.SUCCESS),
        "errore": ("Errore", T.DANGER),
    }

    def __init__(self, parent, view, item):
        super().__init__(parent, height=self.H, bg=T.BG, highlightthickness=0, bd=0)
        self.view, self.item = view, item
        self.close_hover = False
        self._sig = None
        self.bind("<Configure>", lambda e: self.refresh(force=True))
        self.tag_bind("close", "<Enter>", lambda e: self._set_close_hover(True))
        self.tag_bind("close", "<Leave>", lambda e: self._set_close_hover(False))
        self.tag_bind("close", "<Button-1>", lambda e: view.remove(item))

    def _set_close_hover(self, value):
        self.close_hover = value
        self.configure(cursor="hand2" if value else "")
        self.refresh(force=True)

    def refresh(self, force=False):
        i = self.item
        sig = (self.winfo_width(), i["status"], round(i.get("video_progress", 0)), round(i.get("audio_progress", 0)),
               round(i.get("size_mb", 0) or 0, 1), round(i.get("speed_mb_s", 0) or 0, 1), i.get("error"))
        if sig == self._sig and not force:
            return
        self._sig = sig
        self._draw()

    def _draw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.H
        if w <= 1:
            return
        i = self.item
        status, color = self.STATUS.get(i["status"], (i["status"], T.MUTED))
        active = i["status"] == "in_corso"
        rounded_rect(self, 1, 4, w - 1, h - 4, 16, fill=T.SURFACE, outline=T.blend(color, T.SURFACE, 0.5)
                     if active else T.BORDER)
        # Pallino di stato
        self.create_oval(20, 23, 30, 33, fill=color, outline="")
        if active:
            self.create_oval(16, 19, 34, 37, outline=T.blend(color, T.SURFACE, 0.6), width=2)
        # Titolo e sottotitolo
        x = 46
        tf = T.font(11, "bold")
        self.create_text(x, 18, text=T.ellipsize(i["title_name"], tf, w - x - 250), anchor="nw", fill=T.TEXT,
                         font=tf)
        if i.get("kind") == "movie":
            sub = "  ·  ".join(p for p in ("Film", i.get("year"), format_minutes(i.get("duration"))) if p)
        else:
            sub = f"S{i['season']:02d}E{i['episode']:02d}"
        if i.get("episode_name"):
            sub += f"  ·  {i['episode_name']}"
        self.create_text(x, 40, text=T.ellipsize(sub, T.font(9), w - x - 250), anchor="nw", fill=T.MUTED,
                         font=T.font(9))
        # Pill di stato + chiudi
        pf = T.font(8, "bold")
        pw = T.measure(status, pf) + 20
        rx = w - 52
        rounded_rect(self, rx - pw, 16, rx, 36, 10, fill=T.blend(color, T.SURFACE, 0.82), outline="")
        self.create_text(rx - pw / 2, 26, text=status, fill=color, font=pf)
        cx = w - 28
        if self.close_hover:
            self.create_oval(cx - 13, 13, cx + 13, 39, fill=T.SURFACE_3, outline="", tags="close")
        else:
            self.create_oval(cx - 13, 13, cx + 13, 39, fill=T.SURFACE, outline="", tags="close")
        draw_icon(self, "close", cx, 26, 16, T.TEXT if self.close_hover else T.SUBTLE, tags="close")
        # Metadati a destra, seconda riga
        size = i.get("size_mb") or 0
        speed = i.get("speed_mb_s") or 0
        meta = []
        if size:
            meta.append(format_size(size))
        if active and speed:
            meta.append(f"{speed:.1f} MB/s")
        if meta:
            self.create_text(w - 24, 44, text="  ·  ".join(meta), anchor="ne", fill=T.TEXT, font=T.font(9, "bold"))
        # Barre / messaggio
        y = 72
        if i["status"] == "errore":
            msg = (i.get("error") or "Errore sconosciuto") + "  —  dettagli in .sc_debug.log"
            self.create_text(x, y, text=T.ellipsize(msg, T.font(9), w - x - 24), anchor="w", fill=T.DANGER,
                             font=T.font(9))
        elif i["status"] == "completato":
            self._bar(x, w - 24, y, 100, T.SUCCESS)
        elif active or i.get("progress"):
            mid = x + (w - 24 - x) / 2
            self._labeled_bar("VIDEO", x, mid - 16, y, i.get("video_progress", 0), T.ACCENT)
            self._labeled_bar("AUDIO", mid + 16, w - 24, y, i.get("audio_progress", 0), T.ACCENT_2)
        else:
            self.create_text(x, y, text="In attesa di essere scaricato", anchor="w", fill=T.SUBTLE, font=T.font(9))

    def _labeled_bar(self, label, x1, x2, y, pct, color):
        lf = T.font(7, "bold")
        self.create_text(x1, y, text=label, anchor="w", fill=T.SUBTLE, font=lf)
        self.create_text(x2, y, text=f"{pct:.0f}%", anchor="e", fill=color, font=T.font(8, "bold"))
        self._bar(x1 + 46, x2 - 40, y, pct, color)

    def _bar(self, x1, x2, y, pct, color):
        if x2 <= x1:
            return
        rounded_rect(self, x1, y - 3, x2, y + 3, 3, fill=T.SURFACE_3, outline="")
        fw = (x2 - x1) * pct / 100
        if fw >= 1:
            rounded_rect(self, x1, y - 3, x1 + max(fw, 6), y + 3, 3, fill=color, outline="")


class DownloadsView(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=T.BG)
        self.app = app
        self.cards = {}
        self._order = []

        top = tk.Frame(self, bg=T.BG)
        top.pack(fill="x", padx=36, pady=(30, 0))
        page_header(top, "Download", "Coda, avanzamento e velocità in tempo reale").pack(fill="x", pady=(0, 18))

        # Dashboard
        dash = Card(top, padding=18)
        dash.pack(fill="x")
        d = dash.inner
        self.ring = ProgressRing(d, size=116, thickness=10, font_size=20)
        self.ring.pack(side="left")
        stats = tk.Frame(d, bg=T.SURFACE)
        stats.pack(side="left", padx=(26, 26), fill="y")
        self.stat_speed = self._stat(stats, "VELOCITÀ", "0.0 MB/s", T.ACCENT_2)
        self.stat_size = self._stat(stats, "SCARICATI", "0 MB", T.TEXT)
        self.stat_done = self._stat(stats, "COMPLETATI", "0 / 0", T.TEXT)
        graph = tk.Frame(d, bg=T.SURFACE)
        graph.pack(side="left", fill="both", expand=True)
        tk.Label(graph, text="THROUGHPUT · ULTIMI 90 SECONDI", bg=T.SURFACE, fg=T.SUBTLE, font=T.font(8, "bold")) \
            .pack(anchor="w")
        self.spark = Sparkline(graph, height=90)
        self.spark.pack(fill="both", expand=True, pady=(6, 0))

        # Barra comandi
        tools = tk.Frame(top, bg=T.BG)
        tools.pack(fill="x", pady=(18, 10))
        self.btn_start = Button(tools, "Avvia download", icon="play", command=app.toggle_download,
                                variant="primary", height=40)
        self.btn_start.pack(side="left")
        Button(tools, "Rimuovi completati", icon="check", command=self.clear_completed, variant="flat",
               height=40).pack(side="left", padx=(10, 0))
        Button(tools, "Svuota coda", icon="trash", command=self.clear_all, variant="flat", height=40) \
            .pack(side="left")
        self.folder_btn = Button(tools, "", icon="folder", command=app.choose_folder, variant="ghost", height=40)
        self.folder_btn.pack(side="right")
        self.status = tk.Label(top, text="Pronto", bg=T.BG, fg=T.MUTED, font=T.font(9), anchor="w")
        self.status.pack(fill="x")

        self.scroll = ScrollFrame(self)
        self.scroll.pack(fill="both", expand=True, padx=(36, 20), pady=(8, 0))
        self.list = tk.Frame(self.scroll.inner, bg=T.BG)
        self.list.pack(fill="x", padx=(0, 16))
        self.empty = empty_state(self.scroll.inner, "download", "La coda è vuota",
                                 "Cerca una serie in Scopri, seleziona gli episodi\n"
                                 "e aggiungili qui con \"Aggiungi alla coda\".")
        self.update_folder()

    @staticmethod
    def _stat(parent, label, value, color):
        box = tk.Frame(parent, bg=T.SURFACE)
        box.pack(anchor="w", pady=(0, 4))
        tk.Label(box, text=label, bg=T.SURFACE, fg=T.SUBTLE, font=T.font(8, "bold")).pack(anchor="w")
        lbl = tk.Label(box, text=value, bg=T.SURFACE, fg=color, font=T.font(14, "bold"))
        lbl.pack(anchor="w")
        return lbl

    def update_folder(self):
        path = self.app.output_folder
        home = os.path.expanduser("~")
        if path.startswith(home):
            path = "~" + path[len(home):]
        f = T.font(10, "bold")
        if T.measure(path, f) > 300:
            path = "…" + path[-40:]
        self.folder_btn.set_text(path)

    def set_status(self, text):
        self.status.config(text=text)

    def tick(self):
        dm = self.app.download_manager
        queue = dm.queue
        order = [id(item) for item in queue]
        if order != self._order:
            self._order = order
            for key in list(self.cards):
                if key not in order:
                    self.cards.pop(key).destroy()
            for item in queue:
                card = self.cards.get(id(item))
                if card is None:
                    card = self.cards[id(item)] = QueueCard(self.list, self, item)
                card.pack_forget()
            for item in queue:
                self.cards[id(item)].pack(fill="x", pady=2)
            if queue:
                self.empty.pack_forget()
            else:
                self.empty.pack(pady=50)
        for card in self.cards.values():
            card.refresh()

        done = sum(1 for i in queue if i["status"] == "completato")
        size = sum(i.get("size_mb") or 0 for i in queue)
        self.ring.set(dm._overall_progress(), f"{done}/{len(queue)}" if queue else "")
        self.stat_speed.config(text=f"{self.app.current_speed():.1f} MB/s")
        self.stat_size.config(text=format_size(size))
        self.stat_done.config(text=f"{done} / {len(queue)}")
        if dm.is_downloading:
            self.btn_start.set_text("Interrompi")
            self.btn_start.set_variant("danger", icon="stop")
        else:
            self.btn_start.set_text("Avvia download")
            self.btn_start.set_variant("primary", icon="play")

    def remove(self, item):
        dm = self.app.download_manager
        idx = next((n for n, x in enumerate(dm.queue) if x is item), None)
        if idx is None:
            return
        if item["status"] == "in_corso":
            if not messagebox.askyesno("Download in corso",
                                       "Questo episodio è in download: rimuoverlo interrompe tutti i download "
                                       "in corso. Continuare?", parent=self):
                return
            dm.kill_current()
        dm.remove(idx)
        self.tick()

    def clear_completed(self):
        dm = self.app.download_manager
        for idx in reversed(range(len(dm.queue))):
            if dm.queue[idx]["status"] == "completato":
                dm.remove(idx)
        self.tick()

    def clear_all(self):
        dm = self.app.download_manager
        if not dm.queue:
            return
        if dm.is_downloading:
            if not messagebox.askyesno("Download in corso", "Svuotare la coda interrompe i download in corso. "
                                       "Continuare?", parent=self):
                return
            dm.kill_current()
        dm.clear()
        self.tick()


# ─── Impostazioni ────────────────────────────────────────────────────────────


class SettingsView(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=T.BG)
        self.app = app
        scroll = ScrollFrame(self)
        scroll.pack(fill="both", expand=True)
        body = tk.Frame(scroll.inner, bg=T.BG)
        body.pack(fill="x", padx=36, pady=30)
        page_header(body, "Impostazioni", "Le modifiche vengono salvate subito").pack(fill="x", pady=(0, 18))

        self.warning = tk.Label(body, text="Un download è in corso: le nuove impostazioni di download si "
                                            "applicheranno dal prossimo avvio.",
                                bg=T.blend(T.WARNING, T.BG, 0.85), fg=T.WARNING, font=T.font(9, "bold"),
                                anchor="w", padx=14, pady=10)
        self.warning_anchor = tk.Frame(body, bg=T.BG)
        self.warning_anchor.pack(fill="x")

        # Cartella
        card = self._card(body, "Cartella di destinazione",
                          "Serie:  <cartella>/<Nome serie>/Stagione NN/     Film:  <cartella>/Film/")
        row = tk.Frame(card, bg=T.SURFACE)
        row.pack(fill="x", pady=(12, 0))
        self.folder_label = tk.Label(row, text="", bg=T.SURFACE_2, fg=T.TEXT, font=T.font(10), anchor="w",
                                     padx=12, pady=8)
        self.folder_label.pack(side="left", fill="x", expand=True)
        Button(row, "Cambia", icon="folder", command=app.choose_folder, height=38).pack(side="left", padx=(10, 0))

        # Parallelismo
        card = self._card(body, "Episodi in parallelo",
                          "Quanti episodi scaricare contemporaneamente (ognuno scarica già video e audio in "
                          "parallelo). Valori alti possono non aumentare la velocità reale e rischiano di far "
                          "limitare le connessioni dal sito.")
        Stepper(card, app.max_parallel_episodes, 1, 5,
                command=lambda v: app.update_settings(max_parallel_episodes=v)).pack(anchor="w", pady=(12, 0))

        card = self._card(body, "Frammenti concorrenti per stream",
                          "Connessioni parallele usate da yt-dlp per scaricare i frammenti di ogni singolo "
                          "stream video/audio.")
        Stepper(card, app.concurrent_fragments, 1, 16,
                command=lambda v: app.update_settings(concurrent_fragments=v)).pack(anchor="w", pady=(12, 0))

        # Scorciatoie e info
        card = self._card(body, "Scorciatoie da tastiera", "")
        for keys, desc in (("Ctrl+F  /  /", "Vai alla ricerca"), ("Ctrl+1 · 2 · 3", "Cambia sezione"),
                           ("Esc", "Torna ai risultati"), ("Ctrl+A", "Seleziona tutti gli episodi"),
                           ("Invio", "Aggiungi gli episodi selezionati alla coda")):
            r = tk.Frame(card, bg=T.SURFACE)
            r.pack(fill="x", pady=2)
            tk.Label(r, text=keys, bg=T.SURFACE_3, fg=T.TEXT, font=T.font(9, "bold"), padx=8, pady=2,
                     width=14).pack(side="left")
            tk.Label(r, text=desc, bg=T.SURFACE, fg=T.MUTED, font=T.font(9)).pack(side="left", padx=12)

        card = self._card(body, f"SC Downloader {__version__}",
                          "Progetto a scopo educativo. Non affiliato con StreamingCommunity o vixcloud.co. "
                          "In caso di errori i dettagli sono salvati in .sc_debug.log.")
        self.refresh()

    def _card(self, parent, title, text):
        card = Card(parent)
        card.pack(fill="x", pady=(0, 14))
        tk.Label(card.inner, text=title, bg=T.SURFACE, fg=T.TEXT, font=T.font(12, "bold")).pack(anchor="w")
        if text:
            desc = tk.Label(card.inner, text=text, bg=T.SURFACE, fg=T.MUTED, font=T.font(9), justify="left",
                            anchor="w")
            desc.pack(anchor="w", fill="x", pady=(4, 0))
            card.inner.bind("<Configure>", lambda e: desc.config(wraplength=max(200, e.width - 10)), add="+")
        return card.inner

    def refresh(self):
        self.folder_label.config(text=self.app.output_folder)
        if self.app.download_manager.is_downloading:
            self.warning.pack(in_=self.warning_anchor, fill="x", pady=(0, 14))
        else:
            self.warning.pack_forget()
