import re
from urllib.parse import parse_qs, urlparse

from curl_cffi import requests as curl_requests

from .constants import USER_AGENT, base_url, follow_redirect

# ─── ScrapeEngine ────────────────────────────────────────────────────────────


class ScrapeEngine:
    """Estrazione URL M3U8 da vixcloud.co."""

    def __init__(self, session=None):
        self.session = session or curl_requests.Session(impersonate="chrome")

    def build_m3u8(self, title_id, episode_id=None):
        """Costruisce l'URL M3U8 partendo dal title_id e episode_id (None per
        i film, che hanno un solo video per titolo)."""
        return self.build_m3u8_info(title_id, episode_id)[0]

    def build_m3u8_info(self, title_id, episode_id=None):
        """Come build_m3u8, ma restituisce (url, can_fhd): can_fhd e' il flag canPlayFHD del player in quel
        momento. Se e' False la playlist arriva al massimo a 720p (il sito a volte non concede il 1080p)."""
        # Step 1: Fetch the iframe page to get the vixcloud embed URL
        iframe_url = f"{base_url()}/it/iframe/{title_id}"
        if episode_id is not None:
            iframe_url += f"?episode_id={episode_id}"
        resp_html = self.session.get(
            iframe_url,
            headers={"User-Agent": USER_AGENT, "Referer": f"{base_url()}/it/watch/{title_id}"},
        )
        follow_redirect(iframe_url, getattr(resp_html, "url", None))

        vix_match = re.search(r'src="(https://vixcloud\.co/embed[^"]+)"', resp_html.text)
        if not vix_match:
            raise Exception("Impossibile trovare l'embed vixcloud.co")

        vix_url = vix_match.group(1).replace("&amp;", "&")
        return self.m3u8_from_embed(vix_url, f"{base_url()}/")

    def m3u8_from_embed(self, vix_url, referer):
        """(url M3U8, can_fhd) dalla pagina embed di vixcloud. Serve anche ad altri siti che usano lo stesso
        player (es. AnimeUnity, il cui /embed-url/{episodio} porta a vixcloud.co/embed/...)."""
        # Step 2: Fetch the vixcloud embed page to get playlist info
        resp_vix = self.session.get(
            vix_url,
            headers={"User-Agent": USER_AGENT, "Referer": referer},
        )

        if resp_vix.status_code != 200:
            raise Exception(f"Errore vixcloud: HTTP {resp_vix.status_code}")

        content = resp_vix.text

        token_match = re.search(r"'token':\s*'([^']+)'", content)
        expires_match = re.search(r"'expires':\s*'([^']+)'", content)
        url_match = re.search(r"url:\s*'(https?://[^']+)'", content)
        fhd_match = re.search(r"canPlayFHD\s*=\s*(true|false)", content)

        if not all([token_match, expires_match, url_match]):
            raise Exception("Impossibile estrarre token/url da vixcloud")

        token = token_match.group(1)
        expires = expires_match.group(1)
        playlist_url = url_match.group(1)
        can_fhd = fhd_match.group(1) == "true" if fhd_match else False

        parsed = urlparse(playlist_url)
        params = parse_qs(parsed.query, keep_blank_values=True)
        params["token"] = [token]
        params["expires"] = [expires]
        if can_fhd:
            params["h"] = ["1"]
        # params contiene già anche la query originale (es. "b=1"): il separatore dopo il path è sempre "?"
        flat_params = "&".join(f"{k}={v[0]}" for k, v in params.items())
        m3u8_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}?{flat_params}"

        return m3u8_url, can_fhd

    def has_separate_audio(self, m3u8_url):
        """True se la master playlist ha tracce audio separate (EXT-X-MEDIA
        TYPE=AUDIO), il caso tipico; False se gli stream sono gia' muxati
        video+audio (succede per alcuni titoli, es. quelli con "b=1" nell'URL).
        In caso di errore assume il caso tipico."""
        try:
            resp = self.session.get(
                m3u8_url,
                headers={"User-Agent": USER_AGENT, "Referer": "https://vixcloud.co/", "Origin": "https://vixcloud.co"},
            )
        except Exception:
            return True
        if resp.status_code != 200 or "#EXTM3U" not in resp.text:
            return True
        return "TYPE=AUDIO" in resp.text
