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
import statistics
import bisect
from typing import Callable, Awaitable, Any, cast

def get_ytdlp_path() -> str:
    """Compatibilità — usa get_tool_path internamente."""
    return get_tool_path("yt-dlp")

# Importa le utility condivise
from utils import (
    get_seconds, get_unique_filename, get_video_duration,
    safe_kill_process, kill_process_tree, ESTENSIONI_VIDEO, TEMP_MASTER_FILE,
    get_tool_path, RIGA_TXT, righe_txt_ignorate
)

# Saturazione media (0-~180) sopra la quale un fotogramma scuro non è nero ma contenuto:
# il nero sporco dei VHS (grigio, verdastro, righe di traking) resta sotto 6, un fondo
# blu saturo arriva a 70.
SAT_NERO = 10

# Neri lunghi e suono (vedi _inizio_suono): si ascoltano i neri di almeno NERO_LUNGO secondi;
# se il suono riparte almeno ANTICIPO_SUONO secondi prima della fine del nero, il nero è
# l'apertura scura dello spot. Livelli in dB (RMS su 0.1s).
NERO_LUNGO, ANTICIPO_SUONO = 2.0, 2.0
DB_SUONO, DB_SILENZIO = -45.0, -50.0

# Tipo per le callback di progresso: funzione async che accetta (messaggio, colore)
LogCallback      = Callable[[str, str], Awaitable[None]]
ProgressCallback = Callable[[float, str], Awaitable[None]]  # (valore 0.0-1.0, label)


