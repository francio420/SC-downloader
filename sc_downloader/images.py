import io
import threading
from concurrent.futures import ThreadPoolExecutor

from curl_cffi import requests as curl_requests

from . import theme as T
from .constants import USER_AGENT

# Pillow e' opzionale: serve solo a decodificare le immagini .webp del CDN
# (Tk da solo legge PNG/GIF). Senza, l'interfaccia mostra dei segnaposto.
try:
    from PIL import Image, ImageChops, ImageDraw, ImageOps, ImageTk
    AVAILABLE = True
except ImportError:
    AVAILABLE = False

# ─── ImageLoader ─────────────────────────────────────────────────────────────


class ImageLoader:
    """Scarica ed elabora (ritaglio, angoli arrotondati, sfumature) le immagini
    in thread separati; la PhotoImage finale viene creata sul thread Tk."""

    def __init__(self, root):
        self.root = root
        self.cdn_url = None
        self._pool = ThreadPoolExecutor(max_workers=6)
        self._photos = {}
        self._raw = {}
        self._raw_lock = threading.Lock()

    def url_for(self, images, *types):
        """URL della prima immagine del tipo richiesto (in ordine di preferenza)."""
        if not self.cdn_url or not images:
            return None
        for kind in types:
            for img in images:
                if img.get("type") == kind and img.get("filename"):
                    return f"{self.cdn_url}/images/{img['filename']}"
        return None

    def load(self, url, size, callback, radius=0, style=None, bg=T.BG):
        """callback(PhotoImage) sul thread Tk; non chiamata se l'immagine non e'
        disponibile. style: None | "hero" (sfumata verso il fondo)."""
        if not AVAILABLE or not url:
            return
        key = (url, size, radius, style, bg)
        if key in self._photos:
            callback(self._photos[key])
            return

        def work():
            try:
                image = self._process(self._fetch(url), size, radius, style, bg)
            except Exception:
                return
            self.root.after(0, finish, image)

        def finish(image):
            try:
                photo = self._photos.get(key) or ImageTk.PhotoImage(image)
            except Exception:
                return
            self._photos[key] = photo
            callback(photo)

        self._pool.submit(work)

    def _fetch(self, url):
        with self._raw_lock:
            data = self._raw.get(url)
        if data is None:
            resp = curl_requests.get(url, impersonate="chrome", timeout=20, headers={"User-Agent": USER_AGENT})
            resp.raise_for_status()
            data = resp.content
            with self._raw_lock:
                self._raw[url] = data
        return data

    @staticmethod
    def _process(data, size, radius, style, bg):
        img = Image.open(io.BytesIO(data)).convert("RGB")
        img = ImageOps.fit(img, size, Image.LANCZOS, centering=(0.5, 0.3 if style == "hero" else 0.5))
        bg_rgb = tuple(int(bg[i:i + 2], 16) for i in (1, 3, 5))
        if style == "hero":
            # Scurisce e sfuma verso il colore di fondo in basso e a sinistra,
            # cosi' il testo sovrapposto resta leggibile.
            w, h = size
            base = Image.new("RGB", size, bg_rgb)
            vertical = Image.new("L", (1, h))
            vertical.putdata([int(255 * (1 - (y / h) ** 1.6)) for y in range(h)])
            horizontal = Image.new("L", (w, 1))
            horizontal.putdata([int(255 * min(1.0, 0.25 + x / (w * 0.75))) for x in range(w)])
            mask = ImageChops.multiply(vertical.resize(size), horizontal.resize(size))
            img = Image.composite(img, base, mask.point(lambda v: v * 150 // 255))
        if radius:
            scale = 3
            mask = Image.new("L", (size[0] * scale, size[1] * scale), 0)
            ImageDraw.Draw(mask).rounded_rectangle(
                (0, 0, size[0] * scale - 1, size[1] * scale - 1), radius * scale, fill=255)
            mask = mask.resize(size, Image.LANCZOS)
            img = Image.composite(img, Image.new("RGB", size, bg_rgb), mask)
        return img
