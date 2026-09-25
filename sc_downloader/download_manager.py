import glob
import os
import re
import signal
import subprocess
import sys
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from .api import StreamingCommunityAPI
from .constants import DEBUG_LOG_FILE
from .scraper import ScrapeEngine

# ─── DownloadManager ─────────────────────────────────────────────────────────

IS_WINDOWS = os.name == "nt"


class DownloadManager:
    """Gestisce la coda di download con threading."""

    def __init__(self, output_folder, progress_callback=None, status_callback=None, finished_callback=None,
                 max_parallel_episodes=1, concurrent_fragments=4):
        self.output_folder = output_folder
        self.progress_callback = progress_callback or (lambda *a: None)
        self.status_callback = status_callback or (lambda *a: None)
        self.finished_callback = finished_callback or (lambda *a: None)
        self.max_parallel_episodes = max_parallel_episodes
        self.concurrent_fragments = concurrent_fragments
        self.queue = []
        self.current_index = -1
        self.is_downloading = False
        self._stop_flag = False
        self._current_processes = []
        self._processes_lock = threading.Lock()
        self.api = StreamingCommunityAPI()
        self.scrape = ScrapeEngine(session=self.api.session)

    def kill_current(self):
        """Termina immediatamente tutti i download in corso (fino a
        max_parallel_episodes episodi in parallelo, ognuno con video e audio
        scaricati a loro volta in parallelo, e i loro eventuali processi
        figli come ffmpeg), evitando che restino orfani in background."""
        self._stop_flag = True
        with self._processes_lock:
            processes = list(self._current_processes)
        for process in processes:
            if process and process.poll() is None:
                try:
                    if IS_WINDOWS:
                        # os.killpg non esiste su Windows: taskkill /T termina
                        # l'intero albero di processi (compresi eventuali figli
                        # come ffmpeg), equivalente a killpg su POSIX.
                        subprocess.run(
                            ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                            capture_output=True,
                        )
                    else:
                        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                except (ProcessLookupError, PermissionError, OSError):
                    process.kill()

    def add(self, item):
        """Aggiunge un elemento alla coda. Episodio: {title_name, title_id, season, episode, episode_id,
        episode_name, duration}; film: {kind: "movie", title_name, title_id, episode_id: None, year, duration}."""
        item["status"] = "in_coda"
        item["progress"] = 0
        item["video_progress"] = 0
        item["audio_progress"] = 0
        self.queue.append(item)

    def remove(self, index):
        if 0 <= index < len(self.queue):
            if self.queue[index]["status"] == "in_corso":
                # Non e' possibile fermare un solo episodio tra quelli in
                # parallelo senza toccare gli altri: rimuoverne uno attivo
                # interrompe l'intero batch, come per il pulsante "Interrompi".
                self._stop_flag = True
            self.queue.pop(index)
            if self.current_index >= len(self.queue):
                self.current_index = len(self.queue) - 1

    def clear(self):
        self._stop_flag = True
        self.queue.clear()
        self.current_index = -1

    def start_all(self):
        if self.is_downloading:
            return
        self.is_downloading = True
        self._stop_flag = False
        thread = threading.Thread(target=self._download_loop, daemon=True)
        thread.start()

    def _download_loop(self):
        # Congelati per l'intera durata di questo batch: cambiarli dal menu
        # Impostazioni mentre e' in corso un download si applica solo al
        # prossimo avvio, non a meta' di uno gia' partito.
        parallel_episodes = max(1, self.max_parallel_episodes)
        concurrent_fragments = self.concurrent_fragments

        pending = [item for item in self.queue if item["status"] != "completato"]

        def worker(item):
            if self._stop_flag:
                return
            item["status"] = "in_corso"
            self.status_callback(self._status_message())
            self.progress_callback(self._overall_progress())
            try:
                self._download_one(item, concurrent_fragments)
                if self._stop_flag:
                    # Interrotto dall'utente: non e' completato, va ripreso
                    # in un successivo avvio invece di essere segnato come
                    # scaricato con successo.
                    item["status"] = "in_coda"
                    item["progress"] = 0
                    item["size_mb"] = 0
                else:
                    item["status"] = "completato"
                    item["progress"] = 100
            except Exception as e:
                item["status"] = "errore"
                item["error"] = str(e)
                self.status_callback(f"Errore: {e}")
            self.status_callback(self._status_message())
            self.progress_callback(self._overall_progress())

        # Fino a parallel_episodes episodi scaricati contemporaneamente;
        # ognuno a sua volta scarica video e audio in parallelo tra loro.
        with ThreadPoolExecutor(max_workers=parallel_episodes) as pool:
            list(pool.map(worker, pending))

        self.is_downloading = False
        self.current_index = -1
        self.finished_callback()

    def _status_message(self):
        active = [i for i in self.queue if i["status"] == "in_corso"]
        done = sum(1 for i in self.queue if i["status"] == "completato")
        if not active:
            return f"{done}/{len(self.queue)} completati"
        titles = ", ".join(self.item_label(i) for i in active)
        return f"In corso ({len(active)}): {titles} — {done}/{len(self.queue)} completati"

    def _overall_progress(self):
        """Percentuale complessiva su tutti gli elementi in coda."""
        if not self.queue:
            return 0
        return sum(i.get("progress", 0) for i in self.queue) / len(self.queue)

    @staticmethod
    def item_label(item):
        """"Serie S01E02" per gli episodi, "Film (2010)" per i film."""
        if item.get("kind") == "movie":
            return f"{item['title_name']} ({item['year']})" if item.get("year") else item["title_name"]
        return f"{item['title_name']} S{item.get('season', 0):02d}E{item.get('episode', 0):02d}"

    @staticmethod
    def _resolve_dir(parent, name):
        """Riusa una sottocartella di 'parent' gia' esistente con lo stesso nome
        (case-insensitive) invece di crearne una nuova; altrimenti la crea."""
        try:
            for entry in os.listdir(parent):
                if entry.lower() == name.lower() and os.path.isdir(os.path.join(parent, entry)):
                    return os.path.join(parent, entry)
        except OSError:
            pass
        path = os.path.join(parent, name)
        os.makedirs(path, exist_ok=True)
        return path

    @staticmethod
    def _log_failure(item, cmds, outputs, extra=""):
        """Scrive un log dettagliato di un download fallito (comandi eseguiti,
        codici di uscita, output completo di yt-dlp/ffmpeg) in DEBUG_LOG_FILE,
        cosi' l'errore si puo' diagnosticare senza doverlo riprodurre a mano."""
        try:
            with open(DEBUG_LOG_FILE, "a", encoding="utf-8") as f:
                f.write("=" * 80 + "\n")
                f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - "
                        f"{DownloadManager.item_label(item)}\n")
                for label, cmd in cmds.items():
                    f.write(f"\n[{label}] comando:\n  {' '.join(cmd)}\n")
                for label, output in outputs.items():
                    f.write(f"\n[{label}] output:\n{output}\n")
                if extra:
                    f.write(f"\n{extra}\n")
                f.write("=" * 80 + "\n\n")
        except OSError:
            pass

    def _download_one(self, item, concurrent_fragments):
        m3u8_url = self.scrape.build_m3u8(item["title_id"], item["episode_id"])
        # Di solito video e audio sono rendition HLS separate, ma per alcuni
        # titoli il CDN offre solo stream gia' muxati: li' "bestvideo"/
        # "bestaudio" non trovano nulla e si scarica un unico stream "best".
        muxed = not self.scrape.has_separate_audio(m3u8_url)

        if item.get("kind") == "movie":
            # Film: <output>/Film/<Titolo (Anno)>.mp4, tutti insieme e separati
            # dalla cartella "Serie TV".
            filename = re.sub(r'[<>:"/\\|?*]', '_', self.item_label(item))
            dest_dir = self._resolve_dir(self.output_folder, "Film")
        else:
            safe_name = re.sub(r'[<>:"/\\|?*]', '_', item["title_name"])
            filename = f"{safe_name}_S{item['season']:02d}E{item['episode']:02d}"
            # Cartella <output>/Serie TV/<Serie>/<Stagione NN>/, sempre, cosi' la struttura
            # resta coerente anche scaricando le stagioni in sessioni separate
            # (altrimenti scaricare una stagione alla volta non creerebbe mai la
            # sottocartella, mescolando le stagioni nella cartella della serie).
            # Riusa cartelle gia' esistenti (case-insensitive) invece di duplicarle.
            dest_dir = self._resolve_dir(self.output_folder, "Serie TV")
            dest_dir = self._resolve_dir(dest_dir, safe_name)
            dest_dir = self._resolve_dir(dest_dir, f"Stagione {item['season']:02d}")
        item["filename"] = filename

        def disk_size_mb():
            """Somma la dimensione reale su disco dei file di questo episodio
            (i .part di video e audio in scaricamento, o il file finale dopo
            il merge). E' l'unica fonte di verita' per il peso: niente stime
            "~" che possono sovra/sottostimare il totale."""
            total = 0
            for path in glob.glob(os.path.join(dest_dir, filename + "*")):
                try:
                    total += os.path.getsize(path)
                except OSError:
                    pass
            return total / (1024 * 1024)

        base_args = [
            sys.executable, "-u", "-m", "yt_dlp",
            "--newline",
            "--referer", "https://vixcloud.co/",
            "--add-header", "Origin:https://vixcloud.co",
            "--impersonate", "chrome",
            "--hls-prefer-native",
            "--concurrent-fragments", str(concurrent_fragments),
        ]

        popen_kwargs = dict(
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            encoding="utf-8", errors="replace", bufsize=1,
        )
        if IS_WINDOWS:
            # start_new_session (setsid) e' POSIX-only; su Windows un nuovo
            # gruppo di processi si crea cosi', ed e' quanto serve a
            # kill_current() per usare taskkill /T sull'intero albero.
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            popen_kwargs["start_new_session"] = True  # permette di terminare anche i figli (es. ffmpeg) come gruppo

        def cleanup_partial_files():
            """Rimuove eventuali file .video./.audio. parziali di un tentativo
            fallito. Necessario prima di ritentare: vixcloud puo' rispondere
            con errori 503/416 sotto carico (troppi frammenti/episodi
            paralleli), a quel punto yt-dlp esaurisce i suoi retry interni e
            puo' anche corrompere lo stato dei frammenti (.part-FragN "No
            such file"); ripartire da zero evita di ereditare quello stato,
            invece che lasciare video e audio a meta' scaricati e mai uniti
            nella cartella di destinazione."""
            for path in glob.glob(os.path.join(dest_dir, f"{filename}.video.*")):
                try:
                    os.remove(path)
                except OSError:
                    pass
            for path in glob.glob(os.path.join(dest_dir, f"{filename}.audio.*")):
                try:
                    os.remove(path)
                except OSError:
                    pass

        MAX_ATTEMPTS = 3
        streams = None
        cmds = {}
        last_outputs = {}
        last_video_rc = last_audio_rc = None

        for attempt in range(1, MAX_ATTEMPTS + 1):
            if self._stop_flag:
                return
            if attempt > 1:
                # Breve attesa prima di ritentare (non bloccante rispetto allo
                # stop): da' tempo al CDN di smettere di limitare le
                # connessioni invece di ripresentarsi identico subito dopo.
                for _ in range(20):
                    if self._stop_flag:
                        return
                    time.sleep(0.2)
                cleanup_partial_files()

            if muxed:
                streams = {
                    "video": {
                        "template": os.path.join(dest_dir, f"{filename}.video.%(ext)s"),
                        "format": "best",
                    },
                }
            else:
                streams = {
                    "video": {
                        "template": os.path.join(dest_dir, f"{filename}.video.%(ext)s"),
                        "format": "bestvideo",
                    },
                    "audio": {
                        "template": os.path.join(dest_dir, f"{filename}.audio.%(ext)s"),
                        # Alcuni titoli (spesso i film) hanno piu' tracce
                        # audio (es. inglese + italiano): si preferisce
                        # esplicitamente l'italiano invece di affidarsi a
                        # quale traccia yt-dlp considera "migliore".
                        "format": "bestaudio[language=ita]/bestaudio",
                    },
                }
            for key, s in streams.items():
                cmd = base_args + ["-f", s["format"], "-o", s["template"], m3u8_url]
                s["cmd"] = cmd
                # Ultime 200 righe di output per stream: se il download fallisce,
                # finiscono nel log di debug invece di andare perse.
                s["output"] = deque(maxlen=200)
                s["process"] = subprocess.Popen(cmd, **popen_kwargs)

            # Aggiunge (non sostituisce) alla lista condivisa: con piu' episodi in
            # parallelo, ognuno ha i propri processi ma la lista/il lock sono
            # condivisi a livello di DownloadManager per fermarli tutti insieme.
            with self._processes_lock:
                self._current_processes.extend(s["process"] for s in streams.values())

            def reader(key, process, output_buffer):
                """Legge l'output di un singolo stream (video o audio) e ne
                aggiorna la percentuale/velocita' in modo indipendente
                dall'altro, dato che ora scaricano in parallelo."""
                pkey = f"{key}_progress"
                last_callback = 0.0
                for line in process.stdout:
                    output_buffer.append(line)
                    if self._stop_flag:
                        break

                    updated = False

                    frag_match = re.search(r"\(frag\s+(\d+)/(\d+)\)", line)
                    if frag_match:
                        n, m = int(frag_match.group(1)), int(frag_match.group(2))
                        if m > 0:
                            item[pkey] = max(item.get(pkey, 0), min(100.0, n / m * 100))
                            updated = True
                    else:
                        pct_match = re.search(r"\[download\]\s+([\d.]+)%", line)
                        if pct_match:
                            item[pkey] = max(item.get(pkey, 0), min(100.0, float(pct_match.group(1))))
                            updated = True

                    speed_match = re.search(r"at\s+([\d.]+)\s*([KMG])i?B/s", line)
                    if speed_match:
                        value, unit = float(speed_match.group(1)), speed_match.group(2)
                        scale = {"K": 1 / 1024, "M": 1, "G": 1024}[unit]
                        item[f"{key}_speed_mb_s"] = value * scale
                        updated = True

                    # Fallback per il raro caso in cui yt-dlp deleghi questo
                    # stream a ffmpeg (es. crypto non disponibile): usa il tempo
                    # processato rispetto alla durata nota dell'episodio.
                    time_match = re.search(r"time=(\d+):(\d{2}):(\d{2})\.\d+", line)
                    if time_match and item.get("duration"):
                        h, m2, s2 = (int(g) for g in time_match.groups())
                        total_seconds = item["duration"] * 60
                        if total_seconds > 0:
                            candidate = min(99.0, (h * 3600 + m2 * 60 + s2) / total_seconds * 100)
                            item[pkey] = max(item.get(pkey, 0), candidate)
                            updated = True

                    # Con 8 frammenti concorrenti per stream le righe possono
                    # arrivare molto piu' spesso di quanto serva aggiornare la
                    # UI: limitiamo le notifiche a ~10/s per non intasare il
                    # loop di Tkinter (i valori restano comunque aggiornati,
                    # solo la notifica e' limitata).
                    if muxed:
                        # Un solo stream che contiene anche l'audio
                        item["audio_progress"] = item.get("video_progress", 0)
                    now = time.monotonic()
                    if updated and now - last_callback >= 0.1:
                        last_callback = now
                        item["progress"] = (item.get("video_progress", 0) + item.get("audio_progress", 0)) / 2
                        item["speed_mb_s"] = item.get("video_speed_mb_s", 0) + item.get("audio_speed_mb_s", 0)
                        self.progress_callback(self._overall_progress())

                process.wait()

            threads = [
                threading.Thread(target=reader, args=(key, s["process"], s["output"]), daemon=True)
                for key, s in streams.items()
            ]
            for t in threads:
                t.start()

            last_disk_check = 0.0
            while any(t.is_alive() for t in threads):
                if self._stop_flag:
                    self.kill_current()
                    break
                now = time.monotonic()
                if now - last_disk_check >= 1.0:
                    last_disk_check = now
                    size_mb = disk_size_mb()
                    if size_mb:
                        item["size_mb"] = size_mb
                        self.progress_callback(self._overall_progress())
                time.sleep(0.2)

            for t in threads:
                t.join(timeout=5)

            item["speed_mb_s"] = 0
            with self._processes_lock:
                for s in streams.values():
                    if s["process"] in self._current_processes:
                        self._current_processes.remove(s["process"])

            if self._stop_flag:
                return

            cmds = {key: s["cmd"] for key, s in streams.items()}
            last_video_rc = streams["video"]["process"].returncode
            last_audio_rc = streams["audio"]["process"].returncode if "audio" in streams else 0
            if last_video_rc == 0 and last_audio_rc == 0:
                break
            last_outputs = {key: "".join(s["output"]) for key, s in streams.items()}
        else:
            cleanup_partial_files()
            self._log_failure(
                item, cmds, last_outputs,
                extra=f"video_rc={last_video_rc} audio_rc={last_audio_rc} (dopo {MAX_ATTEMPTS} tentativi)",
            )
            raise Exception(
                f"yt-dlp fallito dopo {MAX_ATTEMPTS} tentativi "
                f"(video={last_video_rc}, audio={last_audio_rc}) - dettagli in {DEBUG_LOG_FILE}"
            )

        def pick_media_file(paths):
            """Sceglie il file multimediale vero scartando eventuali metadati
            temporanei di yt-dlp (es. .ytdl) che possono comparire nello
            stesso elenco insieme al file effettivo."""
            media = [p for p in paths if not p.endswith(".ytdl")]
            return media[0] if media else paths[0]

        video_files = glob.glob(os.path.join(dest_dir, f"{filename}.video.*"))
        audio_files = glob.glob(os.path.join(dest_dir, f"{filename}.audio.*"))
        if not video_files or (not muxed and not audio_files):
            outputs = {key: "".join(s["output"]) for key, s in streams.items()}
            self._log_failure(item, cmds, outputs, extra="File video o audio mancante dopo il download")
            raise Exception(f"File video o audio mancante dopo il download - dettagli in {DEBUG_LOG_FILE}")
        inputs = ["-i", pick_media_file(video_files)]
        if not muxed:
            inputs += ["-i", pick_media_file(audio_files)]

        # Con stream muxato e' un semplice remux in .mp4 del file unico
        final_path = os.path.join(dest_dir, f"{filename}.mp4")
        merge_cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                     *inputs, "-c", "copy", final_path]
        merge = subprocess.run(merge_cmd, capture_output=True, text=True)
        if merge.returncode != 0:
            self._log_failure(
                item, {**cmds, "ffmpeg merge": merge_cmd},
                {"ffmpeg merge (stdout+stderr)": merge.stdout + merge.stderr},
            )
            raise Exception(f"ffmpeg merge fallito - dettagli in {DEBUG_LOG_FILE}")

        # Rimuove tutti i file intermedi trovati (non solo quelli usati per il
        # merge), cosi' eventuali residui di tentativi precedenti per lo
        # stesso episodio non restano nella cartella insieme al file finale.
        for path in set(video_files + audio_files):
            try:
                os.remove(path)
            except OSError:
                pass

        size_mb = disk_size_mb()  # ora resta solo il file finale unito
        if size_mb:
            item["size_mb"] = size_mb
