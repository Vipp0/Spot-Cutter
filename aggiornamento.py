"""
aggiornamento.py — Aggiornamento del programma dalle release di GitHub.

1. cerca_aggiornamento(): chiede a GitHub l'ultima release e la confronta con la versione in uso.
2. scarica(): scarica il pacchetto .zip della release e ne controlla l'impronta SHA-256.
3. avvia_sostituzione(): estrae il pacchetto e lancia uno script che aspetta la chiusura del
   programma, sostituisce SpotCutter.exe e _internal (il resto della cartella non si tocca:
   bin con yt-dlp e ffmpeg, file dell'utente), e riapre il programma. Se la sostituzione non
   riesce rimette la versione di prima. L'esito finisce in un file che il programma legge
   al riavvio (esito_precedente()).
Nessuna dipendenza da Qt: lo usa main.py dai suoi thread.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

# (la variabile d'ambiente serve solo alle prove: punta a una release finta in locale)
URL_ULTIMA = (os.environ.get("SPOTCUTTER_URL_AGGIORNAMENTI")
              or "https://api.github.com/repos/Vipp0/Spot-Cutter/releases/latest")
PAGINA_RELEASE = "https://github.com/Vipp0/Spot-Cutter/releases/latest"


def _numeri(versione: str) -> tuple:
    """ "1.4.10" -> (1, 4, 10); le parti non numeriche contano zero."""
    return tuple(int(p) if p.isdigit() else 0 for p in re.split(r"[.\-]", versione.strip().lstrip("vV")))


def piu_nuova(candidata: str, attuale: str) -> bool:
    a, b = _numeri(candidata), _numeri(attuale)
    n = max(len(a), len(b))
    return a + (0,) * (n - len(a)) > b + (0,) * (n - len(b))


def novita(note: str, massimo: int = 8) -> list:
    """Dai testi della release, i titoli in grassetto delle voci in italiano."""
    titoli = []
    for riga in note.splitlines():
        if "🇮🇹" in riga:
            m = re.search(r"\*\*(.+?)\*\*", riga)
            if m:
                titoli.append(m.group(1).replace("`", ""))
    return titoli[:massimo]


def cerca_aggiornamento(versione_attuale: str, url: str = URL_ULTIMA) -> dict | None:
    """
    L'ultima release, se è più nuova di quella in uso: {"versione", "note", "pagina", "zip",
    "dimensione", "sha256"} ("zip" è None se la release non ha il pacchetto .zip). None se si
    è già aggiornati. Solleva un'eccezione se GitHub non risponde.
    """
    req = urllib.request.Request(url, headers={"User-Agent": "SpotCutter",
                                               "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        dati = json.loads(r.read().decode("utf-8"))
    versione = str(dati.get("tag_name", "")).lstrip("vV")
    if not versione or not piu_nuova(versione, versione_attuale):
        return None
    pacchetto = next((a for a in dati.get("assets", []) if a.get("name", "").lower().endswith("-win-x64.zip")), None)
    digest = (pacchetto or {}).get("digest") or ""
    return {
        "versione": versione,
        "note": dati.get("body") or "",
        "pagina": dati.get("html_url") or PAGINA_RELEASE,
        "zip": (pacchetto or {}).get("browser_download_url"),
        "dimensione": (pacchetto or {}).get("size", 0),
        "sha256": digest.split(":", 1)[1].lower() if digest.startswith("sha256:") else None,
    }


def cartella_programma() -> str:
    """La cartella di SpotCutter.exe (solo per il programma compilato)."""
    return os.path.dirname(sys.executable)


def si_puo_aggiornare() -> str | None:
    """None se l'aggiornamento automatico è possibile, altrimenti il motivo."""
    if not getattr(sys, "frozen", False):
        return "il programma è avviato dal codice sorgente, non dalla versione compilata"
    prova = os.path.join(cartella_programma(), ".prova_scrittura")
    try:
        with open(prova, "w") as f:
            f.write("x")
        os.remove(prova)
    except OSError:
        return "la cartella del programma non è modificabile (per esempio è dentro Programmi)"
    return None


def scarica(url: str, destinazione: str, sha256: str | None = None, progresso=None):
    """Scarica il pacchetto; se GitHub ne dà l'impronta, la controlla. Nessun file a metà in caso di errore."""
    parziale = destinazione + ".part"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "SpotCutter"})
        h = hashlib.sha256()
        with urllib.request.urlopen(req, timeout=30) as r, open(parziale, "wb") as f:
            totale, fatti = int(r.headers.get("Content-Length") or 0), 0
            while True:
                blocco = r.read(256 * 1024)
                if not blocco:
                    break
                f.write(blocco)
                h.update(blocco)
                fatti += len(blocco)
                if progresso and totale:
                    progresso(min(fatti / totale, 1.0))
        if sha256 and h.hexdigest() != sha256:
            raise RuntimeError("il file scaricato non corrisponde all'impronta della release")
        os.replace(parziale, destinazione)
    finally:
        if os.path.exists(parziale):
            try:
                os.remove(parziale)
            except OSError:
                pass


def file_esito() -> str:
    return os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "SpotCutter", "aggiornamento.txt")


def esito_precedente() -> str | None:
    """Il risultato dell'ultimo aggiornamento (letto una volta sola, poi il file si cancella)."""
    path = file_esito()
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            testo = f.read().strip()
        os.remove(path)
        return testo or None
    except OSError:
        return None


