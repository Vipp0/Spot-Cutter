"""
utils.py — Funzioni di utilità pure
"""
import re
import os
import sys
import json
import subprocess
import asyncio
import atexit
from datetime import datetime

# ── COSTANTI ──────────────────────────────────────────────────────────────
ESTENSIONI_VIDEO = ('.mp4', '.mkv', '.avi', '.mov', '.mpg', '.webm')
TEMP_MASTER_FILE = "master_temp.mkv"
SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")
SETTINGS_DEFAULTS = {
    "crf": "20", "cusc_i": "0.05", "cusc_f": "0.12",
    "toll": "2.0", "bth": "0.1", "bdur": "0.1",
    "parallel_cuts": "0", "silence_thresh": "-35dB",
    "silence_dur": "0.1", "auto_start_after_yt": False
}

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

def get_seconds(time_str):
    try:
        parts = list(map(float, str(time_str).replace(',', '.').split(':')))
        if len(parts) == 3: return parts[0] * 3600 + parts[1] * 60 + parts[2]
        if len(parts) == 2: return parts[0] * 60 + parts[1]
        return parts[0]
    except: return 0.0

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

def get_unique_filename(directory, name, ext=".mkv"):
    if not ext.startswith("."): ext = "." + ext
    full_path = os.path.join(directory, f"{name}{ext}")
    base_name = name
    counter = 1
    while os.path.exists(full_path):
        counter += 1
        full_path = os.path.join(directory, f"{base_name} ({counter}){ext}")
    return full_path

def get_video_duration(file_path):
    cmd = [get_tool_path('ffprobe'), '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', file_path]
    try:
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        res = subprocess.run(cmd, capture_output=True, text=True, creationflags=flags)
        return float(res.stdout.strip())
    except: return 0.0

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
                  silence_thresh="-35dB", silence_dur="0.1", auto_start_after_yt=False):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump({"crf": crf, "cusc_i": str(cusc_i), "cusc_f": str(cusc_f), 
                       "toll": str(toll), "bth": bth, "bdur": bdur,
                       "parallel_cuts": str(parallel_cuts),
                       "silence_thresh": silence_thresh,
                       "silence_dur": silence_dur,
                       "auto_start_after_yt": auto_start_after_yt}, f, indent=2)
    except Exception as e: print(f"⚠️ Errore settings: {e}")