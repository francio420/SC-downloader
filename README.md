# SC Downloader

Scarica video da StreamingCommunity con ricerca integrata e interfaccia grafica.

## Funzionalita

- **Ricerca integrata**: Cerca titoli direttamente dall'app, con griglia di locandine e filtri Serie/Film
- **Selettore episodi**: Scegli stagione e episodi da scaricare (con copertine, trame, selezione a intervallo)
- **Dashboard download**: anello di avanzamento, velocita' live con grafico, barre separate video/audio
- **Coda download**: Aggiungi piu episodi, con piu' episodi scaricati in parallelo (configurabile in Impostazioni)
- **Download parallelo**: video e audio di ogni episodio si scaricano contemporaneamente (poi uniti automaticamente)
- **Download 1080p**: Scarica in massima qualita disponibile

## Requisiti

- Python 3.10+
- ffmpeg (nel PATH di sistema)
- Pillow (installato da `requirements.txt`, serve per mostrare le locandine)

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

1. In **Scopri** scrivi il nome di una serie TV e premi Invio
2. Clicca sulla locandina del titolo
3. Scegli la stagione e clicca sugli episodi (Maiusc+clic per un intervallo, Ctrl+A per tutti)
4. Clicca "Aggiungi alla coda" oppure "Scarica ora"
5. Segui l'avanzamento nella sezione **Download**, dove puoi anche cambiare cartella

Nella sezione **Opzioni** puoi configurare la cartella, quanti episodi scaricare
in parallelo e quanti frammenti concorrenti usare per ogni stream video/audio.
Scorciatoie: Ctrl+F cerca, Ctrl+1/2/3 cambia sezione, Esc torna ai risultati.

## Note

- Il programma usa `curl_cffi` per bypassare il fingerprinting TLS di vixcloud.co
- I download vengono eseguiti tramite `yt-dlp` con `ffmpeg`; `pycryptodomex` e' necessaria per gli stream HLS criptati
- L'ultima cartella di destinazione usata e le impostazioni di download sono salvate in `.sc_settings.json`
- In caso di download fallito, i dettagli (comandi eseguiti e output completo) sono salvati in `.sc_debug.log`

## Disclaimer

Questo progetto è realizzato esclusivamente a scopo educativo e di studio
(scraping HTML, gestione di stream HLS, GUI Tkinter). Non è affiliato in alcun
modo con StreamingCommunity, vixcloud.co o i titolari dei contenuti, e non
ospita né distribuisce alcun contenuto.

L'utente è l'unico responsabile dell'uso che fa del software e del rispetto
delle leggi sul diritto d'autore vigenti nel proprio paese. L'autore non si
assume alcuna responsabilità per eventuali usi illeciti.

## Licenza

Distribuito con licenza MIT, vedi [LICENSE](LICENSE).
