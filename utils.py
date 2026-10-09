"""
utils.py — Funzioni di utilità pure
"""
import re
import os
import sys
import json
import shutil
import subprocess
import asyncio
import atexit
import logging
from datetime import datetime

# ── COSTANTI ──────────────────────────────────────────────────────────────
ESTENSIONI_VIDEO = ('.mp4', '.mkv', '.avi', '.mov', '.mpg', '.webm')
TEMP_MASTER_FILE = "master_temp.mkv"
SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")
SETTINGS_DEFAULTS = {
    "crf": "20", "cusc_i": "0.05", "cusc_f": "0.12",
    "toll": "2.0", "bth": "0.1", "bdur": "0.1",
    "parallel_cuts": "0", "auto_start_after_yt": False, "use_master": False
}

# ── LOG TECNICO ───────────────────────────────────────────────────────────
# Tutto ciò che passa nel log della finestra, più i dettagli che lì non entrano (errori
# completi di yt-dlp, comandi lanciati, errori imprevisti), in un file con data e ora.
# Finché avvia_log_tecnico() non viene chiamata (prove, tools) i messaggi si perdono.
LOG = logging.getLogger("spotcutter")
LOG.addHandler(logging.NullHandler())
LOG_MAX_BYTE = 5 * 1024 * 1024   # il file non supera i 5 MB; se ne tiene uno solo precedente

def cartella_log() -> str:
    return os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "SpotCutter")

def avvia_log_tecnico() -> str:
    """Accende il log su file (spotcutter.log, più spotcutter.log.1 quando si riempie). Ritorna il percorso."""
    from logging.handlers import RotatingFileHandler
    path = os.path.join(cartella_log(), "spotcutter.log")
    try:
        os.makedirs(cartella_log(), exist_ok=True)
        h = RotatingFileHandler(path, maxBytes=LOG_MAX_BYTE, backupCount=1, encoding="utf-8")
        h.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-7s  %(message)s", "%d-%m-%Y %H:%M:%S"))
        LOG.addHandler(h)
        LOG.setLevel(logging.DEBUG)
    except OSError:
        pass   # senza log il programma funziona lo stesso
    return path

