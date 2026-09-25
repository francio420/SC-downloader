import html
import json
import re

from curl_cffi import requests as curl_requests

from .constants import BASE_URL, USER_AGENT

# ─── StreamingCommunityAPI ───────────────────────────────────────────────────


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
            "Referer": f"{BASE_URL}/",
        }

    def _parse_data_page(self, html):
        """Estrae il JSON dal data-page attribute di Inertia.js."""
        m = re.search(r'data-page="([^"]+)"', html)
        if not m:
            return None
        data = json.loads(m.group(1).replace("&quot;", '"').replace("&amp;", "&"))
        cdn_url = data.get("props", {}).get("cdn_url")
        if cdn_url:
            self.cdn_url = cdn_url.rstrip("/")
        return data

    def search(self, query, page=1):
        """Cerca titoli. Restituisce lista di dict con id, name, type, score, slug, seasons_count."""
        params = {"q": query, "page": page}
        resp = self.session.get(f"{BASE_URL}/it/search", headers=self._headers(), params=params)
        data = self._parse_data_page(resp.text)
        if not data:
            return [], 0
        titles = data.get("props", {}).get("titles", [])
        total = data.get("props", {}).get("totalCount", 0)
        results = []
        for t in titles:
            results.append({
                "id": t["id"],
                "name": html.unescape(t["name"]),
                "slug": t["slug"],
                "type": t.get("type", "tv"),
                "score": t.get("score", "N/A"),
                "seasons_count": t.get("seasons_count", 0),
                "sub_ita": t.get("sub_ita", 0),
                "last_air_date": t.get("last_air_date"),
                "images": t.get("images", []),
            })
        return results, total

    def get_title(self, title_id, slug):
        """Ottiene dettagli titolo con lista stagioni e episodi della prima stagione."""
        url = f"{BASE_URL}/it/titles/{title_id}-{slug}"
        resp = self.session.get(url, headers=self._headers())
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
            "images": title.get("images", []),
            "seasons": seasons,
            "loaded_season_number": loaded_season.get("number", 1),
            "episodes": episodes,
        }

    def get_season(self, title_id, slug, season_number):
        """Ottiene episodi di una stagione specifica."""
        url = f"{BASE_URL}/it/titles/{title_id}-{slug}/season-{season_number}"
        resp = self.session.get(url, headers=self._headers())
        data = self._parse_data_page(resp.text)
        if not data:
            return []
        loaded_season = data.get("props", {}).get("loadedSeason", {})
        return loaded_season.get("episodes", [])
