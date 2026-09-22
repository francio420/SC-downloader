# SC Downloader

Scarica video da StreamingCommunity con ricerca integrata e interfaccia grafica.

## Funzionalita

- **Ricerca integrata**: Cerca titoli direttamente dall'app
- **Selettore episodi**: Scegli stagione e episodi da scaricare
- **Coda download**: Aggiungi piu episodi, con piu' episodi scaricati in parallelo (configurabile in Impostazioni)
- **Download parallelo**: video e audio di ogni episodio si scaricano contemporaneamente (poi uniti automaticamente)
- **Download 1080p**: Scarica in massima qualita disponibile

## Requisiti

- Python 3.10+
- ffmpeg (nel PATH di sistema)

## Installazione

```bash
pip install -r requirements.txt
```

### Windows (avvio rapido)

In alternativa, su Windows basta fare doppio click su `avvia.bat`: se mancano
Python o ffmpeg li installa da solo con `winget` (gia' incluso in Windows
10/11 aggiornati) e li aggiunge al PATH, poi crea l'ambiente virtuale,
installa le dipendenze e avvia il programma (nelle esecuzioni successive lo
avvia direttamente). Se `winget` non e' disponibile, mostra le istruzioni per
installarli manualmente.

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

Dal menu **Impostazioni** in alto puoi configurare quanti episodi scaricare in
parallelo e quanti frammenti concorrenti usare per ogni stream video/audio.

## Note

- Il programma usa `curl_cffi` per bypassare il fingerprinting TLS di vixcloud.co
- I download vengono eseguiti tramite `yt-dlp` con `ffmpeg`; `pycryptodomex` e' necessaria per gli stream HLS criptati
- L'ultima cartella di destinazione usata e le impostazioni di download sono salvate in `.sc_settings.json`
- In caso di download fallito, i dettagli (comandi eseguiti e output completo) sono salvati in `.sc_debug.log`
