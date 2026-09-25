import tkinter.font as tkfont
from tkinter import ttk

# ─── Palette ─────────────────────────────────────────────────────────────────
# Tema "notte da cinema": fondo quasi nero con due accenti (viola/ciano) usati
# anche come colori distinti per i flussi video (viola) e audio (ciano).

BG = "#0d0d14"
SURFACE = "#15151f"
SURFACE_2 = "#1c1c29"
SURFACE_3 = "#262637"
BORDER = "#2d2d42"
TEXT = "#ececf5"
MUTED = "#8b8ba7"
SUBTLE = "#5b5b76"
ACCENT = "#8b7bff"
ACCENT_2 = "#2dd4ee"
SUCCESS = "#3ddc97"
WARNING = "#f7c35f"
DANGER = "#ff6b81"
ON_ACCENT = "#0d0d14"

_PREFERRED_FAMILIES = ("Inter", "Segoe UI", "SF Pro Text", "Noto Sans", "Cantarell", "Ubuntu", "DejaVu Sans")
_family = None


def family():
    """Primo font "moderno" disponibile sul sistema (richiede una root Tk)."""
    global _family
    if _family is None:
        available = set(tkfont.families())
        _family = next((f for f in _PREFERRED_FAMILIES if f in available), "TkDefaultFont")
    return _family


def font(size=10, weight="normal"):
    return (family(), size, weight)


_fonts = {}
_char_widths = {}


def measure(text, fnt):
    """Larghezza in pixel del testo. Ogni `font measure` di Tk costa ~1 ms e
    troncare/andare a capo ne richiede centinaia per ridisegno, quindi si
    misura ogni carattere una volta sola e si somma: Tk non applica kerning,
    per cui il risultato coincide al pixel con la misura dell'intera stringa."""
    widths = _char_widths.get(fnt)
    if widths is None:
        widths = _char_widths[fnt] = {}
        _fonts[fnt] = tkfont.Font(family=fnt[0], size=fnt[1], weight=fnt[2])
    total = 0
    for ch in text:
        w = widths.get(ch)
        if w is None:
            w = widths[ch] = _fonts[fnt].measure(ch)
        total += w
    return total


def ellipsize(text, fnt, max_width):
    if measure(text, fnt) <= max_width:
        return text
    lo, hi = 0, len(text)  # ricerca binaria del prefisso piu' lungo che ci sta
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if measure(text[:mid] + "…", fnt) <= max_width:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo].rstrip() + "…"


def wrap_lines(text, fnt, max_width, max_lines):
    """Spezza il testo in al massimo max_lines righe, con "…" sull'ultima se
    non ci sta tutto (il testo dei Canvas non ha un troncamento nativo)."""
    words = (text or "").split()
    lines, current = [], ""
    for i, word in enumerate(words):
        candidate = f"{current} {word}".strip()
        if measure(candidate, fnt) <= max_width or not current:
            current = candidate
            continue
        lines.append(current)
        current = word
        if len(lines) == max_lines:
            rest = " ".join([lines.pop()] + words[i:])
            lines.append(ellipsize(rest, fnt, max_width))
            return lines
    if current:
        lines.append(ellipsize(current, fnt, max_width))
    return lines


def blend(c1, c2, t):
    """Miscela due colori hex (Tk non supporta la trasparenza sui widget)."""
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(a, b))


def setup_styles(root):
    root.configure(bg=BG)
    root.option_add("*Font", font(10))
    style = ttk.Style(root)
    style.theme_use("clam")
    # Scrollbar sottile senza frecce
    for orient in ("Vertical", "Horizontal"):
        style.layout(f"{orient}.TScrollbar", [(f"{orient}.Scrollbar.trough", {
            "sticky": "ns" if orient == "Vertical" else "we",
            "children": [(f"{orient}.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"})],
        })])
        style.configure(f"{orient}.TScrollbar", troughcolor=BG, background=SURFACE_3, bordercolor=BG,
                        lightcolor=SURFACE_3, darkcolor=SURFACE_3, arrowsize=8, gripcount=0)
        style.map(f"{orient}.TScrollbar", background=[("active", SUBTLE)])
    style.configure("TEntry", fieldbackground=SURFACE_2, foreground=TEXT, insertcolor=TEXT,
                    bordercolor=BORDER, lightcolor=SURFACE_2, darkcolor=SURFACE_2, padding=6)
