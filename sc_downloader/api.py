import html
import json
import re

from curl_cffi import requests as curl_requests

from .constants import USER_AGENT, base_url, follow_redirect

class SiteError(Exception):
    """Il sito non ha risposto con una sua pagina (errore HTTP, pagina di blocco, dominio sbagliato)."""


# ─── StreamingCommunityAPI ───────────────────────────────────────────────────


def _unescape_strings(value):
    """I testi del sito arrivano con codici HTML anche dentro il JSON (es. "sull&#39;inferno" nei nomi e nelle trame
    degli episodi): si decodificano tutti, una volta, appena letti."""
    if isinstance(value, str):
        return html.unescape(value) if "&" in value else value
    if isinstance(value, list):
        return [_unescape_strings(v) for v in value]
    if isinstance(value, dict):
        return {k: _unescape_strings(v) for k, v in value.items()}
    return value


class StreamingCommunityAPI:
    """Comunicazione con StreamingCommunity parsing data-page HTML."""

    def __init__(self):
        self.session = curl_requests.Session(impersonate="chrome")
        # Base URL delle immagini (poster, copertine), letta dalle props della
        # pagina: il dominio del CDN cambia insieme a quello del sito.
        self.cdn_url = None

    def _headers(self):
        return {
            "User-Agent": USER_AGENT,
            "Referer": f"{base_url()}/",
        }

    def _get(self, path, **kwargs):
        """GET di una pagina del sito; se il dominio ha fatto redirect a uno nuovo, da qui in poi si usa quello."""
        url = f"{base_url()}{path}"
        resp = self.session.get(url, headers=self._headers(), **kwargs)
        follow_redirect(url, getattr(resp, "url", None))
        # pagina d'errore (sito giu', sovraccarico, bloccato): non e' una risposta vuota, e chi la ricevesse come
        # tale salverebbe "nessun risultato". Il 404 resta una risposta (titolo che non esiste).
        if resp.status_code >= 500 or resp.status_code in (403, 429):
            raise SiteError(f"{path}: HTTP {resp.status_code}")
        return resp

    def _parse_data_page(self, html):
        """Estrae il JSON dal data-page attribute di Inertia.js."""
        m = re.search(r'data-page="([^"]+)"', html)
        if not m:
            return None
        data = _unescape_strings(json.loads(m.group(1).replace("&quot;", '"').replace("&amp;", "&")))
        cdn_url = data.get("props", {}).get("cdn_url")
        if cdn_url:
            self.cdn_url = cdn_url.rstrip("/")
        return data

    def search(self, query, page=1):
        """Cerca titoli. Restituisce lista di dict con id, name, type, score, slug, seasons_count."""
        params = {"q": query, "page": page}
        resp = self._get("/it/search", params=params)
        data = self._parse_data_page(resp.text)
        if not data:
            raise SiteError("la pagina di ricerca non e' quella del sito (dominio cambiato o pagina di blocco?)")
        titles = data.get("props", {}).get("titles", [])
        total = data.get("props", {}).get("totalCount", 0)
        return [self._summarize_title(t) for t in titles], total

    @staticmethod
    def _summarize_title(t):
        """Riga di elenco (ricerca, homepage) con i soli campi usati dalle viste."""
        return {
            "id": t["id"],
            "name": html.unescape(t["name"]),
            "slug": t["slug"],
            "type": t.get("type", "tv"),
            "score": t.get("score", "N/A"),
            "seasons_count": t.get("seasons_count", 0),
            "sub_ita": t.get("sub_ita", 0),
            "last_air_date": t.get("last_air_date"),
            "images": t.get("images", []),
        }

    @staticmethod
    def _credits(people):
        people = sorted(people or [], key=lambda p: (p.get("pivot") or {}).get("order", 0))
        return [html.unescape(p["name"]) for p in people if p.get("name")]

    def get_home(self):
        """Slider della homepage (es. trending, latest, top10).

        Restituisce una lista di dict {name, label, titles}: `name` e' la chiave
        del sito, `label` il titolo in italiano, `titles` righe come in search().
        """
        resp = self._get("/it")
        data = self._parse_data_page(resp.text)
        if not data:
            return []
        sliders = data.get("props", {}).get("sliders", [])
        return [
            {
                "name": s.get("name", ""),
                "label": s.get("label", ""),
                "titles": [self._summarize_title(t) for t in s.get("titles", [])],
            }
            for s in sliders
        ]

    def get_latest(self):
        """Titoli aggiunti di recente (slider "latest" della homepage)."""
        for slider in self.get_home():
            if slider["name"] == "latest":
                return slider["titles"]
        return []

    def get_title(self, title_id, slug):
        """Ottiene dettagli titolo con lista stagioni e episodi della prima stagione."""
        resp = self._get(f"/it/titles/{title_id}-{slug}")
        data = self._parse_data_page(resp.text)
        if not data:
            return None
        props = data.get("props", {})
        title = props.get("title", {})
        # Per i film loadedSeason e' null
        loaded_season = props.get("loadedSeason") or {}
        seasons = title.get("seasons", [])
        episodes = loaded_season.get("episodes", [])
        return {
            "id": title.get("id", title_id),
            "name": html.unescape(title.get("name", "")),
            "slug": title.get("slug", slug),
            "type": title.get("type", "tv"),
            "plot": html.unescape(title.get("plot") or ""),
            "score": title.get("score"),
            "release_date": title.get("release_date") or title.get("last_air_date"),
            "runtime": title.get("runtime"),
            "genres": [g.get("name", "") for g in title.get("genres", []) if g.get("name")],
            # attori e registi principali, nell'ordine del sito
            "cast": self._credits(title.get("main_actors")),
            "directors": self._credits(title.get("main_directors")),
            "images": title.get("images", []),
            # Lingua (anche sui singoli episodi): dub_ita=0 + sub_ita=1 = solo audio originale coi sottotitoli
            # (es. episodi appena usciti, non ancora doppiati). None se il sito non li riporta.
            "dub_ita": title.get("dub_ita"),
            "sub_ita": title.get("sub_ita"),
            "original_language": title.get("original_language"),
            "seasons": seasons,
            "loaded_season_number": loaded_season.get("number", 1),
            "episodes": episodes,
        }

    def get_season(self, title_id, slug, season_number):
        """Ottiene episodi di una stagione specifica."""
        resp = self._get(f"/it/titles/{title_id}-{slug}/season-{season_number}")
        data = self._parse_data_page(resp.text)
        if not data:
            return []
        loaded_season = data.get("props", {}).get("loadedSeason", {})
        return loaded_season.get("episodes", [])
