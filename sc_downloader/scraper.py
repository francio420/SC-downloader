import re
from urllib.parse import parse_qs, urlparse

from curl_cffi import requests as curl_requests

from .constants import BASE_URL, USER_AGENT

# ─── ScrapeEngine ────────────────────────────────────────────────────────────


class ScrapeEngine:
    """Estrazione URL M3U8 da vixcloud.co."""

    def __init__(self, session=None):
        self.session = session or curl_requests.Session(impersonate="chrome")

    def build_m3u8(self, title_id, episode_id):
        """Costruisce l'URL M3U8 partendo dal title_id e episode_id."""
        # Step 1: Fetch the iframe page to get the vixcloud embed URL
        iframe_url = f"{BASE_URL}/it/iframe/{title_id}?episode_id={episode_id}"
        resp_html = self.session.get(
            iframe_url,
            headers={"User-Agent": USER_AGENT, "Referer": f"{BASE_URL}/it/watch/{title_id}"},
        )

        vix_match = re.search(r'src="(https://vixcloud\.co/embed[^"]+)"', resp_html.text)
        if not vix_match:
            raise Exception("Impossibile trovare l'embed vixcloud.co")

        vix_url = vix_match.group(1).replace("&amp;", "&")

        # Step 2: Fetch the vixcloud embed page to get playlist info
        resp_vix = self.session.get(
            vix_url,
            headers={"User-Agent": USER_AGENT, "Referer": f"{BASE_URL}/"},
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
        flat_params = "&".join(f"{k}={v[0]}" for k, v in params.items())
        sep = "&" if parsed.query else "?"
        m3u8_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}{sep}{flat_params}"

        return m3u8_url