# ── RICERCA ESEGUIBILI ESTERNI ────────────────────────────────────────────
def _get_base_dir() -> str:
    """Cartella base: quella dell'EXE in produzione, dello script in sviluppo."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def get_tool_path(name: str) -> str:
    """
    Cerca un eseguibile nell'ordine:
    1. Cartella EXE/script
    2. Sottocartella bin/
    3. PATH di sistema
    """
    base = _get_base_dir()
    candidates = [name]
    if sys.platform == "win32" and not name.endswith(".exe"):
        candidates.append(name + ".exe")
    for candidate in candidates:
        path = os.path.join(base, candidate)
        if os.path.isfile(path):
            return path
        path = os.path.join(base, "bin", candidate)
        if os.path.isfile(path):
            return path
    return name

def strumento_presente(name: str) -> bool:
    """True se l'eseguibile c'è: nella cartella del programma, in bin/ o nel PATH di sistema."""
    path = get_tool_path(name)
    return os.path.isfile(path) or bool(shutil.which(path))

def aggiungi_strumenti_al_path():
    """
    Mette in testa al PATH del programma la sua cartella e bin/, se contengono ffmpeg o ffprobe:
    così li trova anche chi viene lanciato da noi (yt-dlp per unire video e audio, ffplay).
    """
    base = _get_base_dir()
    attuali = os.environ.get("PATH", "").split(os.pathsep)
    for cartella in (os.path.join(base, "bin"), base):
        if cartella not in attuali and any(os.path.isfile(os.path.join(cartella, exe))
                                           for exe in ("ffmpeg.exe", "ffprobe.exe")):
            os.environ["PATH"] = cartella + os.pathsep + os.environ.get("PATH", "")

# Pagina ufficiale di yt-dlp: l'ultima versione e l'elenco delle impronte SHA-256
YTDLP_URL = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/"

def scarica_ytdlp(progresso=None) -> str:
    """
    Scarica yt-dlp.exe dalla pagina ufficiale in bin/ e ne controlla l'impronta SHA-256.
    progresso(frazione 0-1) viene chiamata durante lo scaricamento. Ritorna il percorso;
    se qualcosa va storto solleva un'eccezione e non lascia file a metà.
    """
    import hashlib
    import urllib.request
    cartella = os.path.join(_get_base_dir(), "bin")
    os.makedirs(cartella, exist_ok=True)
    finale, parziale = os.path.join(cartella, "yt-dlp.exe"), os.path.join(cartella, "yt-dlp.exe.part")

    def apri(nome):
        req = urllib.request.Request(YTDLP_URL + nome, headers={"User-Agent": "SpotCutter"})
        return urllib.request.urlopen(req, timeout=30)

    try:
        with apri("SHA2-256SUMS") as r:
            impronte = r.read().decode("utf-8", "replace")
        attesa = next((riga.split()[0].lower() for riga in impronte.splitlines()
                       if riga.split()[1:] == ["yt-dlp.exe"]), None)
        if not attesa:
            raise RuntimeError("impronta di yt-dlp.exe non trovata nella pagina ufficiale")
        sha = hashlib.sha256()
        with apri("yt-dlp.exe") as r, open(parziale, "wb") as f:
            totale, fatti = int(r.headers.get("Content-Length") or 0), 0
            while True:
                blocco = r.read(256 * 1024)
                if not blocco:
                    break
                f.write(blocco)
                sha.update(blocco)
                fatti += len(blocco)
                if progresso and totale:
                    progresso(min(fatti / totale, 1.0))
        if sha.hexdigest() != attesa:
            raise RuntimeError("il file scaricato non corrisponde all'impronta ufficiale")
        os.replace(parziale, finale)
        return finale
    finally:
        if os.path.exists(parziale):
            try: os.remove(parziale)
            except OSError: pass

@atexit.register
def cleanup_temp_files():
    if os.path.exists(TEMP_MASTER_FILE):
        try: os.remove(TEMP_MASTER_FILE)
        except: pass

async def safe_kill_process(proc, timeout=2):
    if proc is None: return
    try:
        if proc.returncode is None:
            proc.terminate()
            try: await asyncio.wait_for(proc.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
    except Exception: pass

async def kill_process_tree(proc, timeout=5):
    """Chiude il processo e i suoi figli (yt-dlp.exe lancia un sottoprocesso e ffmpeg)."""
    if proc is None or proc.returncode is not None: return
    if sys.platform == "win32":
        try:
            killer = await asyncio.create_subprocess_exec(
                "taskkill", "/F", "/T", "/PID", str(proc.pid),
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW)
            await killer.wait()
        except Exception: pass
    await safe_kill_process(proc, timeout)

def get_seconds(time_str):
    try:
        parts = list(map(float, str(time_str).replace(',', '.').split(':')))
        if len(parts) == 3: return parts[0] * 3600 + parts[1] * 60 + parts[2]
        if len(parts) == 2: return parts[0] * 60 + parts[1]
        return parts[0]
    except: return 0.0

# Riga del txt degli spot che il programma taglia: "mm:ss - Nome" (anche "m:ss", "h:mm:ss")
RIGA_TXT = re.compile(r"(\d{1,2}:\d{2}(?::\d{2})?)\s*-\s*(.+)")

def righe_txt_ignorate(txt_path) -> list[str]:
    """
    Righe del txt che non sono nel formato "mm:ss - Nome" e quindi non diventano un taglio
    (quello spot resterebbe attaccato al precedente). Non conta le righe vuote e quelle
    senza lettere né cifre, come i separatori "****".
    """
    try:
        with open(txt_path, "r", encoding="utf-8", errors="replace") as f:
            return [l.strip() for l in f
                    if any(c.isalnum() for c in l) and not RIGA_TXT.search(l)]
    except OSError:
        return []

def righe_txt_fuori_ordine(txt_path) -> list[str]:
    """
    Righe del txt con un orario uguale o precedente a quello della riga prima. A volte è
    giusto (bumper e spot nello stesso secondo), a volte è un errore di chi ha scritto i
    timestamp: il programma non può saperlo, quindi lo segnala.
    """
    try:
        with open(txt_path, "r", encoding="utf-8", errors="replace") as f:
            righe = [(get_seconds(m.group(1)), l.strip()) for l in f if (m := RIGA_TXT.search(l))]
    except OSError:
        return []
    return [riga for (t_prima, _), (t, riga) in zip(righe, righe[1:]) if t <= t_prima]

def is_valid_date(g, m, a):
    try:
        day, month, year = int(g), int(m), int(a)
        if not (1900 <= year <= 2100): 
            return False
        # Verifica l'esistenza reale del giorno (es. no 31 Febbraio)
        datetime(year, month, day)
        return True
    except:
        return False

def extract_date_info(filename):
    raw_name = filename 
    found_candidates = []

    # Regex potenziata: gestisce -, ., /, e lo slash speciale ⧸
    # Cerca schemi GG-MM-AAAA
    pattern_sep = re.finditer(r'(\d{1,2})[-/.⧸](\d{1,2})[-/.⧸](\d{4})', raw_name)
    
    for m in pattern_sep:
        g, m_val, a = m.groups()
        if is_valid_date(g, m_val, a):
            found_candidates.append({
                "date_str": f"{str(g).zfill(2)}-{str(m_val).zfill(2)}-{a}",
                "year": int(a),
                "priority": 1
            })

    # Cerca numeri compatti (8 cifre tipo 18102018)
    for m in re.finditer(r"(\d{8})", raw_name):
        d = m.group(1)
        g, m_val, a = d[:2], d[2:4], d[4:]
        if is_valid_date(g, m_val, a):
            found_candidates.append({
                "date_str": f"{g}-{m_val}-{a}",
                "year": int(a),
                "priority": 2
            })

    if not found_candidates:
        # Date compatte senza barre né zeri ("1331983" = 13/3/1983, "2071984" = 20/7/1984):
        # nei titoli originali giorno e mese non hanno lo zero davanti, quindi una parte che
        # inizia con 0 non è una lettura possibile. Restano arancioni (da confermare): la
        # verifica online col titolo YouTube le rende verdi. Se le letture sono due
        # ("1121985" = 1/12 o 11/2) si sa solo l'anno.
        for m in re.finditer(r"(?<!\d)(\d{2,3})((?:19|20)\d{2})(?!\d)", raw_name):
            gm, a = m.groups()
            letture = [(gm[:i], gm[i:]) for i in range(1, len(gm))
                       if gm[0] != "0" and gm[i] != "0" and is_valid_date(gm[:i], gm[i:], a)]
            if len(letture) == 1:
                g, m_val = letture[0]
                return f"{g.zfill(2)}-{m_val.zfill(2)}-{a}", a, "orange"
            if letture:
                return f"01-01-{a}", a, "orange"

        # Fallback anno isolato (es. "Film 1995.mp4")
        year_match = re.search(r'(?:^|\D)(19\d{2}|20\d{2})(?:\D|$)', raw_name)
        if year_match:
            a = year_match.group(1)
            return f"01-01-{a}", str(a), "orange"
        return "", "Sconosciuto", "red"

    # Selezione: Anno più vecchio vince (utile per repliche/archivi)
    found_candidates.sort(key=lambda x: (x["year"], x["priority"]))
    best = found_candidates[0]
    
    # Logica colore: Verde se è materiale d'archivio (<2015), Arancio se recente (da verificare)
    color = "green" if best["year"] < 2015 else "orange"
    
    return best["date_str"], str(best["year"]), color

def motivo_non_pronto(vid, txt, manual_date, cartella) -> str | None:
    """
    Perché un video in coda non si può ancora elaborare (None se è pronto): serve un txt non
    vuoto e una data certa (inserita a mano, confermata online o verde dal nome del file).
    La usano il pulsante Avvia e il motore, che la richiede quando tocca a quel video.
    """
    if not txt:
        return "manca il txt"
    try:
        if os.path.getsize(os.path.join(cartella, txt)) == 0:
            return "il txt è vuoto"
    except OSError:
        return "manca il txt"
    manuale = manual_date.strip() if manual_date else ""
    if manuale in ("", "--"):
        data, _, colore = extract_date_info(vid)
        if not data:
            return "manca la data"
    else:
        data, colore = manuale, "green"
    try:
        datetime.strptime(data, "%d-%m-%Y")
    except ValueError:
        return "data non valida"
    return None if colore == "green" else "data da confermare"

def get_unique_filename(directory, name, ext=".mkv", reserved=None):
    """reserved: set di percorsi (normcase) già assegnati ma non ancora scritti su disco."""
    if not ext.startswith("."): ext = "." + ext
    full_path = os.path.join(directory, f"{name}{ext}")
    base_name = name
    counter = 1

    def _taken(p):
        return os.path.exists(p) or (reserved is not None and os.path.normcase(p) in reserved)

    while _taken(full_path):
        counter += 1
        full_path = os.path.join(directory, f"{base_name} ({counter}){ext}")
    if reserved is not None:
        reserved.add(os.path.normcase(full_path))
    return full_path

def get_video_duration(file_path):
    cmd = [get_tool_path('ffprobe'), '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', file_path]
    try:
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        res = subprocess.run(cmd, capture_output=True, text=True, creationflags=flags)
        return float(res.stdout.strip())
    except: return 0.0

def miniatura_video(file_path, durata=0.0):
    """
    Un fotogramma del video (192 px di larghezza) per la card della coda: percorso del jpg,
    o None se non si riesce. Si tiene in una cartella temporanea e si rifà solo se il video
    cambia. Si prende un po' dopo l'inizio e si sceglie il fotogramma più rappresentativo di
    due secondi (filtro thumbnail), perché il primo è spesso nero.
    """
    import hashlib, tempfile
    try:
        st = os.stat(file_path)
    except OSError:
        return None
    cartella = os.path.join(tempfile.gettempdir(), "SpotCutter_miniature")
    os.makedirs(cartella, exist_ok=True)
    chiave = hashlib.md5(f"2|{file_path}|{st.st_size}|{st.st_mtime}".encode("utf-8")).hexdigest()
    out = os.path.join(cartella, chiave + ".jpg")
    if os.path.exists(out) and os.path.getsize(out) > 0:
        return out
    t = min(max(durata * 0.1, 3.0), 30.0) if durata > 6 else 0.0
    cmd = [get_tool_path('ffmpeg'), '-v', 'error', '-y', '-ss', f"{t:.2f}", '-i', file_path,
           '-frames:v', '1', '-vf', 'thumbnail=50,scale=192:-2', '-q:v', '4', out]
    try:
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        subprocess.run(cmd, capture_output=True, creationflags=flags, timeout=30)
    except Exception:
        return None
    return out if os.path.exists(out) and os.path.getsize(out) > 0 else None

def parse_settings(input_crf, input_cusc_i, input_cusc_f, input_toll, input_bth, input_bdur):
    errors = []
    d = SETTINGS_DEFAULTS

    def _clean_float(input_obj, key_default):
        try:
            # Gestisce sia virgola che punto
            val = str(input_obj.value).replace(',', '.').strip()
            return float(val)
        except:
            errors.append(f"Valore non valido per {key_default}, ripristinato default.")
            return float(d[key_default])

    crf = str(int(_clean_float(input_crf, "crf"))) # CRF deve essere intero
    cusc_i = _clean_float(input_cusc_i, "cusc_i")
    cusc_f = _clean_float(input_cusc_f, "cusc_f")
    toll = _clean_float(input_toll, "toll")
    bth = str(_clean_float(input_bth, "bth"))
    bdur = str(_clean_float(input_bdur, "bdur"))

    return crf, cusc_i, cusc_f, toll, bth, bdur, errors

def load_settings():
    if not os.path.exists(SETTINGS_FILE): return dict(SETTINGS_DEFAULTS)
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            for k, v in SETTINGS_DEFAULTS.items():
                if k not in data: data[k] = v
            return data
    except: return dict(SETTINGS_DEFAULTS)

def save_settings(crf, cusc_i, cusc_f, toll, bth, bdur, parallel_cuts="0",
                  auto_start_after_yt=False, use_master=False):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump({"crf": crf, "cusc_i": str(cusc_i), "cusc_f": str(cusc_f),
                       "toll": str(toll), "bth": bth, "bdur": bdur,
                       "parallel_cuts": str(parallel_cuts),
                       "auto_start_after_yt": auto_start_after_yt,
                       "use_master": use_master}, f, indent=2)
    except Exception as e: print(f"⚠️ Errore settings: {e}")