_SCRIPT = r'''
$ErrorActionPreference = "Stop"
$app   = '{app}'
$nuova = '{nuova}'
$tmp   = '{tmp}'
$esito = '{esito}'
$versione = '{versione}'
function Scrivi($t) {{ New-Item -ItemType Directory -Force -Path (Split-Path $esito) | Out-Null; Set-Content -Path $esito -Value $t -Encoding UTF8 }}
# 1. aspetta che Spot Cutter sia chiuso del tutto
try {{ Wait-Process -Id {pid} -Timeout 120 -ErrorAction SilentlyContinue }} catch {{}}
Start-Sleep -Milliseconds 800
$vecchio_int = Join-Path $app '_internal.vecchio'
$vecchio_exe = Join-Path $app 'SpotCutter.exe.vecchio'
try {{
    # 2. mette da parte la versione in uso (si riprova per qualche secondo se un file è ancora bloccato)
    if (Test-Path $vecchio_int) {{ Remove-Item $vecchio_int -Recurse -Force }}
    if (Test-Path $vecchio_exe) {{ Remove-Item $vecchio_exe -Force }}
    $ok = $false
    for ($i = 0; $i -lt 20 -and -not $ok; $i++) {{
        try {{ Rename-Item (Join-Path $app '_internal') '_internal.vecchio'; $ok = $true }}
        catch {{ Start-Sleep -Milliseconds 500 }}
    }}
    if (-not $ok) {{ throw "la cartella _internal è ancora in uso" }}
    Rename-Item (Join-Path $app 'SpotCutter.exe') 'SpotCutter.exe.vecchio'
    # 3. copia la nuova
    Copy-Item (Join-Path $nuova '_internal') (Join-Path $app '_internal') -Recurse -Force
    Copy-Item (Join-Path $nuova 'SpotCutter.exe') (Join-Path $app 'SpotCutter.exe') -Force
    $leggimi = Join-Path $nuova 'bin\README.txt'
    if (Test-Path $leggimi) {{ New-Item -ItemType Directory -Force -Path (Join-Path $app 'bin') | Out-Null; Copy-Item $leggimi (Join-Path $app 'bin\README.txt') -Force }}
    # 4. tutto a posto: via la versione vecchia
    Remove-Item $vecchio_int -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item $vecchio_exe -Force -ErrorAction SilentlyContinue
    Scrivi "ok $versione"
}} catch {{
    # qualcosa non è andato: si rimette la versione di prima
    $motivo = $_.Exception.Message
    if (Test-Path $vecchio_int) {{
        if (Test-Path (Join-Path $app '_internal')) {{ Remove-Item (Join-Path $app '_internal') -Recurse -Force -ErrorAction SilentlyContinue }}
        Rename-Item $vecchio_int '_internal' -ErrorAction SilentlyContinue
    }}
    if (Test-Path $vecchio_exe) {{
        if (Test-Path (Join-Path $app 'SpotCutter.exe')) {{ Remove-Item (Join-Path $app 'SpotCutter.exe') -Force -ErrorAction SilentlyContinue }}
        Rename-Item $vecchio_exe 'SpotCutter.exe' -ErrorAction SilentlyContinue
    }}
    Scrivi "errore $motivo"
}}
# 5. riapre il programma e fa pulizia
{riapri}
Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
'''


def avvia_sostituzione(zip_path: str, versione: str, app: str | None = None, pid: int | None = None,
                       riapri: bool = True) -> str:
    """
    Estrae il pacchetto e lancia (staccato dal programma) lo script che fa la sostituzione
    quando il programma si chiude. Ritorna il percorso dello script. Dopo questa chiamata il
    programma deve chiudersi.
    """
    app = os.path.abspath(app or cartella_programma())
    tmp = os.path.dirname(os.path.abspath(zip_path))
    estratta = os.path.join(tmp, "estratta")
    shutil.rmtree(estratta, ignore_errors=True)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(estratta)
    nuova = next((radice for radice, _, files in os.walk(estratta)
                  if "SpotCutter.exe" in files and os.path.isdir(os.path.join(radice, "_internal"))), None)
    if not nuova:
        raise RuntimeError("il pacchetto non contiene SpotCutter.exe e la cartella _internal")
    # Di solito installa la versione nuova stessa (avvio.py --installa), mostrando la schermata
    # di caricamento con l'avanzamento; lo script PowerShell resta come riserva
    if riapri and sys.platform == "win32":
        try:
            subprocess.Popen([os.path.join(nuova, "SpotCutter.exe"), "--installa", app,
                              "--pid", str(int(pid or os.getpid())), "--esito", file_esito()],
                             cwd=nuova, close_fds=True)
            return os.path.join(nuova, "SpotCutter.exe")
        except OSError:
            pass
    q = lambda p: p.replace("'", "''")   # apici raddoppiati: stringhe sicure per PowerShell
    script = os.path.join(tmp, "aggiorna.ps1")
    with open(script, "w", encoding="utf-8-sig") as f:
        f.write(_SCRIPT.format(app=q(app), nuova=q(nuova), tmp=q(tmp), esito=q(file_esito()),
                               versione=q(versione), pid=int(pid or os.getpid()),
                               riapri=(f"Start-Process -FilePath '{q(os.path.join(app, 'SpotCutter.exe'))}'"
                                       if riapri else "")))
    flags = 0
    if sys.platform == "win32":
        # niente DETACHED_PROCESS: PowerShell senza console si chiude subito senza fare nulla.
        # Con CREATE_NO_WINDOW ha una console nascosta e sopravvive alla chiusura del programma
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    subprocess.Popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden",
                      "-File", script], creationflags=flags, close_fds=True)
    return script


def cartella_scaricamento() -> str:
    path = os.path.join(tempfile.gettempdir(), "SpotCutter_aggiornamento")
    shutil.rmtree(path, ignore_errors=True)
    os.makedirs(path, exist_ok=True)
    return path
