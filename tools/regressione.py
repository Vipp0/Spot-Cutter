"""
Prova anti-regressione del motore di taglio.

Dopo una modifica al motore dice, su tutti i video di prova, quali tagli cambiano rispetto a
prima. Non crea clip e non tocca nessuna libreria: legge i video e i loro txt.

    python tools/regressione.py                    confronta con i risultati accettati
    python tools/regressione.py --analizza         analizza i video nuovi o cambiati (lento)
    python tools/regressione.py --accetta          i risultati di adesso diventano quelli attesi
    python tools/regressione.py --rispetto-a REF   confronta col motore di un commit git (es. HEAD)
    python tools/regressione.py --fotogrammi       per ogni taglio cambiato, foglio di fotogrammi

La parte lenta (neri, cambi di scena, colore: un passaggio su tutto il video) si fa una volta
sola con --analizza e resta salvata; il confronto poi ricalcola solo la scelta dei tagli e
richiede pochi secondi. L'audio dei neri lunghi si legge la prima volta che serve e resta
salvato anche lui. I dati stanno in tools/regressione_dati/ (fuori da git: contengono i
percorsi dei video): lì cartelle.json dice in quali cartelle cercare i video di prova.
"""
import argparse
import asyncio
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys

QUI = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(QUI)
sys.path.insert(0, REPO)
sys.stdout.reconfigure(encoding="utf-8")

from utils import get_video_duration, ESTENSIONI_VIDEO   # noqa: E402
from video_engine import VideoEngine                     # noqa: E402

DATI = os.path.join(QUI, "regressione_dati")
ANALISI = os.path.join(DATI, "analisi")
ATTESI = os.path.join(DATI, "attesi.json")
CARTELLE = os.path.join(DATI, "cartelle.json")
FOTO = os.path.join(DATI, "fotogrammi")
# Impostazioni di fabbrica: la prova non deve dipendere da quelle scelte nel programma
BTH, BDUR, TOLL = "0.1", "0.1", 2.0
FLAGS = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


async def _nop(*a, **k):
    pass


