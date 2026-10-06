import os

# Radice del repository (una cartella sopra il package), dove vivono anche
# .sc_settings.json e .sc_debug.log, coerente con il comportamento storico
# dello script quando era un file singolo.
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from urllib.parse import urlsplit

# Il sito cambia dominio spesso (blocchi): il dominio attuale e' una variabile, non una costante.
# - SC_BASE_URL nell'ambiente lo sceglie all'avvio (serve solo se il vecchio dominio e' morto senza redirect);
# - follow_redirect() adotta da solo il nuovo dominio quando il vecchio risponde con un redirect (301 al
#   nuovo indirizzo, quello che fa il sito a ogni cambio); chi usa il pacchetto puo' salvarlo con
#   on_base_url_change() (il server lo tiene nel database, cosi' sopravvive ai riavvii).
DEFAULT_BASE_URL = "https://streamingcommunityz.promo"
_base_url = (os.environ.get("SC_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
_listeners = []


def base_url():
    """Dominio attuale del sito, es. https://streamingcommunityz.promo (senza / finale)."""
    return _base_url


def set_base_url(url):
    """Imposta il dominio del sito; avvisa chi si e' registrato con on_base_url_change() se cambia."""
    global _base_url
    url = url.rstrip("/")
    if url == _base_url:
        return
    _base_url = url
    for callback in list(_listeners):
        callback(url)


def on_base_url_change(callback):
    _listeners.append(callback)


def follow_redirect(requested_url, final_url):
    """Se una richiesta al dominio attuale e' finita (dopo i redirect) su un altro dominio, con la stessa
    sezione /it del sito, quello e' il nuovo indirizzo. Restituisce True se il dominio e' cambiato."""
    req, fin = urlsplit(requested_url), urlsplit(str(final_url or ""))
    current = urlsplit(_base_url)
    if req.hostname != current.hostname or not fin.hostname or fin.hostname == req.hostname:
        return False
    if fin.scheme != "https" or not fin.path.startswith("/it"):
        return False  # redirect verso una pagina qualsiasi (parcheggio, blocco): non e' il sito
    set_base_url(f"https://{fin.netloc}")
    return True

SETTINGS_FILE = os.path.join(ROOT_DIR, ".sc_settings.json")
# SC_DEBUG_LOG permette a chi usa il pacchetto come libreria (es. il server in Docker, dove ROOT_DIR
# cadrebbe dentro site-packages) di scegliere dove scrivere il log dei fallimenti.
DEBUG_LOG_FILE = os.environ.get("SC_DEBUG_LOG") or os.path.join(ROOT_DIR, ".sc_debug.log")
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
