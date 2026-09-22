import os

# Radice del repository (una cartella sopra il package), dove vivono anche
# .sc_settings.json e .sc_debug.log, coerente con il comportamento storico
# dello script quando era un file singolo.
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BASE_URL = "https://streamingcommunityz.tax"
SETTINGS_FILE = os.path.join(ROOT_DIR, ".sc_settings.json")
DEBUG_LOG_FILE = os.path.join(ROOT_DIR, ".sc_debug.log")
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