class VideoEngine:
    """
    Gestisce tutta la logica pesante: blackdetect, taglio segmenti (e master, se richiesto).
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
        self._current_proc  = None
        self._running = True   # verrà sincronizzato con state["running"]
        self._prefisso_progresso = ""   # "Playlist 3/100 · " durante una playlist

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
        completati = 0
        session_log = []   # raccoglie i risultati per il report finale
        # Nomi assegnati ma non ancora creati da FFmpeg: evita che due spot
        # con lo stesso nome (es. bumper ripetuti) si sovrascrivano nei tagli paralleli
        nomi_prenotati: set[str] = set()
        # Ripresa dopo uno Stop: i video nello storico sono già fatti e si saltano;
        # tagli_in_corso.json ricorda i clip già creati di un video lasciato a metà,
        # che vengono rimossi prima di rifarlo (niente doppioni "(2)")
        cartella_lib  = state.get("work_dir", state["current_dir"])
        storico_path  = os.path.join(cartella_lib, "storico.json")
        in_corso_path = os.path.join(cartella_lib, "tagli_in_corso.json")

        total_videos = len(queue_snapshot)

        for idx, (vid, txt, m_year) in enumerate(queue_snapshot):
            # --- AGGIORNAMENTO PROGRESSO GLOBALE (v0.86) ---
            if global_progress_cb:
                await global_progress_cb(idx, total_videos)
            # Controlla interruzione ad ogni video. Il video fermato a metà ha già il suo
            # "Interrotto": questo (idx) non è mai partito e resta com'è
            if not state["running"]:
                break

            if not txt:
                continue

            if vid in self._leggi_json(storico_path):
                await self.log(f"⏭️ {vid}: già elaborato, saltato "
                               f"(per rifarlo toglilo dallo storico).", "grey")
                if status_cb:
                    await status_cb(idx, "✅ Già elaborato", "#4CAF50")
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
            precedenti = self._leggi_json(in_corso_path).get(vid, [])
            if precedenti:
                rimossi = 0
                for clip in precedenti:
                    try:
                        if os.path.exists(clip):
                            os.remove(clip)
                            rimossi += 1
                    except OSError as e:
                        await self.log(f"⚠️ Impossibile rimuovere {os.path.basename(clip)}: {e}", "orange")
                self._aggiorna_in_corso(in_corso_path, vid, None)
                await self.log(f"🧹 Ripresa dopo un'interruzione: rimossi {rimossi} clip "
                               f"del tentativo precedente, il video viene rifatto da capo.", "grey")
            if colore_data == "orange":
                await self.log(f"⚠️ Data in {vid} potrebbe essere ambigua, verificare.", "orange")
            duration = get_video_duration(video_path_completo)

            # ── 1. SORGENTE: ORIGINALE (default) O MASTER ALL-INTRA ───────
            # I clip vengono sempre ricodificati, quindi FFmpeg taglia al fotogramma
            # esatto anche dall'originale: il master aggiungerebbe solo una
            # ricodifica in più (verificato su 137 clip: stessi fotogrammi, qualità
            # più alta, file più leggeri). Resta disponibile dalle impostazioni.
            usa_master = state.get("use_master", False)
            master = master_dir = None
            if usa_master:
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

                ok = await self._create_master(video_path_completo, master, duration, state, c_flags)
                if not ok:
                    # Se fallisce la creazione del master, segniamo l'errore (o lo Stop)
                    if not state["running"]:
                        if status_cb:
                            await status_cb(idx, "🛑 Interrotto", "orange")
                        break
                    if status_cb:
                        await status_cb(idx, "❌ Errore Master", "red")
                    continue

                if not state["running"]:
                    if status_cb:
                        await status_cb(idx, "🛑 Interrotto", "orange")
                    break
                sorgente = master
            else:
                await self.log("Taglio diretto dall'originale (senza master).", "grey")
                sorgente = video_path_completo

            # ── 2. RICERCA NERI E CAMBI DI SCENA (un solo passaggio) ──────
            analisi = await self._analyze_video(sorgente, v_bth, v_bdur, duration, state, c_flags)
            if analisi is None:
                if status_cb:
                    await status_cb(idx, "🛑 Interrotto", "orange")
                break
            neri, scene, colorati = analisi

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
            ignorate = righe_txt_ignorate(txt_path_completo)
            if ignorate:
                await self.log(f"⚠️ Righe del txt ignorate perché non nel formato \"mm:ss - Nome\" "
                               f"({len(ignorate)}): se sono spot, restano attaccati al precedente.",
                               "orange")
                for riga in ignorate[:10]:
                    await self.log(f"   · {riga}", "orange")
                if len(ignorate) > 10:
                    await self.log(f"   · ... e altre {len(ignorate) - 10}", "orange")

            # ── 3b. SCEGLI IL NERO DI OGNI STACCO ─────────────────────────
            # Lo stesso nero chiude lo spot precedente (inizio nero + cuscinetto fine)
            # e apre quello successivo (fine nero - cuscinetto inizio).
            timestamps = [s["t"] for s in spot_list]
            tagli, scarto, n_campioni = self._choose_cuts(timestamps, neri, scene, v_toll, colorati)
            # Un nero lungo può essere l'apertura scura dello spot successivo (Super Faust:
            # 8s di buio col sonoro, poi compare la bomboletta): se dopo un silenzio il suono
            # riparte ben prima che torni l'immagine, il clip parte da lì. Le pause vere
            # restano in silenzio fino alla fine del nero e non cambiano.
            for tg in tagli:
                if tg and tg["tipo"] == "nero" and tg["b"] - tg["a"] >= NERO_LUNGO:
                    inizio = await self._inizio_suono(video_path_completo, tg["a"], tg["b"], c_flags)
                    if inizio is not None and inizio <= tg["b"] - ANTICIPO_SUONO:
                        tg["b_suono"], tg["b"] = tg["b"], inizio
            if n_campioni >= 3:
                await self.log(f"Timestamp del txt: il nero cade in media {scarto:+.2f}s dopo "
                               f"(misurato su {n_campioni} stacchi).", "grey")
            punti = []          # per ogni timestamp: (fine clip precedente, inizio clip)
            da_verificare = 0
            for j, (t, tg) in enumerate(zip(timestamps, tagli), 1):
                mmss = f"{int(t) // 60:02d}:{int(t) % 60:02d}"
                if tg is None:
                    punti.append((None, max(0.0, t - v_cusc_i)))
                elif tg["tipo"] == "nero":
                    if "b_suono" in tg:
                        corr = (f", apertura scura dello spot: si parte dal suono, non dalla "
                                f"fine del nero a {tg['b_suono']:.2f}s")
                    else:
                        corr = (f", fine corretta da {tg['b_base']:.2f}s" if "b_base" in tg else "")
                    await self.log(f"Stacco {j} ({mmss}): nero {tg['a']:.2f}-{tg['b']:.2f}s "
                                   f"(sensibilità {tg['sens']}{corr})", "grey")
                    # La fine del clip precedente resta dentro il nero: con un nero di soli
                    # 3 fotogrammi il cuscinetto arriverebbe sul primo fotogramma dello spot dopo
                    fine_prec = min(tg["a"] + v_cusc_f, tg["b"] - 0.02)
                    punti.append((fine_prec, max(0.0, tg["b"] - v_cusc_i)))
                else:
                    da_verificare += 1
                    motivo = ("stacco netto (cambio di scena)" if tg["tipo"] == "scena"
                              else "nessuno stacco riconoscibile, punto stimato")
                    await self.log(f"⚠️ Stacco {j} ({mmss}): nessun nero, {motivo} a "
                                   f"{tg['a']:.2f}s — da verificare", "orange")
                    # Senza nero il fotogramma sul punto di stacco è già del clip successivo:
                    # mezzo fotogramma prima basta a escluderlo dal clip precedente.
                    punti.append((tg["a"] - 0.02, tg["a"]))

            # ── 4. CALCOLA TUTTI I JOB DI TAGLIO ─────────────────────────
            # Prima costruiamo la lista completa dei job (tempi + nomi + path)
            # senza eseguire ancora nulla. Questo ci permette di lanciare
            # più tagli in parallelo nel passo successivo.
            cut_jobs = []
            results  = []
            tagli_riusciti = 0
            for i, spot in enumerate(spot_list, 1):
                name_r = spot["n"]
                # La "/" diventa un trattino ("Promo/teaser" -> "Promo-teaser"), gli altri
                # caratteri vietati da Windows spariscono; i punti restano ("G.W. Electronics")
                name_c = re.sub(r'[\\*?:"<>|]', "", name_r.replace("/", "-"))
                if len(name_c) > 100:
                    # Troppo lungo: si taglia all'ultimo spazio (non a metà parola) e senza
                    # lasciare una parentesi aperta ("... Junior (sponsorizzato da Mo")
                    if " " in name_c[:101]:
                        name_c = name_c[:101].rsplit(" ", 1)[0]
                    else:
                        name_c = name_c[:100]
                    if name_c.count("(") > name_c.count(")"):
                        name_c = name_c[:name_c.rfind("(")]
                    name_c = name_c.rstrip(" -,")
                name_c = name_c.rstrip(". ") or "Sconosciuto"

                r_s = punti[i - 1][1]
                if i < len(spot_list):
                    r_e = punti[i][0]
                else:
                    if duration and duration > r_s:
                        r_e = duration
                    else:
                        r_e = r_s + 60

                d_cat, k, l_col = self._categorize(name_r, data_finale)
                base_libreria   = state.get("work_dir", state["current_dir"])
                target_p        = (os.path.join(base_libreria, final_year, d_cat)
                                   if d_cat
                                   else os.path.join(base_libreria, final_year))
                os.makedirs(target_p, exist_ok=True)

                nome_finale = f"{self._nome_con_canale(name_c, vid)}{data_tag}"
                out_f      = get_unique_filename(target_p, nome_finale, ext=".mkv",
                                                 reserved=nomi_prenotati)

                cut_jobs.append({
                    "idx_spot": i,
                    "r_s": r_s, "r_e": r_e,
                    "out_f": out_f, "k": k, "l_col": l_col,
                })

            # ── 5. TAGLIA IN BATCH PARALLELI ─────────────────────────────
            # Ogni taglio ricodifica il segmento dalla sorgente (keyframe normali + CRF)
            # e scrive un file diverso: i nomi sono già stati prenotati al passo 4.
            #
            # Coda continua: appena un taglio finisce ne parte un altro, e i clip più
            # lunghi partono per primi, così alla fine i bumper corti riempiono i buchi
            # invece di lasciare core fermi ad aspettare lo spot più lungo.
            # Ogni x264 usa già tutti i core da solo: limitarne i thread non aiuta
            # (misurato su i5-13500H, da 4 a 16 tagli insieme).
            #
            # Parallelismo adattivo: metà core logici, min 1, max 12.
            # Esempi:
            #   i5-8259U (4 core /  8 thread) → 4 tagli paralleli
            #   i5-8400  (6 core /  6 thread) → 3 tagli paralleli
            #   5900X    (12 core / 24 thread) → 12 tagli paralleli
            # Il cap a 12 evita saturazione disco su HDD — su NVMe si può alzare.
            # Configurabile manualmente nelle impostazioni (0 = automatico).
            logical_cores = os.cpu_count() or 2
            # Valore manuale dalle impostazioni oppure calcolo automatico
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
            # L'ETA si basa sui secondi di video già tagliati, non sul numero di clip
            sec_totali  = sum(max(0.5, j["r_e"] - j["r_s"]) for j in cut_jobs) or 1.0
            sec_fatti   = 0.0
            t_inizio    = time.time()
            coda        = sorted(cut_jobs, key=lambda j: j["r_e"] - j["r_s"], reverse=True)
            posti       = asyncio.Semaphore(parallel_cuts)
            # Processi FFmpeg attivi: Stop li chiude tutti, non solo l'ultimo
            active_procs = []

            await self.progress(0.0, f"Taglio 0/{total_jobs} "
                                     f"({parallel_cuts} paralleli) — calcolo ETA...")

            async def _run_one(job):
                """Esegue un singolo taglio appena si libera un posto nella coda."""
                nonlocal done_count, sec_fatti, tagli_riusciti
                async with posti:
                    if not state["running"]:
                        return
                    await self.log(
                        f"⚙️ Avvio taglio {job['idx_spot']}/{total_jobs}: "
                        f"{os.path.basename(job['out_f'])}",
                        "grey"
                    )
                    t_start = time.time()
                    ok = await self._cut_segment(
                        sorgente, job["r_s"], job["r_e"],
                        v_crf, job["out_f"], state, c_flags,
                        proc_list=active_procs
                    )
                    elapsed = round(time.time() - t_start, 1)
                    if ok:
                        # Annotato anche se lo Stop arriva ora: il clip esiste e alla
                        # ripresa va tolto prima di rifare il video
                        self._aggiorna_in_corso(in_corso_path, vid, job["out_f"])
                    if ok and state["running"]:
                        await self.log(
                            f"✅ Tagliato {job['idx_spot']}/{total_jobs}: "
                            f"{os.path.basename(job['out_f'])} ({elapsed}s)",
                            job["l_col"]
                        )
                    elif not ok:
                        await self.log(
                            f"❌ Fallito {job['idx_spot']}/{total_jobs}: "
                            f"{os.path.basename(job['out_f'])}",
                            "red"
                        )

                done_count += 1
                sec_fatti  += max(0.5, job["r_e"] - job["r_s"])
                if ok and state["running"]:
                    tagli_riusciti += 1
                    state["stats_counts"].setdefault(job["k"], 0)
                    state["stats_counts"][job["k"]] += 1
                    if "update_stats_cb" in state and state["update_stats_cb"]:
                        await state["update_stats_cb"]()
                if state["running"]:
                    resto = (time.time() - t_inizio) / sec_fatti * (sec_totali - sec_fatti)
                    em, es = divmod(int(resto), 60)
                    await self.progress(done_count / total_jobs,
                                        f"Taglio {done_count}/{total_jobs} "
                                        f"({parallel_cuts} paralleli) — ~{em}m {es}s")

            await asyncio.gather(*[_run_one(j) for j in coda])
            if not state["running"]:
                await self.log("🛑 Interruzione durante taglio spot", "orange")
                if status_cb:
                    await status_cb(idx, "🛑 Interrotto", "orange")

            # ── 5. PULIZIA E SPOSTAMENTO ──────────────────────────────────
            if master and os.path.exists(master):
                try:
                    os.remove(master)
                except Exception:
                    pass
            # Rimuove la cartella Master_Temp solo se è rimasta vuota
            if master_dir and os.path.exists(master_dir):
                try:
                    os.rmdir(master_dir)
                except Exception:
                    pass

            if state["running"]:
                # Video arrivato in fondo: i suoi clip sono definitivi
                self._aggiorna_in_corso(in_corso_path, vid, None)
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
                    elif da_verificare:
                        avviso = f"{da_verificare} stacc{'o' if da_verificare == 1 else 'hi'} senza nero, da verificare"
                        if status_cb:
                            await status_cb(idx, f"⚠️ {avviso}", "#FF9500")
                        await self.log(
                            f"⚠️ {os.path.basename(video_path_completo)} elaborato "
                            f"({tagli_riusciti} tagli) — {avviso}.", "orange"
                        )
                        session_log.append(
                            f"  ⚠️ {os.path.basename(video_path_completo)} — "
                            f"{tagli_riusciti} tagli, {avviso}"
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
    def _leggi_json(path: str) -> dict:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    @staticmethod
    def _aggiorna_in_corso(path: str, vid: str, clip: str | None):
        """Aggiunge un clip creato al video in corso, o con clip=None chiude la sua voce."""
        dati = VideoEngine._leggi_json(path)
        if clip is None:
            if vid not in dati:
                return
            dati.pop(vid)
        else:
            dati.setdefault(vid, []).append(clip)
        try:
            if dati:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(dati, f, indent=2, ensure_ascii=False)
            elif os.path.exists(path):
                os.remove(path)
        except OSError:
            pass

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

    # ── BLACKDETECT A PIÙ SENSIBILITÀ ─────────────────────────────────────
    async def _analyze_video(self, video, bth, bdur, duration, state, c_flags) -> tuple | None:
        """
        Un solo passaggio sul video (originale o master):
        - blackdetect a tre sensibilità (bth, +0.05, +0.10): il nero delle registrazioni
          VHS cambia anche dentro lo stesso video;
        - cambi di scena (scdet), per gli stacchi netti senza nero;
        - fotogrammi colorati (saturazione media > SAT_NERO): blackdetect guarda solo la
          luminosità, e un blu saturo è scuro quanto il nero sporco del VHS, che però è grigio.
        Ritorna ({sensibilità: [(black_start, black_end), ...]}, [(tempo, punteggio), ...],
        [tempi dei fotogrammi colorati]), None se interrotto.
        """
        levels = [round(float(bth) + k * 0.05, 2) for k in range(3)]
        n = len(levels)
        graph = (f"[0:v]split={n + 2}" + "".join(f"[s{i}]" for i in range(n + 2)) + ";"
                 + ";".join(f"[s{i}]blackdetect=d={bdur}:pix_th={th}[o{i}]"
                            for i, th in enumerate(levels))
                 + f";[s{n}]scale=320:-2,scdet=threshold=3[o{n}]"
                 + f";[s{n + 1}]scale=160:-2,signalstats,metadata=mode=select:"
                   f"key=lavfi.signalstats.SATAVG:value={SAT_NERO}:function=greater,"
                   f"metadata=mode=print:key=lavfi.signalstats.SATAVG[o{n + 1}]")
        maps = [a for i in range(n + 2) for a in ("-map", f"[o{i}]")]
        cmd = [get_tool_path('ffmpeg'), '-y', '-stats', '-i', video,
               '-filter_complex', graph, *maps, '-f', 'null', '-']
        # Nel grafo il filtro 0 è lo split, quindi il blackdetect i-esimo è Parsed_blackdetect_{i+1}
        names = {f"Parsed_blackdetect_{i + 1}": th for i, th in enumerate(levels)}
        found = {th: [] for th in levels}
        scene = []
        colorati = []
        rx = re.compile(r"(Parsed_blackdetect_\d+) @ [^\]]*\] black_start:\s*([\d.]+) black_end:\s*([\d.]+)")
        rx_sc = re.compile(r"lavfi\.scd\.score:\s*([\d.]+),\s*lavfi\.scd\.time:\s*([\d.]+)")
        rx_col = re.compile(r"Parsed_metadata_\d+ @ [^\]]*\] frame:\d+\s+pts:\S+\s+pts_time:([\d.]+)")

        await self.log(f"Ricerca neri (sensibilità {', '.join(map(str, levels))})...", "grey")
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
                creationflags=c_flags
            )
            self._current_proc = proc
            buf = ""
            while True:
                if not state["running"]:
                    await safe_kill_process(proc)
                    self._current_proc = None
                    return None
                try:
                    chunk = await asyncio.wait_for(proc.stderr.read(4096), timeout=0.5)
                except asyncio.TimeoutError:
                    continue
                if not chunk:
                    break
                buf += chunk.decode(errors="ignore")
                *lines, buf = re.split(r"[\r\n]", buf)
                for line in lines:
                    if m := rx.search(line):
                        if m.group(1) in names:
                            found[names[m.group(1)]].append((float(m.group(2)), float(m.group(3))))
                    elif m := rx_sc.search(line):
                        scene.append((float(m.group(2)), float(m.group(1))))
                    elif m := rx_col.search(line):
                        colorati.append(float(m.group(1)))
                    elif duration > 0 and (tm := re.search(r"time=(\d{2}:\d{2}:\d{2}\.\d{2})", line)):
                        perc = min(0.99, get_seconds(tm.group(1)) / duration)
                        await self.progress(perc, f"Ricerca neri: {int(perc * 100)}%")
            await proc.wait()
            self._current_proc = None
            if proc.returncode != 0:
                await self.log(f"⚠️ Ricerca neri terminata con errore (codice {proc.returncode})", "red")
            await self.log("Neri trovati: " + ", ".join(
                f"{len(v)} a sensibilità {th}" for th, v in found.items()), "grey")
            return found, scene, sorted(colorati)
        except Exception as e:
            self._current_proc = None
            await self.log(f"⚠️ Errore ricerca neri: {e}", "red")
            return {th: [] for th in levels}, [], None

    @staticmethod
    def _choose_cuts(timestamps: list, neri: dict, scene: list, toll: float,
                     colorati: list | None = None) -> tuple:
        """
        Trova il punto di taglio di ogni stacco (uno per timestamp del txt).

        1. I pezzi di nero separati da meno di 0.2s diventano un nero unico
           (disturbi VHS in mezzo al nero).
        2. Scarto: i timestamp di uno stesso video hanno di solito un anticipo costante
           (mdeplo: ~+0.8s), misurato sugli stacchi con un solo nero corto vicino.
           Il punto atteso di ogni stacco è timestamp + scarto.
        3. Alla sensibilità più severa gli stacchi si assegnano tutti insieme: un nero va
           bene se dista al massimo toll dal punto atteso (0 se il punto cade dentro il nero,
           così funzionano anche i neri lunghi), in ordine e senza mai riusare lo stesso nero.
           Un timestamp uguale al precedente non dice nulla: prende il primo nero libero.
        4. Stacchi rimasti senza nero: sensibilità più permissive, poi il cambio di scena
           (stacco netto) abbastanza forte più vicino al punto atteso, infine il punto atteso
           stesso. Per uno stacco netto il punto atteso usa l'anticipo misurato sull'inizio dei
           neri, non sulla fine: il txt segna l'inizio del nero e su uno stacco netto non c'è
           nero da attraversare (con i bumper di 2s si prendeva lo stacco dopo).
        5. La fine di ogni nero si allunga con le sensibilità più permissive (nero VHS che
           schiarisce), fermandosi al primo fotogramma colorato (vedi colorati).

        Ritorna (tagli, scarto, n_campioni). tagli[k] è None (primo spot senza nero) oppure
        {"tipo": "nero"|"scena"|"stima", "a": inizio, "b": fine, "sens": sensibilità del nero};
        "b_base" è la fine del nero prima del passo 5, se è cambiata.
        """
        GAP, MAX_CORTO, PENALITA, SCENA_MIN = 0.2, 1.5, toll + 0.5, 5.0
        levels = sorted(neri)

        def unisci(lst):
            out = []
            for a, b in sorted(lst):
                if out and a - out[-1][1] <= GAP + 1e-6:
                    out[-1] = (out[-1][0], max(out[-1][1], b))
                else:
                    out.append((a, b))
            return out

        def distanza(p, b):
            return 0.0 if b[0] <= p <= b[1] else min(abs(p - b[0]), abs(p - b[1]))

        neri = {th: unisci(v) for th, v in neri.items()}
        base = neri[levels[0]]

        campioni, campioni_inizio = [], []
        for t in timestamps:
            c = [b for b in base if abs(b[1] - t) <= toll]
            if len(c) == 1 and c[0][1] - c[0][0] <= MAX_CORTO:
                campioni.append(c[0][1] - t)
                campioni_inizio.append(c[0][0] - t)
        scarto = statistics.median(campioni) if len(campioni) >= 3 else 0.0
        attesi = [t + scarto for t in timestamps]
        # Punto atteso di uno stacco netto (senza nero): dove il nero inizierebbe
        scarto_inizio = statistics.median(campioni_inizio) if len(campioni_inizio) >= 3 else 0.0
        attesi_netti = [t + scarto_inizio for t in timestamps]
        n = len(attesi)

        # 3. Programmazione dinamica: stato = indice dell'ultimo nero usato
        stati = {-1: (0.0, [])}
        for k, p in enumerate(attesi):
            duplicato = k > 0 and timestamps[k] <= timestamps[k - 1]
            limite = attesi[k + 1] if k + 1 < n else float("inf")
            nuovi = {}
            for ultimo, (costo, scelte) in stati.items():
                opzioni = [(ultimo, costo + PENALITA, None)]
                for j in range(ultimo + 1, len(base)):
                    b = base[j]
                    if duplicato:
                        if b[0] > limite:
                            break
                        opzioni.append((j, costo + 0.001 * (j - ultimo), j))
                    else:
                        if b[0] > p + toll:
                            break
                        d = distanza(p, b)
                        if d <= toll:
                            opzioni.append((j, costo + d, j))
                for chiave, c, scelta in opzioni:
                    if chiave not in nuovi or c < nuovi[chiave][0]:
                        nuovi[chiave] = (c, scelte + [scelta])
            stati = nuovi
        scelte = min(stati.values(), key=lambda s: s[0])[1]

        tagli = [{"tipo": "nero", "a": base[j][0], "b": base[j][1], "sens": levels[0]}
                 if j is not None else None for j in scelte]

        # 4. Stacchi senza nero, sempre tra i due stacchi vicini
        for k in range(n):
            if tagli[k]:
                continue
            p = attesi[k]
            lo = max((t["b"] for t in tagli[:k] if t), default=0.0)
            hi = min((t["a"] for t in tagli[k + 1:] if t), default=float("inf"))
            for th in levels[1:]:
                c = [b for b in neri[th] if b[0] >= lo and b[1] <= hi and distanza(p, b) <= toll]
                if c:
                    b = min(c, key=lambda x: distanza(p, x))
                    tagli[k] = {"tipo": "nero", "a": b[0], "b": b[1], "sens": th}
                    break
            if not tagli[k] and k > 0:   # il primo spot senza nero parte dal suo timestamp
                p = attesi_netti[k]
                c = [s for s in scene if lo < s[0] < hi and abs(s[0] - p) <= toll and s[1] >= SCENA_MIN]
                if c:
                    # Il più vicino, non il più forte: negli spot molto montati uno stacco
                    # interno può essere più netto di quello vero
                    s = min(c, key=lambda x: abs(x[0] - p))
                    tagli[k] = {"tipo": "scena", "a": s[0], "b": s[0]}
                else:
                    q = min(max(p, lo), hi)
                    tagli[k] = {"tipo": "stima", "a": q, "b": q}

        # 5. Fine del nero: sui nastri rovinati il nero si "solleva" verso il grigio (o un
        #    disturbo lo spezza) e la sensibilità scelta ne vede solo la prima parte. Se alle
        #    sensibilità più permissive lo stesso nero continua, il clip successivo parte dalla
        #    fine vera, mai oltre l'inizio dello stacco dopo. Il nero finisce comunque al primo
        #    fotogramma colorato: per la luminosità un blu saturo è "nero", ma è già lo spot.
        #    Senza i dati sul colore (analisi fallita) i neri restano come sono.
        #    La fine del clip precedente non cambia.
        if colorati is not None:
            for k, tg in enumerate(tagli):
                if not tg or tg["tipo"] != "nero":
                    continue
                hi = min((t["a"] for t in tagli[k + 1:] if t), default=float("inf"))
                fine = tg["b"]
                for th in levels:
                    if th <= tg["sens"]:
                        continue
                    for x, y in neri[th]:
                        if x <= fine + GAP + 1e-6 and fine < y < hi:
                            fine = y
                # Un nero scelto a sensibilità permissiva può contenere colore già dall'inizio
                da = tg["a"] if tg["sens"] > levels[0] else tg["b"]
                i = bisect.bisect_left(colorati, da - 1e-3)
                if i < len(colorati) and colorati[i] < fine:
                    fine = max(colorati[i], tg["a"])
                if fine <= tg["a"] + 1e-6:
                    # Colorato fin dal primo fotogramma: non era un nero ma lo sfondo scuro
                    # dello spot successivo, quindi è uno stacco netto proprio lì
                    tagli[k] = {"tipo": "scena", "a": tg["a"], "b": tg["a"], "b_base": tg["b"]}
                elif abs(fine - tg["b"]) > 1e-6:
                    tg["b_base"], tg["b"] = tg["b"], fine
        return tagli, scarto, len(campioni)

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
                    if mm := RIGA_TXT.search(line):
                        spot_list.append({
                            "t": get_seconds(mm.group(1)),
                            "n": mm.group(2).strip()
                        })
            return spot_list
        except Exception:
            return None

    async def _inizio_suono(self, video, a, b, c_flags) -> float | None:
        """
        Dentro il nero a-b: inizio dell'ultimo tratto di suono che arriva fino alla fine del
        nero, se prima c'è un silenzio. None se il nero è muto in fondo, se il suono c'è per
        tutto il nero (nessuno stacco sentito) o se l'audio non si legge.
        """
        cmd = [get_tool_path('ffmpeg'), '-v', 'error', '-ss', f"{a:.2f}", '-i', video,
               '-t', f"{b - a:.2f}", '-vn', '-af',
               "aresample=44100,asetnsamples=n=4410,astats=metadata=1:reset=1,"
               "ametadata=print:key=lavfi.astats.Overall.RMS_level:file=-", '-f', 'null', '-']
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
                creationflags=c_flags)
            out, _ = await asyncio.wait_for(proc.communicate(), 60)
        except (OSError, asyncio.TimeoutError):
            return None
        livelli, t = [], None
        for riga in out.decode(errors="ignore").splitlines():
            if "pts_time:" in riga:
                t = a + float(riga.split("pts_time:")[1])
            elif "RMS_level=" in riga and t is not None:
                v = riga.split("=")[1]
                livelli.append((t, -120.0 if "inf" in v else float(v)))
        i = len(livelli)
        while i > 0 and livelli[i - 1][1] > DB_SUONO:
            i -= 1
        if i == len(livelli) or i == 0 or not any(db < DB_SILENZIO for _, db in livelli[:i]):
            return None
        return livelli[i][0]

    @staticmethod
    async def _scarta_parziale(out_f):
        """Cancella il clip rimasto a metà (Stop, timeout o errore): in libreria solo clip completi."""
        for _ in range(10):
            try:
                if os.path.exists(out_f):
                    os.remove(out_f)
                return
            except PermissionError:
                # Windows può tenere il file aperto per un attimo dopo la chiusura di FFmpeg
                await asyncio.sleep(0.2)
            except OSError:
                return

    async def _cut_segment(self, src, r_s, r_e, crf, out_f, state, c_flags,
                           proc_list: list | None = None) -> bool:
        """
        Taglia un singolo segmento dalla sorgente (originale o master) e lo salva in out_f.
        proc_list: lista condivisa dove registrare il processo attivo,
                   usata dai tagli paralleli per killarli tutti su Stop.
        Ritorna True se riuscito.
        """
        # Seek ibrido: salto veloce fino a 1s prima, poi seek preciso sull'ultimo secondo.
        # Dall'originale FFmpeg riparte dal keyframe precedente e decodifica fino al
        # fotogramma esatto, quindi il primo fotogramma è lo stesso che dal master.
        # Stesso risultato del solo seek dopo -i (anche nei pacchetti audio copiati),
        # ma senza decodificare il video dall'inizio.
        pre = min(1.0, r_s)
        cmd = [
            get_tool_path('ffmpeg'), '-y',
            '-ss', f"{r_s - pre:.2f}", '-i', src,
            '-ss', f"{pre:.2f}",
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
                    await self._scarta_parziale(out_f)
                    return False
                await asyncio.sleep(0.1)
                if time.time() - start_time > timeout:
                    await self.log("⏱️ Timeout FFmpeg...", "red")
                    await safe_kill_process(p_cut)
                    await self._scarta_parziale(out_f)
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
                await self._scarta_parziale(out_f)
                return False
            return True
        except Exception as e:
            await self.log(f"🚨 Errore critico FFmpeg: {e}", "red")
            await self._scarta_parziale(out_f)
            if proc_list is None:
                self._current_proc = None
            return False
        
    # ── RILEVAMENTO CANALE ────────────────────────────────────────────────
    CANALI = [
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
        (["tele+", "tele +", "telepiù", "sky"],           "Tele+"),
    ]

    @staticmethod
    def _extract_channel(name_r: str) -> str:
        """
        Cerca il nome del canale nel titolo del file.
        Ritorna il nome canale formattato oppure "" se non trovato.
        """
        n = name_r.lower()
        for keywords, label in VideoEngine.CANALI:
            if any(k in n for k in keywords):
                return label
        return ""

    @staticmethod
    def _nome_con_canale(nome: str, vid: str) -> str:
        """
        Nome del clip con il canale del video, scritto una volta sola nella forma standard.
        Il canale che mdeplo mette in coda al nome ("Promo X - Retequattro", anche seguito
        da "(sponsorizzato da ...)") diventa la forma standard ("Promo X - Rete 4").
        Se il nome cita già il canale in un altro punto ("Bumper ident Retequattro") resta
        com'è; se non lo cita, il canale viene aggiunto in coda.
        """
        label = VideoEngine._extract_channel(vid)
        if not label:
            return nome
        alias = next(k for k, lb in VideoEngine.CANALI if lb == label)
        parti = nome.split(" - ")
        for i, parte in enumerate(parti[1:], 1):
            for a in alias:
                if m := re.match(rf"{re.escape(a)}(?=\s*(\(|$))", parte, re.IGNORECASE):
                    parti[i] = label + parte[m.end():]
                    break
        nome = " - ".join(parti)
        if any(a in nome.lower() for a in alias):
            return nome
        return f"{nome} - {label}"

    # ── CATEGORIZZAZIONE SPOT ─────────────────────────────────────────────
    @staticmethod
    def _categorize(name_r: str, data: str | None = None) -> tuple:
        """
        Ritorna (cartella_destinazione, chiave_stats, colore_log)
        data: "GG-MM-AAAA" del video (o None), serve per i marchi natalizi.
        """
        n = name_r.lower()

        # --- CATEGORIA FESTIVITÀ (Natale & Capodanno) ---
        # Usiamo radici per catturare singolari/plurali e varianti
        keywords_feste = [
            # Natale: Dolci
            "nataliz", "natale", "pandor", "panetton",

            # Capodanno e Festeggiamenti
            "capodanno", "vigilia", "brindisi", "spumant",
            "cenon", "cin cin", "buon anno",

            # Termini generici ma sicuri
            "augur", "buone feste", "festività"
        ]
        # Marchi dei dolci natalizi: fanno anche caramelle e gelati ("Sanagola Alemagna",
        # "Tartufone Motta"), quindi valgono solo per i video di novembre, dicembre e gennaio
        # (o senza data)
        marchi_feste = ["bauli", "melegatti", "alemagna", "maina", "paluani", "tartufon"]
        try:
            periodo_feste = int(data.split("-")[1]) in (11, 12, 1)
        except (AttributeError, IndexError, ValueError):
            periodo_feste = True

        if any(x in n for x in keywords_feste) or (periodo_feste and any(x in n for x in marchi_feste)):
            return "Natale", "natale", "#FF3D00"
        # ---------------------------------

        # Nei txt la prima parola dice il tipo ("Spot ...", "Promo/anticipazioni ..."): vale
        # quella, così "Spot promozioni Fiat" non finisce nei Promo né "Spot giornale annunci"
        # negli Annunci. Le parole chiave sotto restano per i nomi che iniziano diversamente.
        prima = re.split(r"[\s/]+", n.strip(' "'), maxsplit=1)[0]
        if prima in ("spot", "minispot"):
            return "", "spot", "#2ECC71"
        if prima in ("promo", "trailer"):
            return "Promo", "promo", "#F1C40F"
        if prima == "bumper":
            return "Bumper", "bumper", "#00E5FF"
        if prima in ("annuncio", "annunci"):
            return "Annunci", "annunci", "#FF85FF"
        if prima in ("cartello", "cartelli"):
            return "Cartelli", "cartelli", "#E0E0E0"
        if prima in ("videosigla", "videosigle", "sigla", "sigle"):
            return "Videosigle", "videosigle", "#BF94FF"

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

    # ── TXT DALLA DESCRIZIONE YOUTUBE ─────────────────────────────────────
    @staticmethod
    def _righe_txt(desc: str) -> list[str]:
        """Righe "mm:ss - Nome" ricavate dai timestamp della descrizione di un video."""
        righe = []
        for d_line in desc.splitlines():
            m = re.search(r"(\d{1,2}:\d{2}(?::\d{2})?)\s*[-:]?\s*(.+)", d_line.strip())
            if m and m.group(2).strip():
                righe.append(f"{m.group(1)} - {m.group(2).strip().strip('*_ ')}")
        return righe

    @staticmethod
    def _nomi_descrizione(desc: str) -> list[str]:
        """
        Nomi della lista "Contenuto della sequenza:" delle descrizioni senza timestamp
        ("- Spot Aperol Barbieri"), in ordine; i separatori "****" tra le sequenze si saltano.
        """
        return [m.group(1).strip() for riga in desc.splitlines()
                if (m := re.match(r"\s*[-–•]\s*(.*\w.*)$", riga))]

    # yt-dlp mette nei nomi dei file varianti "larghe" dei caratteri vietati da Windows
    _LARGHI = str.maketrans({"⧸": "/", "＂": '"', "：": ":", "？": "?", "＊": "*",
                             "｜": "|", "＜": "<", "＞": ">", "＼": "\\"})

    @staticmethod
    def _norm_titolo(s: str) -> str:
        """Solo lettere e cifre minuscole: "25⧸4⧸1985 - RaiDue" e "2541985   RaiDue" coincidono."""
        return "".join(c for c in s.translate(VideoEngine._LARGHI).lower() if c.isalnum())

    @staticmethod
    def _query_da_file(vid_name: str) -> list[str]:
        """
        Testo da cercare su YouTube ricavato dal nome del file. Se la data ha perso le barre
        ("2541985 RaiDue ...") le rimette, provando entrambe le letture quando è ambigua
        ("1111985" -> 1/11/1985 e 11/1/1985): senza barre YouTube non trova il video.
        """
        t = re.sub(r"\s+", " ", os.path.splitext(vid_name)[0].translate(VideoEngine._LARGHI)).strip()
        m = re.match(r"(\d{2,4})((?:19|20)\d{2})\b\s*(.*)", t)
        if not m:
            return [t]
        gm, anno, resto = m.groups()
        varianti = []
        for i in range(1, len(gm)):
            g, me = gm[:i], gm[i:]
            if len(g) <= 2 and len(me) <= 2 and 1 <= int(g) <= 31 and 1 <= int(me) <= 12:
                varianti.append(f"{int(g)}/{int(me)}/{anno} {resto}".strip())
        return varianti or [t]

    async def cerca_txt_youtube(self, vid_name: str, solo_data: bool = False) -> dict:
        """
        Cerca su YouTube il video da cui viene vid_name (per titolo) e ne ricava il txt,
        per i video già scaricati senza txt. Non sceglie mai a caso: accetta solo un titolo
        uguale al nome del file (o di cui il nome è l'inizio, per i nomi troncati).
        Ritorna {"esito": "ok" | "no_timestamp" | "non_trovato" | "ambiguo" | "errore",
                 "messaggio": ..., "data" ("GG-MM-AAAA" dal titolo, o None) se il video è
                 stato trovato, "txt" solo se ok, "nomi" (lista senza orari) se no_timestamp}.
        solo_data: serve solo la data del titolo (verifica online), la descrizione non si legge.
        """
        c_flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

        async def _yt(*args, timeout=60):
            p = await asyncio.create_subprocess_exec(
                self.ytdlp_bin, "--no-warnings", "--encoding", "utf-8", *args,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                creationflags=c_flags)
            try:
                out, _ = await asyncio.wait_for(p.communicate(), timeout)
            except asyncio.TimeoutError:
                await kill_process_tree(p)
                raise RuntimeError("YouTube non risponde")
            return out.decode("utf-8", errors="replace")

        def compatibili(cand, nf):
            return [(v, ch, tit) for v, (ch, tit) in cand.items()
                    if (nt := self._norm_titolo(tit)) == nf or (len(nf) >= 20 and nt.startswith(nf))]

        # I file doppioni hanno un segno in fondo al nome ("... prom[2]", "(2)", "- Copia")
        # che nessun titolo YouTube ha: solo se il nome intero non trova nulla si riprova senza.
        base, ext = os.path.splitext(vid_name)
        senza = re.sub(r"(?:\s*(?:\[\d+\]|\(\d+\)|-\s*cop(?:ia|y)))+\s*$", "", base, flags=re.I).strip()
        nomi = [base] + ([senza] if senza and senza != base else [])

        # Nei nomi troncati l'ultima parola è spezzata ("... e prom") e YouTube con quella
        # non trova nulla: se la ricerca completa fallisce si riprova senza l'ultima parola.
        # Il confronto dei titoli resta sul nome intero. Le letture di una data ambigua si
        # cercano sempre tutte, così due video compatibili risultano ambigui.
        try:
            for nome in nomi:
                nf = self._norm_titolo(nome)
                candidati = {}
                for q in self._query_da_file(nome + ext):
                    ricerche = [q] + ([q.rsplit(" ", 1)[0]] if len(q.split()) >= 4 else [])
                    for r in ricerche:
                        trovati = {}
                        out = await _yt("--flat-playlist", "--print", "%(id)s\t%(channel)s\t%(title)s",
                                        f"ytsearch8:{r}")
                        for riga in out.splitlines():
                            parti = riga.split("\t")
                            if len(parti) == 3:
                                trovati.setdefault(parti[0], (parti[1], parti[2]))
                        candidati.update(trovati)
                        if compatibili(trovati, nf):
                            break
                buoni = compatibili(candidati, nf)
                if buoni:
                    break
        except Exception as e:
            return {"esito": "errore", "messaggio": f"ricerca su YouTube non riuscita ({e})"}

        if len(buoni) > 1:
            esatti = [b for b in buoni if self._norm_titolo(b[2]) == nf]
            buoni = esatti or buoni
        if len(buoni) > 1:
            buoni = [b for b in buoni if b[1].lower() == "mdeplo"] or buoni
        if not buoni:
            return {"esito": "non_trovato", "messaggio": "nessun video su YouTube con questo titolo"}
        if len(buoni) > 1:
            return {"esito": "ambiguo", "messaggio": "più video con titolo compatibile: "
                    + "; ".join(f'"{b[2]}"' for b in buoni[:3])}

        vid_id, canale, titolo = buoni[0]
        # La data del titolo vero ("25/4/1985 - ...") vale anche quando il nome del file
        # l'ha persa o resa ambigua ("2541985"), anche se la descrizione non ha timestamp
        from utils import extract_date_info
        data, _, colore = extract_date_info(titolo)
        data = data if colore == "green" else None
        if solo_data:
            return {"esito": "ok", "data": data, "messaggio": f"trovato \"{titolo}\" ({canale})"}
        try:
            desc = await _yt("--skip-download", "--print", "description",
                             f"https://www.youtube.com/watch?v={vid_id}")
        except Exception as e:
            return {"esito": "errore", "messaggio": f"descrizione di \"{titolo}\" non letta ({e})"}
        righe = self._righe_txt(desc)
        if not righe:
            return {"esito": "no_timestamp", "data": data, "nomi": self._nomi_descrizione(desc),
                    "messaggio": f"trovato \"{titolo}\" ({canale}), ma la descrizione non ha timestamp"}
        return {"esito": "ok", "txt": "\n".join(righe), "data": data,
                "messaggio": f"trovato \"{titolo}\" ({canale}), {len(righe)} righe"}

    # ── DOWNLOAD PLAYLIST ─────────────────────────────────────────────────
    async def elenco_playlist(self, url: str) -> list[dict] | None:
        """Video della playlist (anche da un link "watch?v=...&list=..."), senza scaricarli."""
        c_flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        try:
            p = await asyncio.create_subprocess_exec(
                self.ytdlp_bin, "--flat-playlist", "--yes-playlist", "--no-warnings",
                "--encoding", "utf-8", "--print", "%(id)s\t%(title)s", url,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                creationflags=c_flags)
            out, _ = await asyncio.wait_for(p.communicate(), 180)
        except Exception as e:
            await self.log(f"⚠️ Elenco della playlist non letto: {e}", "red")
            return None
        voci = []
        for riga in out.decode("utf-8", errors="replace").splitlines():
            vid_id, _, titolo = riga.partition("\t")
            if vid_id.strip():
                voci.append({"id": vid_id.strip(), "titolo": titolo.strip()})
        return voci

    async def download_playlist(self, url: str, output_dir: str, state: dict,
                                generate_txt: bool, video_cb) -> dict | None:
        """
        Scarica la playlist un video alla volta, con lo stesso procedimento del video singolo
        (txt compreso). video_cb(risultato) viene chiamata appena ogni video è pronto, così
        finisce subito in coda. I video già in archive.txt vengono saltati: rimettendo lo
        stesso link dopo uno Stop si riparte dal primo che manca.
        """
        voci = await self.elenco_playlist(url)
        if not voci:
            await self.log("⚠️ Nessun video trovato nella playlist.", "orange")
            return None
        archivio = set()
        try:
            with open(os.path.join(output_dir, "archive.txt"), "r", encoding="utf-8") as f:
                archivio = {r.split()[1] for r in f if len(r.split()) == 2}
        except OSError:
            pass

        n = len(voci)
        esito = {"totale": n, "scaricati": 0, "saltati": 0, "errori": 0}
        await self.log(f"📃 Playlist: {n} video.", "cyan")
        try:
            for i, v in enumerate(voci, 1):
                if not state.get("running", True):
                    break
                self._prefisso_progresso = f"Playlist {i}/{n} · "
                if v["id"] in archivio:
                    esito["saltati"] += 1
                    await self.log(f"⏭️ Playlist {i}/{n}: {v['titolo']} — già scaricato.", "grey")
                    continue
                await self.log(f"📃 Playlist {i}/{n}: {v['titolo']}", "cyan")
                risultato = await self.download_youtube(
                    f"https://www.youtube.com/watch?v={v['id']}", output_dir, state, generate_txt)
                if risultato:
                    esito["scaricati"] += 1
                    await video_cb(risultato)
                elif state.get("running", True):
                    esito["errori"] += 1
        finally:
            self._prefisso_progresso = ""
        esito["interrotta"] = not state.get("running", True)
        await self.log(
            f"📃 Playlist {'interrotta' if esito['interrotta'] else 'finita'}: "
            f"{esito['scaricati']} scaricati, {esito['saltati']} già presenti"
            + (f", {esito['errori']} non riusciti" if esito["errori"] else "")
            + (" — rimetti lo stesso link per riprendere." if esito["interrotta"] else "."),
            "orange" if esito["interrotta"] or esito["errori"] else "green")
        return esito

    # ── DOWNLOAD YOUTUBE ──────────────────────────────────────────────────
    async def download_youtube(self, url: str, output_dir: str, state: dict,
                               generate_txt: bool = True) -> list[tuple[str, str | None]] | None:
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
                    if not state.get("running", True):
                        break
                    # Timeout: lo Stop deve funzionare anche se yt-dlp resta in silenzio
                    try:
                        chunk = await asyncio.wait_for(process.stdout.read(256), timeout=0.5)
                    except asyncio.TimeoutError:
                        continue
                    if not chunk:
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
                                            await self.progress(p, f"{self._prefisso_progresso}⬇️ {int(p * 100)}% — {video_title}")
                                        except ValueError:
                                            pass
                                break

            await _read_progress()
            if not state.get("running", True):
                await kill_process_tree(process)
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
                txt_lines = self._righe_txt(desc)
                if txt_lines:
                    txt_basename = os.path.splitext(vid_basename)[0] + ".txt"
                    with open(os.path.join(output_dir, txt_basename), "w", encoding="utf-8") as tf:
                        tf.write("\n".join(txt_lines))
                elif generate_txt:
                    await self.log("ℹ️ Nessun timestamp nella descrizione — TXT non generato.", "orange")
                    txt_basename = None
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
