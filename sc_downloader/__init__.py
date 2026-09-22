"""SC Downloader - StreamingCommunity Downloader con Ricerca Integrata."""

import importlib.util
import sys

# yt-dlp viene invocato con `sys.executable -m yt_dlp` (vedi
# download_manager.py): deve quindi essere installato nello STESSO
# interprete Python che sta eseguendo l'app, non genericamente sul sistema.
# Se l'app viene avviata con un Python diverso da quello del venv del
# progetto (es. python di sistema invece di .venv/bin/python), yt-dlp
# risulterebbe "importabile" qui ma introvabile al momento del download,
# con un errore criptico ("No module named yt_dlp") visibile solo nel log
# di debug. Controlliamo quindi qui, con un messaggio chiaro subito.
_MISSING = [
    name for name, module in [("curl_cffi", "curl_cffi"), ("yt-dlp", "yt_dlp"), ("pycryptodomex", "Cryptodome")]
    if importlib.util.find_spec(module) is None
]
if _MISSING:
    print(
        f"Errore: dipendenze mancanti nell'interprete {sys.executable}: {', '.join(_MISSING)}.\n"
        f"Esegui: {sys.executable} -m pip install -r requirements.txt\n"
        f"(o avvia l'app con ./.venv/bin/python main.py se hai un virtualenv nel progetto)"
    )
    sys.exit(1)

__version__ = "1.0.0"