def _leggi(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _scrivi(path, dati):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(dati, f, ensure_ascii=False)
    os.replace(tmp, path)


def _file_analisi(video):
    return os.path.join(ANALISI, hashlib.md5(video.encode("utf-8")).hexdigest() + ".json")


def _impronta(path):
    st = os.stat(path)
    return [st.st_size, int(st.st_mtime)]


def _txt(video):
    return os.path.splitext(video)[0] + ".txt"


def video_di_prova():
    """Video con txt nelle cartelle di cartelle.json; lo stesso file in due cartelle conta una volta."""
    cartelle = _leggi(CARTELLE, None)
    if cartelle is None:
        cartelle = [REPO, os.path.join(REPO, "dist", "SpotCutter")]
        _scrivi(CARTELLE, cartelle)
        print(f"Creato {CARTELLE}: aggiungi lì le cartelle con i video di prova.")
    trovati, visti = [], set()
    for c in cartelle:
        for radice, _, files in os.walk(c):
            if os.path.basename(radice) in ("_internal", "bin"):
                continue
            for f in sorted(files):
                p = os.path.join(radice, f)
                if f.lower().endswith(ESTENSIONI_VIDEO) and os.path.exists(_txt(p)):
                    chiave = (f, os.path.getsize(p))
                    if chiave not in visti:
                        visti.add(chiave)
                        trovati.append(os.path.normpath(p))
    return trovati


# ── ANALISI (lenta, una volta per video) ──────────────────────────────────
async def analizza(video):
    eng = VideoEngine(_nop, _nop)
    sem = asyncio.Semaphore(max(1, (os.cpu_count() or 4) // 4))
    da_fare = []
    for v in video:
        d = _leggi(_file_analisi(v), {})
        if d.get("impronta") != _impronta(v) or d.get("bth") != BTH or d.get("bdur") != BDUR:
            da_fare.append(v)
    print(f"Da analizzare: {len(da_fare)} video su {len(video)}.")

    async def uno(v):
        async with sem:
            an = await eng._analyze_video(v, BTH, BDUR, get_video_duration(v), {"running": True}, FLAGS)
            if an is None:
                print(f"  ❌ analisi non riuscita: {v}")
                return
            _scrivi(_file_analisi(v), {"video": v, "impronta": _impronta(v), "bth": BTH, "bdur": BDUR,
                                       "neri": an[0], "scene": an[1], "colorati": an[2], "audio": {}})
            print(f"  ✅ {os.path.basename(v)}")

    await asyncio.gather(*(uno(v) for v in da_fare))


# ── SCELTA DEI TAGLI (veloce) ─────────────────────────────────────────────
def carica_motore(ref):
    """La classe VideoEngine del commit ref (il motore com'era), per confrontare senza attesi."""
    sorgente = subprocess.run(["git", "show", f"{ref}:video_engine.py"], cwd=REPO, capture_output=True)
    if sorgente.returncode != 0:
        sys.exit(f"Commit non trovato: {ref}")
    path = os.path.join(DATI, "motore_riferimento.py")
    os.makedirs(DATI, exist_ok=True)
    with open(path, "wb") as f:
        f.write(sorgente.stdout)
    spec = importlib.util.spec_from_file_location("motore_riferimento", path)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo.VideoEngine


async def tagli_di(classe, dati):
    """Tagli scelti dal motore per un video analizzato: [[tipo, a, b] | None per ogni riga del txt]."""
    eng = classe(_nop, _nop)
    audio = dati.setdefault("audio", {})
    leggi_audio = eng._livelli_audio if hasattr(eng, "_livelli_audio") else None

    async def livelli_salvati(video, a, b, c_flags):
        chiave = f"{a:.3f}|{b:.3f}"
        if chiave not in audio:
            audio[chiave] = await leggi_audio(video, a, b, c_flags)
            dati["_nuovo_audio"] = True
        return [tuple(x) for x in audio[chiave]]

    spots = eng._read_spot_list(_txt(dati["video"])) or []
    neri = {float(k): v for k, v in dati["neri"].items()}
    if "durata" not in dati:
        dati["durata"] = get_video_duration(dati["video"])
        dati["_nuovo_audio"] = True   # fa salvare il file di analisi
    if hasattr(eng, "_scegli_tagli"):
        # Dalla 1.3.8 tutta la scelta dei tagli sta in una funzione sola del motore
        eng._livelli_audio = livelli_salvati
        tagli = (await eng._scegli_tagli(spots, neri, dati["scene"], dati["colorati"], dati["video"],
                                         dati["durata"], TOLL, FLAGS))[2]
    else:
        tagli = eng._choose_cuts([s["t"] for s in spots], neri, dati["scene"], TOLL, dati["colorati"])[0]
        if hasattr(eng, "_applica_suono"):
            eng._livelli_audio = livelli_salvati
            await eng._applica_suono(tagli, dati["video"], FLAGS)
    return [s["n"] for s in spots], [[t["tipo"], round(t["a"], 2), round(t["b"], 2)] if t else None
                                    for t in tagli]


async def calcola(classe, video):
    """{video: {"txt": impronta del txt, "nomi": [...], "tagli": [...]}} per i video già analizzati."""
    ris = {}
    for v in video:
        dati = _leggi(_file_analisi(v), None)
        if not dati or dati.get("impronta") != _impronta(v):
            continue
        nomi, tagli = await tagli_di(classe, dati)
        if dati.pop("_nuovo_audio", False):
            _scrivi(_file_analisi(v), dati)
        with open(_txt(v), "rb") as f:
            impronta_txt = hashlib.md5(f.read()).hexdigest()
        ris[v] = {"txt": impronta_txt, "nomi": nomi, "tagli": tagli}
    return ris


# ── RESOCONTO ─────────────────────────────────────────────────────────────
def mmss(t):
    return f"{int(t) // 60:02d}:{int(t) % 60:02d}"


def descrivi(t):
    return "—" if t is None else f"{t[0]} {t[1]:.2f}" + (f"-{t[2]:.2f}" if t[2] != t[1] else "")


def confronta(prima, dopo):
    cambi, nuovi, txt_cambiati, uguali = [], [], [], 0
    for v, d in dopo.items():
        p = prima.get(v)
        if p is None:
            nuovi.append(v)
        elif p["txt"] != d["txt"]:
            txt_cambiati.append(v)
        else:
            for k, (x, y) in enumerate(zip(p["tagli"], d["tagli"])):
                if x == y:
                    uguali += 1
                else:
                    cambi.append((v, k, d["nomi"][k], x, y))
    return cambi, nuovi, txt_cambiati, uguali


def fotogrammi(cambi):
    shutil.rmtree(FOTO, ignore_errors=True)
    os.makedirs(FOTO)
    font = os.path.join(FOTO, "arial.ttf")
    shutil.copy(os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "arial.ttf"), font)
    for n, (v, k, nome, x, y) in enumerate(cambi, 1):
        punti = [t[1] for t in (x, y) if t] + [t[2] for t in (x, y) if t]
        a0 = max(0.0, min(punti) - 1.2)
        durata = max(punti) - a0 + 1.2
        righe = int(durata * 6 / 10) + 1
        nome_file = f"{n:03d} stacco {k + 1} {os.path.splitext(os.path.basename(v))[0][:40]}.png"
        nome_file = "".join(c for c in nome_file if c not in '\\/:*?"<>|⧸')
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{a0:.2f}", "-i", v, "-t", f"{durata:.2f}",
                        "-vf", f"fps=6,scale=128:-2,drawtext=fontfile=arial.ttf:"
                        f"text='%{{pts\\:flt\\:{a0:.2f}}}':x=2:y=2:fontsize=12:fontcolor=yellow:"
                        f"box=1:boxcolor=black,tile=10x{righe}", "-frames:v", "1", nome_file],
                       cwd=FOTO, creationflags=FLAGS)
    os.remove(font)
    print(f"\nFotogrammi (6 al secondo, col tempo in giallo) in {FOTO}")


