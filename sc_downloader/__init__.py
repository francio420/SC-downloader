"""SC Downloader - StreamingCommunity Downloader con Ricerca Integrata."""

import sys

try:
    import curl_cffi  # noqa: F401  (verifica soltanto che sia installato)
except ImportError:
    print("Errore: curl_cffi non installato. Esegui: pip install curl_cffi")
    sys.exit(1)

__version__ = "1.0.0"
