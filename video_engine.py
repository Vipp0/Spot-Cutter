"""
video_engine.py — Motore di elaborazione video (FFmpeg + yt-dlp)
Nessuna dipendenza da Flet: riceve dati, esegue operazioni, comunica
il progresso tramite callback asincrone.

Importa in main.py con:  from video_engine import VideoEngine
"""

import asyncio
import os
import re
import sys
import shutil
import subprocess
import time
import json
from typing import Callable, Awaitable, Any, cast

def get_ytdlp_path() -> str:
    """Compatibilità — usa get_tool_path internamente."""
    return get_tool_path("yt-dlp")

# Importa le utility condivise
from utils import (
    get_seconds, get_unique_filename, get_video_duration,
    safe_kill_process, ESTENSIONI_VIDEO, TEMP_MASTER_FILE,
    get_tool_path
)

# Tipo per le callback di progresso: funzione async che accetta (messaggio, colore)
LogCallback      = Callable[[str, str], Awaitable[None]]
ProgressCallback = Callable[[float, str], Awaitable[None]]  # (valore 0.0-1.0, label)


class VideoEngine:
    """
    Gestisce tutta la logica pesante: creazione master, blackdetect, taglio segmenti.
    Non sa nulla di Flet — comunica con main.py solo tramite callback.

    Uso tipico in main.py:
        engine = VideoEngine(log_cb=write_log, progress_cb=update_progress)
        await engine.process_all(queue_snapshot, state, settings)
    """

    def __init__(
        self,
        log_cb:      LogCallback,
        progress_cb: ProgressCallback,
    ):
        """
        Parametri:
            log_cb:      async def log(msg: str, color: str) — scrive nel log UI
            progress_cb: async def progress(value: float, label: str) — aggiorna la barra
        """
        self.log      = log_cb
        self.progress = progress_cb
        self._current_proc = None
        self._running = True   # verrà sincronizzato con state["running"]

        self.ytdlp_bin  = get_ytdlp_path()
        self.ffmpeg_bin = get_tool_path("ffmpeg")
        self.ffprobe_bin = get_tool_path("ffprobe")

    async def update_ytdlp(self):
        """Aggiorna il binario yt-dlp.exe direttamente usando il comando ufficiale"""
        await self.log(f"Controllo aggiornamenti per yt-dlp...", "cyan")
        
        try:
            # Comando: yt-dlp.exe --update
            # Usiamo asyncio per non bloccare la UI
            c_flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            process = await asyncio.create_subprocess_exec(
                self.ytdlp_bin, "--update",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=c_flags
            )
            self._current_proc = process
            stdout, stderr = await process.communicate()
            
            output = stdout.decode().strip()
            if "is up to date" in output:
                await self.log("✨ yt-dlp è già all'ultima versione disponibile.", "green")
            elif "Updated" in output:
                # Estraiamo la versione se presente, altrimenti messaggio generico
                version_match = re.search(r"stable@(\d{4}\.\d{2}\.\d{2})", output)
                v_str = f" alla versione {version_match.group(1)}" if version_match else ""
                await self.log(f"✅ Aggiornamento riuscito{v_str}! Ora sei al passo con gli ultimi cambiamenti di YouTube.", "green")
            else:
                await self.log("✅ Controllo aggiornamenti completato.", "green")
                
        except Exception as e:
            await self.log(f"Impossibile aggiornare yt-dlp: {str(e)}", "orange")

    # ── METODO PRINCIPALE ─────────────────────────────────────────────────
    async def process_all(self, queue_snapshot: list, state: dict, settings: tuple, status_cb=None, global_progress_cb=None) -> bool:
        """
        Elabora tutti i video nella coda.
        
        Parametri:
            queue_snapshot: lista di tuple (video, txt, anno_manuale)
            state:          dizionario di stato dell'app (per leggere running/current_dir)
            settings:       tupla (crf, cusc_i, cusc_f, toll, bth, bdur)

        Ritorna True se l'elaborazione è completata, False se interrotta.
        """
        v_crf, v_cusc_i, v_cusc_f, v_toll, v_bth, v_bdur = settings
        c_flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        cut_times = []
        completati = 0
        session_log = []   # raccoglie i risultati per il report finale

        total_videos = len(queue_snapshot)

        for idx, (vid, txt, m_year) in enumerate(queue_snapshot):
            # --- AGGIORNAMENTO PROGRESSO GLOBALE (v0.86) ---
            if global_progress_cb:
                await global_progress_cb(idx, total_videos)
            # Controlla interruzione ad ogni video
            if not state["running"]: 
                # 🔵 NOTIFICA INTERRUZIONE (Se l'utente preme stop)
                if status_cb:
                    await status_cb(idx, "🛑 Interrotto", "orange")
                break 

            if not txt:
                continue

            # --- LOGICA DI INIZIO VIDEO ---
            # 🔵 NOTIFICA INIZIO (Diventa BLU nella lista)
            if status_cb:
                await status_cb(idx, "⏳ In lavorazione...", "#2196F3")

            video_path_completo = os.path.join(state["current_dir"], vid)

            from utils import extract_date_info

            # extract_date_info ora ritorna (data_GG-MM-AAAA, anno_AAAA, colore)
            # m_year può essere una data completa "GG-MM-AAAA" inserita manualmente
            data_estratta, anno_estratto, colore_data = extract_date_info(vid)

            # Se l'utente ha inserito una data manuale, la usiamo
            # altrimenti usiamo quella estratta dal nome file
            if m_year:
                # m_year è nel formato "GG-MM-AAAA" (come lo salva DateEditorDialog)
                data_finale = m_year
                # Estrae l'anno dall'ultima parte della data manuale
                parti = m_year.split("-")
                final_year = parti[-1] if len(parti) == 3 else anno_estratto
            else:
                data_finale = data_estratta   # es. "04-12-1984"
                final_year  = anno_estratto   # es. "1984"

            # Tag per il nome file: " [04-12-1984]" o vuoto se data sconosciuta
            data_tag = f" [{data_finale}]" if data_finale else ""

            await self.log(f"🎬 Elaborazione: {vid}...", "blue")
            if colore_data == "orange":
                await self.log(f"⚠️ Data in {vid} potrebbe essere ambigua, verificare.", "orange")
            duration = get_video_duration(video_path_completo)
            # È meglio crearlo dentro la cartella dei video, non dove sta lo script
            master_dir = os.path.join(state["current_dir"], "Master_Temp")
            os.makedirs(master_dir, exist_ok=True)
            master = os.path.join(master_dir, f"MASTER_{os.path.splitext(vid)[0]}.mp4")

            # Pulizia master precedente rimasto da elaborazione interrotta
            if os.path.exists(master):
                try:
                    os.remove(master)
                    await self.log(f"🧹 Master precedente rimosso: {os.path.basename(master)}", "grey")
                except Exception as e:
                    await self.log(f"⚠️ Impossibile rimuovere master precedente: {e}", "orange")
            # ----------------------------------------------

            # ── 1. CREA MASTER ────────────────────────────────────────────
            ok = await self._create_master(video_path_completo, master, duration, state, c_flags)
            if not ok:
                # Se fallisce la creazione del master, segniamo l'errore
                if status_cb:
                    await status_cb(idx, "❌ Errore Master", "red")
                continue
            
            if not state["running"]:
                if status_cb:
                    await status_cb(idx, "🛑 Interrotto", "orange")
                break

            # ── 2. BLACKDETECT ────────────────────────────────────────────
            b_starts, b_ends, s_starts, s_ends = await self._detect_blacks(
                master, v_bth, v_bdur, c_flags,
                silence_thresh=state.get("silence_thresh", "-35dB"),
                silence_dur=state.get("silence_dur", "0.1")
            )

            # ── 3. LEGGI SPOT DAL TXT ─────────────────────────────────────
            # NEW: Costruiamo il percorso assoluto usando la cartella corrente
            txt_path_completo = os.path.join(state["current_dir"], txt)
            spot_list = self._read_spot_list(txt_path_completo)
            if spot_list is None:
                await self.log(f"⚠️ Impossibile leggere {txt}, salto video.", "orange")
                if status_cb:
                    await status_cb(idx, "⚠️ Errore TXT", "orange")
                continue
            await self.log(f"✅ Trovati {len(spot_list)} segmenti in {txt}.", "white")

            # ── 4. CALCOLA TUTTI I JOB DI TAGLIO ─────────────────────────
            # Prima costruiamo la lista completa dei job (tempi + nomi + path)
            # senza eseguire ancora nulla. Questo ci permette di lanciare
            # più tagli in parallelo nel passo successivo.
            cut_jobs = []
            results  = []
            tagli_riusciti = 0
            for i, spot in enumerate(spot_list, 1):
                t_s    = spot["t"]
                name_r = spot["n"]
                name_c = re.sub(r'[\\/*?:"<>|]', "", name_r)
                name_c = "Sconosciuto" if not name_c else name_c[:100]

                near_s = min(b_ends, key=lambda x: abs(x - t_s)) if b_ends else t_s
                # Silencedetect: se c'è un silenzio vicino al nero, affina il punto di inizio
                if s_ends:
                    near_s_sil = min(s_ends, key=lambda x: abs(x - t_s))
                    if abs(near_s_sil - t_s) <= v_toll and abs(near_s_sil - near_s) <= v_toll:
                        near_s = (near_s + near_s_sil) / 2  # media tra nero e silenzio
                r_s    = (max(0.0, near_s - v_cusc_i)
                          if abs(near_s - t_s) <= v_toll
                          else max(0.0, t_s - v_cusc_i))

                if i < len(spot_list):
                    t_e_t  = spot_list[i]["t"]
                    near_e = min(b_starts, key=lambda x: abs(x - t_e_t)) if b_starts else t_e_t
                    # Silencedetect: se c'è un silenzio vicino al nero, affina il punto di fine
                    if s_starts:
                        near_e_sil = min(s_starts, key=lambda x: abs(x - t_e_t))
                        if abs(near_e_sil - t_e_t) <= v_toll and abs(near_e_sil - near_e) <= v_toll:
                            near_e = (near_e + near_e_sil) / 2  # media tra nero e silenzio
                    r_e    = near_e + v_cusc_f if abs(near_e - t_e_t) <= v_toll else t_e_t
                else:
                    if duration and duration > r_s:
                        r_e = duration
                    else:
                        r_e = r_s + 60

                d_cat, k, l_col = self._categorize(name_r)
                base_libreria   = state.get("work_dir", state["current_dir"])
                target_p        = (os.path.join(base_libreria, final_year, d_cat)
                                   if d_cat
                                   else os.path.join(base_libreria, final_year))
                os.makedirs(target_p, exist_ok=True)

                nome_base  = os.path.splitext(name_c)[0]
                channel    = self._extract_channel(vid)
                # Aggiunge il canale solo se non è già presente nel nome dello spot
                if channel and channel.lower() not in nome_base.lower():
                    canale_tag = f" - {channel}"
                else:
                    canale_tag = ""
                nome_finale = f"{nome_base}{canale_tag}{data_tag}"
                out_f      = get_unique_filename(target_p, nome_finale, ext=".mkv")

                cut_jobs.append({
                    "idx_spot": i,
                    "r_s": r_s, "r_e": r_e,
                    "out_f": out_f, "k": k, "l_col": l_col,
                })

            # ── 5. TAGLIA IN BATCH PARALLELI ─────────────────────────────
            # Il parallelismo qui è sicuro perché i tagli sono semplici copie
            # di stream (nessuna ricodifica pesante): FFmpeg legge dal master
            # già su disco e scrive file separati — nessuna race condition.
            #
            # Quanti tagli in parallelo?
            # Usiamo metà dei core logici del sistema, con minimo 1 e massimo 6.
            # Metà perché FFmpeg usa già internamente più thread, e vogliamo
            # lasciare risorse libere al resto del sistema.
            # Esempi:
            #   i5-8400  (6 core /  6 thread) → 3 tagli paralleli
            #   5900X    (12 core / 24 thread) → 6 tagli paralleli  (cap 6)
            #   i3-8100  (4 core /  4 thread) → 2 tagli paralleli
            logical_cores = os.cpu_count() or 2
            # Se l'utente ha impostato un valore manuale nelle impostazioni lo usa,
            # altrimenti calcola automaticamente: metà core, min 1, max 12
            manual_cap = int(state.get("parallel_cuts", 0))
            if manual_cap > 0:
                parallel_cuts = manual_cap
                await self.log(
                    f"⚡ Taglio parallelo: {parallel_cuts} processi (impostazione manuale)",
                    "grey"
                )
            else:
                parallel_cuts = max(1, min(12, logical_cores // 2))
                await self.log(
                    f"⚡ Taglio parallelo: {parallel_cuts} processi "
                    f"({logical_cores} core logici rilevati, auto)",
                    "grey"
                )

            total_jobs  = len(cut_jobs)
            done_count  = 0

            # Suddivide la lista in batch di dimensione parallel_cuts
            for batch_start in range(0, total_jobs, parallel_cuts):
                if not state["running"]:
                    await self.log("🛑 Interruzione durante taglio spot", "orange")
                    break

                batch = cut_jobs[batch_start: batch_start + parallel_cuts]

                # Aggiorna la progress bar mostrando il range del batch
                first_n = batch[0]["idx_spot"]
                last_n  = batch[-1]["idx_spot"]
                if not cut_times:
                    label = (f"Taglio {first_n}-{last_n}/{total_jobs} "
                             f"({len(batch)} paralleli) — calcolo ETA...")
                else:
                    remaining_batches = (total_jobs - done_count) / parallel_cuts
                    avg = sum(cut_times) / len(cut_times)
                    em, es = divmod(int(avg * remaining_batches), 60)
                    label = (f"Taglio {first_n}-{last_n}/{total_jobs} "
                             f"({len(batch)} paralleli) — ~{em}m {es}s")
                await self.progress(done_count / total_jobs, label)

                # Azzera results per questo batch — evita di usare
                # i risultati del batch precedente se gather non viene chiamato
                results = []

                # Lancia tutti i tagli del batch in contemporanea
                batch_start_t = time.time()

                # Lista dei processi attivi nel batch corrente,
                # Usata da Stop per killarli tutti, non solo l'ultimo
                active_procs = []

                async def _run_one(job):
                    """Esegue un singolo taglio e ritorna (job, esito)."""
                    ok = await self._cut_segment(
                        master, job["r_s"], job["r_e"],
                        v_crf, job["out_f"], state, c_flags,
                        proc_list=active_procs
                    )
                    return job, ok

                results = await asyncio.gather(
                    *[_run_one(j) for j in batch],
                    return_exceptions=False
                )

                batch_elapsed = time.time() - batch_start_t
                # Il tempo medio per spot dentro il batch vale solo se il
                # batch era pieno (altrimenti l'ETA sarebbe distorta).
                if len(batch) == parallel_cuts:
                    cut_times.append(batch_elapsed)

                # Processa i risultati nell'ordine in cui erano nella lista
                for job, ok_cut in results:
                    done_count += 1
                    if ok_cut and state["running"]:
                        tagli_riusciti += 1
                        state["stats_counts"].setdefault(job["k"], 0)
                        state["stats_counts"][job["k"]] += 1
                        await self.log(
                            f"Tagliato {job['idx_spot']}/{total_jobs}: "
                            f"{os.path.basename(job['out_f'])}",
                            job["l_col"]
                        )
                        if "update_stats_cb" in state and state["update_stats_cb"]:
                            await state["update_stats_cb"]()

            # ── 5. PULIZIA E SPOSTAMENTO ──────────────────────────────────
            if os.path.exists(master):
                try:
                    os.remove(master)
                except Exception:
                    pass
            # Rimuove la cartella Master_Temp solo se è rimasta vuota
            if os.path.exists(master_dir):
                try:
                    os.rmdir(master_dir)
                except Exception:
                    pass

            if state["running"]:
                # tagli_riusciti è già accumulato batch per batch nel loop sopra, quindi qui è aggiornato con il totale reale dei tagli riusciti.

                if tagli_riusciti == 0:
                    await self.log(
                        f"⚠️ {os.path.basename(video_path_completo)} — nessun taglio riuscito, "
                        f"controlla i permessi della cartella di destinazione.", "red"
                    )
                    if status_cb:
                        await status_cb(idx, "❌ Nessun taglio", "#FF3B30")
                else:
                    # Scrivi nello storico solo se almeno un taglio è riuscito
                    self._write_storico(
                        storico_path = os.path.join(
                            state.get("work_dir", state["current_dir"]), "storico.json"
                        ),
                        vid          = vid,
                        n_spot       = tagli_riusciti,
                        canale       = self._extract_channel(vid),
                        anno         = final_year,
                    )

                    if tagli_riusciti < len(cut_jobs):
                        await self.log(
                            f"⚠️ {os.path.basename(video_path_completo)} — "
                            f"{tagli_riusciti}/{len(cut_jobs)} tagli riusciti.", "orange"
                        )
                        if status_cb:
                            await status_cb(idx, f"⚠️ {tagli_riusciti}/{len(cut_jobs)} tagli", "#FF9500")
                        session_log.append(
                            f"  ⚠️ {os.path.basename(video_path_completo)} — "
                            f"{tagli_riusciti}/{len(cut_jobs)} tagli"
                        )
                    else:
                        if status_cb:
                            await status_cb(idx, "✅ Completato", "#4CAF50")
                        await self.log(
                            f"✅ {os.path.basename(video_path_completo)} elaborato "
                            f"({tagli_riusciti} tagli).", "green"
                        )
                        session_log.append(
                            f"  ✅ {os.path.basename(video_path_completo)} — "
                            f"{tagli_riusciti} tagli"
                        )
                    completati += 1

        # --- AGGIORNAMENTO PROGRESSO GLOBALE (v0.86) ---
        if global_progress_cb and state.get("running", True):
            await global_progress_cb(total_videos, total_videos)

        # Report sessione nel log
        if session_log:
            await self.log("─" * 40, "grey")
            await self.log(f"📋 VIDEO ELABORATI IN QUESTA SESSIONE ({completati}):", "cyan")
            for entry in session_log:
                await self.log(entry, "white")
            await self.log("─" * 40, "grey")

        return state.get("running", True)
    
    @staticmethod
    def _write_storico(storico_path: str, vid: str, n_spot: int, canale: str, anno: str):
        """Aggiunge una voce al file storico.json nella Libreria Spot."""
        try:
            storico = {}
            if os.path.exists(storico_path):
                with open(storico_path, "r", encoding="utf-8") as f:
                    storico = json.load(f)
            storico[vid] = {
                "data_elaborazione": __import__("datetime").datetime.now().strftime("%d-%m-%Y %H:%M"),
                "n_spot":  n_spot,
                "canale":  canale,
                "anno":    anno,
            }
            with open(storico_path, "w", encoding="utf-8") as f:
                json.dump(storico, f, indent=2, ensure_ascii=False)
        except Exception as e:
            pass  # Lo storico è opzionale — non blocchiamo l'elaborazione

    async def _create_master(self, vid, master, duration, state, c_flags) -> bool:
        # Assicuriamoci che la cartella di destinazione del master esista
        master_dir = os.path.dirname(master)
        if master_dir and not os.path.exists(master_dir):
            os.makedirs(master_dir, exist_ok=True)

        cmd = [get_tool_path('ffmpeg'), '-y', '-stats', '-i', vid,
               '-c:v', 'libx264', '-crf', '18', '-g', '1',
               '-c:a', 'copy', master]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                creationflags=c_flags
            )
            self._current_proc = proc
            start = time.time()
            timeout = 3600
            
            last_stderr_lines = [] # Memorizziamo le ultime righe per il debug
            
            while True:
                # Controlliamo se il processo è finito
                if proc.returncode is not None:
                    break
                
                if not state["running"]:
                    await self.log(f"🛑 Interruzione durante master di {vid}", "orange")
                    await safe_kill_process(proc)
                    return False

                if time.time() - start > timeout:
                    await self.log(f"⏱️ Timeout creazione master per {vid}", "red")
                    await safe_kill_process(proc)
                    return False

                if proc.stderr is not None:
                    try:
                        # Leggiamo un chunk invece di readline()
                        # FFmpeg usa \r per sovrascrivere la riga di progresso,
                        # quindi readline() aspetta \n che non arriva mai e blocca.
                        chunk = await asyncio.wait_for(
                            proc.stderr.read(512),
                            timeout=0.5
                        )
                        if not chunk:
                            break

                        # Splittiamo su \r e \n per gestire entrambi i formati
                        text = chunk.decode(errors='ignore')
                        parts = re.split(r'[\r\n]+', text)

                        for part in parts:
                            part = part.strip()
                            if part:
                                # Memorizziamo le ultime righe per il debug in caso di errore
                                last_stderr_lines.append(part)
                                if len(last_stderr_lines) > 15:
                                    last_stderr_lines.pop(0)
                                    
                            if "time=" in part and duration > 0:
                                tm = re.search(r"time=(\d{2}:\d{2}:\d{2}.\d{2})", part)
                                if tm:
                                    current_ts = get_seconds(tm.group(1))
                                    perc = min(0.99, current_ts / duration)
                                    await self.progress(perc, f"Analisi Master: {int(perc*100)}%")

                    except asyncio.TimeoutError:
                        continue
                    except Exception as e:
                        await self.log(f"⚠️ Errore lettura log: {e}", "orange")
                        break
                else:
                    break

            await proc.wait()
            self._current_proc = None

            if not os.path.exists(master) or proc.returncode != 0:
                # RECUPERO ERRORE REALE
                error_msg = "\n".join(last_stderr_lines)
                await self.log(f"❌ Errore FFmpeg: {error_msg}", "red")
                await self.log(f"❌ Master non creato (Exit Code: {proc.returncode})", "red")
                return False

            return True

        except Exception as e:
            await self.log(f"🚨 Errore critico creazione master: {e}", "red")
            return False
        
    # ── BLACKDETECT STANDALONE (per dialog tagli manuali) ─────────────────
    async def detect_blacks_standalone(self, video_path: str, bth: str, bdur: str) -> list[float]:
        """
        Analizza un file video originale con blackdetect.
        Ritorna la lista dei black_start (inizio di ogni nero) come float.
        Usato dal dialog di taglio manuale — non richiede il master.
        """
        c_flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        cmd = [get_tool_path('ffmpeg'), '-y', '-i', video_path,
               '-vf', f"blackdetect=d={bdur}:pix_th={bth}",
               '-an', '-f', 'null', '-']
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                creationflags=c_flags
            )
            _, stderr_b = await proc.communicate()
            out = stderr_b.decode(errors='ignore')
            b_starts = [float(x) for x in re.findall(r"black_start:([\d.]+)", out)]
            return b_starts
        except Exception as e:
            await self.log(f"⚠️ Errore blackdetect standalone: {e}", "red")
            return []

    # ── BLACKDETECT ───────────────────────────────────────────────────────
    async def _detect_blacks(self, master, bth, bdur, c_flags,
                             silence_thresh="-35dB", silence_dur="0.1") -> tuple:
        """
        Analizza il master con blackdetect + silencedetect in un unico passaggio.
        Ritorna (b_starts, b_ends, s_starts, s_ends) come liste di float.
        s_starts/s_ends sono i punti di silenzio audio rilevati.
        """
        await self.log("Ricerca stacchi neri e silenzi...", "grey")
        cmd = [get_tool_path('ffmpeg'), '-y', '-i', master,
               '-vf', f"blackdetect=d={bdur}:pix_th={bth}",
               '-af', f"silencedetect=n={silence_thresh}:d={silence_dur}",
               '-f', 'null', '-']
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                creationflags=c_flags
            )
            _, stderr_b = await proc.communicate()
            out = stderr_b.decode(errors='ignore')
            b_starts = [float(x) for x in re.findall(r"black_start:([\d.]+)", out)]
            b_ends   = [float(x) for x in re.findall(r"black_end:([\d.]+)",   out)]
            s_starts = [float(x) for x in re.findall(r"silence_start:([\d.]+)", out)]
            s_ends   = [float(x) for x in re.findall(r"silence_end\s*:\s*([\d.]+)", out)]
            await self.log(f"Trovati {len(b_starts)} neri, {len(s_starts)} silenzi.", "grey")
            return b_starts, b_ends, s_starts, s_ends
        except Exception as e:
            await self.log(f"⚠️ Errore analisi: {e}", "red")
            return [], [], [], []

    # ── LETTURA TXT ───────────────────────────────────────────────────────
    def _read_spot_list(self, txt_path) -> list | None:
        """
        Legge il file .txt degli spot e ritorna lista di dict {t, n}.
        Ritorna None se il file non è leggibile.
        """
        try:
            spot_list = []
            with open(txt_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if mm := re.search(r"(\d{2}:\d{2}(?::\d{2})?)\s*-\s*(.+)", line):
                        spot_list.append({
                            "t": get_seconds(mm.group(1)),
                            "n": mm.group(2).strip()
                        })
            return spot_list
        except Exception:
            return None

    async def _cut_segment(self, master, r_s, r_e, crf, out_f, state, c_flags,
                           proc_list: list | None = None) -> bool:
        """
        Taglia un singolo segmento dal master e lo salva in out_f.
        proc_list: lista condivisa dove registrare il processo attivo,
                   usata dai tagli paralleli per killarli tutti su Stop.
        Ritorna True se riuscito.
        """
        cmd = [
            get_tool_path('ffmpeg'), '-y', '-i', master,
            '-ss', f"{r_s:.2f}",
            '-t',  f"{max(0.5, r_e - r_s):.2f}",
            '-c:v', 'libx264', '-crf', str(crf), '-g', '50',
            '-c:a', 'copy', out_f
        ]
        try:
            p_cut = await asyncio.create_subprocess_exec(*cmd, creationflags=c_flags)
            # Registra il processo nella lista condivisa del batch (thread-safe per asyncio)
            if proc_list is not None:
                proc_list.append(p_cut)
            else:
                self._current_proc = p_cut

            timeout    = 3600
            start_time = time.time()

            while p_cut.returncode is None:
                if not state.get("running", True):
                    await self.log("🛑 Interruzione forzata FFmpeg...", "orange")
                    await safe_kill_process(p_cut)
                    return False
                await asyncio.sleep(0.1)
                if time.time() - start_time > timeout:
                    await self.log("⏱️ Timeout FFmpeg...", "red")
                    await safe_kill_process(p_cut)
                    return False

            await p_cut.wait()
            if proc_list is not None and p_cut in proc_list:
                proc_list.remove(p_cut)
            else:
                self._current_proc = None

            if p_cut.returncode != 0:
                await self.log(
                    f"⚠️ FFmpeg errore (code {p_cut.returncode}): {os.path.basename(out_f)}",
                    "red"
                )
                return False
            return True
        except Exception as e:
            await self.log(f"🚨 Errore critico FFmpeg: {e}", "red")
            if proc_list is None:
                self._current_proc = None
            return False
        
    # ── RILEVAMENTO CANALE ────────────────────────────────────────────────
    @staticmethod
    def _extract_channel(name_r: str) -> str:
        """
        Cerca il nome del canale nel titolo del file.
        Ritorna il nome canale formattato oppure "" se non trovato.
        """
        n = name_r.lower()
        channels = [
            # RAI
            (["raiuno", "rai uno", "rai 1", "rai1"],          "Rai 1"),
            (["raidue", "rai due", "rai 2", "rai2"],          "Rai 2"),
            (["raitre", "rai tre", "rai 3", "rai3"],          "Rai 3"),
            # Mediaset
            (["canale 5", "canale5"],                          "Canale 5"),
            (["retequattro", "rete 4", "rete4", "rete quattro"], "Rete 4"),
            (["italia 1", "italia1"],                          "Italia 1"),
            # Locali e altri
            (["antenna 3", "antenna3"],                        "Antenna 3"),
            (["tmc", "telemontecarlo"],                        "TMC"),
            (["odeon"],                                        "Odeon"),
            (["tva", "televisione delle alpi"],                "TVA"),
            (["fininvest"],                                    "Fininvest"),
            (["europ2", "europa 2"],                           "Europa 2"),
            (["videomusic"],                                   "VideoMusic"),
            (["italia 7", "italia7"],                          "Italia 7"),
            (["tele+", "tele +", "telepiù", "sky"],           "Sky/Tele+"),
        ]
        for keywords, label in channels:
            if any(k in n for k in keywords):
                return label
        return ""

    # ── CATEGORIZZAZIONE SPOT ─────────────────────────────────────────────
    @staticmethod
    def _categorize(name_r: str) -> tuple:
        """
        Ritorna (cartella_destinazione, chiave_stats, colore_log)
        """
        n = name_r.lower()

        # --- CATEGORIA FESTIVITÀ (Natale & Capodanno) ---
        # Usiamo radici per catturare singolari/plurali e varianti
        keywords_feste = [
            # Natale: Brand e Dolci
            "nataliz", "natale", "pandor", "panetton", 
            "bauli", "melegatti", "alemagna", "maina", 
            "paluani", "tartufon",
            
            # Capodanno e Festeggiamenti
            "capodanno", "vigilia", "brindisi", "spumant", 
            "cenon", "cin cin", "buon anno",
            
            # Termini generici ma sicuri
            "augur", "buone feste", "festività"
        ]
        
        if any(x in n for x in keywords_feste):
            return "Natale", "natale", "#FF3D00"
        # ---------------------------------
            
        if "annunc"     in n: return "Annunci",     "annunci",      "#FF85FF"
        if any(x in n for x in ["promo", "trailer"]): 
            return "Promo", "promo", "#F1C40F"
        if "bumper"     in n: return "Bumper",      "bumper",       "#00E5FF"
        if "cartell"    in n: return "Cartelli",    "cartelli",     "#E0E0E0"
        if "videosigl"  in n: return "Videosigle",  "videosigle",   "#BF94FF"
        
        if re.search(r'\btg\d*\b', n) or "telegiorn" in n:
            return "Telegiornali", "telegiornali", "#FFAB40"
            
        # Se non rientra in nessuna categoria, va nella cartella dell'anno senza sottocartella
        return "", "spot", "#2ECC71"

    # ── ESTRAZIONE INFO (Senza Download) ──────────────────────────────────
    async def get_url_info(self, url: str) -> dict | None:
        """
        Ritorna info sul link (se è playlist, quanti video, titolo).
        Usa self.ytdlp_bin (exe esterno) — funziona nell'EXE one-folder.
        NOTA: NO --no-playlist così rileva correttamente le playlist.
        """
        c_flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        cmd = [
            self.ytdlp_bin,
            "--dump-json",
            "--no-download",
            "--flat-playlist",   # elenca le entry senza scaricarle
            "--no-warnings",
            url                  # NO --no-playlist: vogliamo sapere se è playlist
        ]
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                creationflags=c_flags
            )
            stdout, _ = await process.communicate()

            if not stdout:
                return None

            # Ogni riga è un JSON separato (una per entry della playlist)
            lines = [l for l in stdout.decode(errors="replace").splitlines() if l.strip()]
            if not lines:
                return None

            first       = json.loads(lines[0])
            is_playlist = len(lines) > 1 or first.get("_type") == "playlist"

            return {
                "is_playlist": is_playlist,
                "count":       len(lines),
                "title":       first.get("title", "Video singolo")
            }
        except Exception as e:
            await self.log(f"⚠️ Errore get_url_info: {e}", "red")
            return None

    # ── DOWNLOAD YOUTUBE ──────────────────────────────────────────────────
    async def download_youtube(self, url: str, output_dir: str, state: dict,
                               generate_txt: bool = True) -> list[tuple[str, str]] | None:
        """
        Scarica tramite yt-dlp.exe esterno.
        Strategia: snapshot file prima/dopo per trovare cosa è stato scaricato.
        generate_txt=False: niente .txt (download diretto).
        """
        c_flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        archive = os.path.join(output_dir, "archive.txt")
        outtmpl = os.path.join(output_dir, "%(title)s.%(ext)s")

        # Snapshot pre-download: registra tutti i video già presenti
        def _snapshot():
            snap = {}
            try:
                for fname in os.listdir(output_dir):
                    if fname.lower().endswith(ESTENSIONI_VIDEO):
                        fp = os.path.join(output_dir, fname)
                        snap[fp] = os.path.getmtime(fp)
            except Exception:
                pass
            return snap

        files_before = _snapshot()

        cmd = [
            self.ytdlp_bin,
            "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "--no-playlist",
            "--download-archive", archive,
            "-o", outtmpl,
            "--no-warnings",
            "--no-check-certificates",
            "--progress",   # forza output % anche con stderr=PIPE (no TTY)
            "--newline",    # una riga per aggiornamento %
            "--write-description",
            url
        ]

        await self.log("⬇️ Avvio download YouTube...", "cyan")

        last_filepath = None
        logged_start  = False
        video_title   = "video"

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,  # yt-dlp manda tutto su stdout
                stderr=asyncio.subprocess.PIPE,  # teniamo aperto per sicurezza
                creationflags=c_flags
            )
            self._current_proc = process

            async def _read_progress():
                nonlocal logged_start, video_title
                if process.stdout is None:
                    return
                buf = b""
                while True:
                    chunk = await process.stdout.read(256)
                    if not chunk:
                        break
                    if not state.get("running", True):
                        break
                    buf += chunk
                    # Splitta su \r e \n — yt-dlp usa \r per sovrascrivere la riga
                    while b"\r" in buf or b"\n" in buf:
                        for sep in (b"\r", b"\n"):
                            if sep in buf:
                                line_b, buf = buf.split(sep, 1)
                                line = line_b.decode("utf-8", errors="replace").strip()
                                if not line:
                                    continue
                                if "Destination:" in line:
                                    # Cattura il nome file dalla riga "Destination: /path/NomeVideo.mp4"
                                    dest = line.split("Destination:")[-1].strip()
                                    base = os.path.splitext(os.path.basename(dest))[0]
                                    video_title = re.sub(r'\.\w+\d+$', '', base)
                                if "[download]" in line and "%" in line:
                                    if not logged_start:
                                        await self.log(f"⬇️ Download: {video_title}", "yellow")
                                        logged_start = True
                                    m = re.search(r"([\d.]+)%", line)
                                    if m:
                                        try:
                                            p = float(m.group(1)) / 100.0
                                            await self.progress(p, f"⬇️ {int(p * 100)}% — {video_title}")
                                        except ValueError:
                                            pass
                                break

            await _read_progress()
            await process.wait()
            self._current_proc = None

            if not state.get("running", True):
                await self.log("🛑 Download interrotto.", "orange")
                return None

            if process.returncode != 0:
                await self.log(f"⚠️ yt-dlp terminato con codice {process.returncode}.", "red")
                return None

            await self.progress(1.0, "Download completato.")
            await self.log("✅ Download completato.", "green")

            # Confronta snapshot: file nuovo = quello appena scaricato
            files_after = _snapshot()
            new_files = [fp for fp in files_after if fp not in files_before]

            if new_files:
                last_filepath = max(new_files, key=lambda fp: files_after[fp])
            else:
                # Nessun file nuovo = era gia in archivio
                existing = sorted(files_after.items(), key=lambda x: x[1], reverse=True)
                if existing:
                    last_filepath = existing[0][0]
                    await self.log("ℹ️ Video già scaricato, aggiunto alla coda.", "cyan")

            if not last_filepath:
                await self.log("⚠️ Nessun file trovato dopo il download.", "orange")
                return None

            vid_basename = os.path.basename(last_filepath)
            txt_basename = ""
            desc_path    = os.path.splitext(last_filepath)[0] + ".description"

            if generate_txt:
                desc = ""
                if os.path.exists(desc_path):
                    try:
                        with open(desc_path, "r", encoding="utf-8", errors="replace") as df:
                            desc = df.read()
                        os.remove(desc_path)
                    except Exception:
                        pass
                txt_lines = []
                for d_line in desc.splitlines():
                    m = re.search(r"(\d{1,2}:\d{2}(?::\d{2})?)\s*[-:]?\s*(.+)", d_line.strip())
                    if m and m.group(2).strip():
                        txt_lines.append(f"{m.group(1)} - {m.group(2).strip().strip('*_ ')}")
                if txt_lines:
                    txt_basename = os.path.splitext(vid_basename)[0] + ".txt"
                    with open(os.path.join(output_dir, txt_basename), "w", encoding="utf-8") as tf:
                        tf.write("\n".join(txt_lines))
                elif generate_txt:
                    await self.log("ℹ️ Nessun timestamp nella descrizione — TXT non generato.", "orange")
            else:
                if os.path.exists(desc_path):
                    try: os.remove(desc_path)
                    except Exception: pass

            processed_files = [(vid_basename, txt_basename)]
            await self.log(f"✅ Operazione conclusa: {len(processed_files)} video pronti.", "green")
            return processed_files

        except Exception as ex:
            self._current_proc = None
            await self.log(f"⚠️ Errore download YouTube: {ex}", "red")
            return None