def main():
    ap = argparse.ArgumentParser(description="Prova anti-regressione del motore di taglio.")
    ap.add_argument("--analizza", action="store_true", help="analizza i video nuovi o cambiati (lento)")
    ap.add_argument("--accetta", action="store_true", help="i risultati di adesso diventano quelli attesi")
    ap.add_argument("--rispetto-a", metavar="COMMIT", help="confronta col motore di un commit git")
    ap.add_argument("--fotogrammi", action="store_true", help="fogli di fotogrammi dei tagli cambiati")
    arg = ap.parse_args()

    video = video_di_prova()
    if arg.analizza:
        asyncio.run(analizza(video))
    dopo = asyncio.run(calcola(VideoEngine, video))
    mancanti = len(video) - len(dopo)
    if mancanti:
        print(f"⚠️ {mancanti} video non ancora analizzati (o cambiati): lancia con --analizza.")

    if arg.accetta:
        _scrivi(ATTESI, dopo)
        print(f"Risultati accettati: {len(dopo)} video, "
              f"{sum(len(d['tagli']) for d in dopo.values())} tagli.")
        return

    if arg.rispetto_a:
        prima = asyncio.run(calcola(carica_motore(arg.rispetto_a), video))
        rispetto = f"al motore del commit {arg.rispetto_a}"
    else:
        prima = _leggi(ATTESI, None)
        if prima is None:
            sys.exit("Nessun risultato accettato: lancia prima con --accetta.")
        rispetto = "ai risultati accettati"

    cambi, nuovi, txt_cambiati, uguali = confronta(prima, dopo)
    print(f"\nRispetto {rispetto}: {len(dopo)} video, {uguali + len(cambi)} tagli confrontati, "
          f"{uguali} identici, {len(cambi)} cambiati.")
    for v in nuovi:
        print(f"  ➕ nuovo, senza risultato di riferimento: {os.path.basename(v)}")
    for v in txt_cambiati:
        print(f"  📝 txt modificato, non confrontato: {os.path.basename(v)}")
    for n, (v, k, nome, x, y) in enumerate(cambi, 1):
        t = y[1] if y else x[1]
        print(f"{n:3d}. {os.path.basename(v)[:42]} | stacco {k + 1} ({mmss(t)}) {nome[:34]} | "
              f"{descrivi(x)} → {descrivi(y)}")
    if cambi and arg.fotogrammi:
        fotogrammi(cambi)
    sys.exit(1 if cambi else 0)


if __name__ == "__main__":
    main()
