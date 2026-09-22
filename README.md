# SC Downloader

Scarica video da StreamingCommunity con ricerca integrata e interfaccia grafica.

## Funzionalita

- **Ricerca integrata**: Cerca titoli direttamente dall'app
- **Selettore episodi**: Scegli stagione e episodi da scaricare
- **Coda download**: Aggiungi piu episodi e scaricali in sequenza
- **Download parallelo**: video e audio di ogni episodio si scaricano contemporaneamente (poi uniti automaticamente)
- **Download 1080p**: Scarica in massima qualita disponibile

## Requisiti

- Python 3.10+
- ffmpeg (nel PATH di sistema)

## Installazione

```bash
pip install -r requirements.txt
```

## Uso

```bash
python main.py
# oppure, equivalentemente:
python -m sc_downloader
```

1. Scrivi il nome di un film o serie TV nella barra di ricerca
2. Seleziona il titolo dalla lista e clicca "Seleziona"
3. Scegli la stagione e seleziona gli episodi
4. Clicca "Aggiungi Selezionati alla Coda"
5. Scegli la cartella di output e clicca "Scarica Tutti"

## Note

- Il programma usa `curl_cffi` per bypassare il fingerprinting TLS di vixcloud.co
- I download vengono eseguiti tramite `yt-dlp` con `ffmpeg`; `pycryptodomex` e' necessaria per gli stream HLS criptati
- Ogni download completato viene registrato in `.sc_history.json` (non visibile nell'interfaccia)
- L'ultima cartella di destinazione usata e' salvata in `.sc_settings.json`
