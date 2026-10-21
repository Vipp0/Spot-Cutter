"""
avvio.py — Punto di partenza del programma compilato (vedi SpotCutter.spec).

Mostra subito la schermata di caricamento con il logo, e solo dopo carica il resto del
programma (main.py, il motore, gli strumenti), che è la parte che richiede tempo. Così tra
il doppio clic e la finestra c'è sempre qualcosa da vedere.
Si può avviare anche "python main.py": parte lo stesso programma, senza schermata.

Con "--installa" fa invece da installatore di un aggiornamento: è la versione nuova, appena
estratta in una cartella temporanea, che aspetta la chiusura della vecchia, ne sostituisce i
file mostrando la stessa schermata con l'avanzamento, e riapre il programma aggiornato.
Gli argomenti (--installa CARTELLA --pid N --esito FILE) non vanno cambiati: li passa la
versione vecchia (aggiornamento.py).
"""
import os
import sys
import time

# Impostazioni di Qt che vanno date prima di creare l'applicazione
os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"
os.environ["QT_FONT_DPI"] = "96"
os.environ["QT_USE_DIRECTWRITE"] = "1"

from PySide6.QtWidgets import QApplication, QWidget, QFrame, QVBoxLayout, QLabel, QProgressBar
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtCore import Qt

from versione import VERSIONE

DURATA_MINIMA = 0.6   # secondi: anche quando il programma è velocissimo, la schermata non è un lampo


def risorsa(nome: str) -> str:
    """Percorso di un file del programma, sia compilato sia avviato dal codice."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, nome)


class SchermataAvvio(QWidget):
    """Riquadro bianco con gli angoli arrotondati: logo, nome, versione e cosa sta facendo."""

    def __init__(self):
        super().__init__(None, Qt.WindowType.SplashScreen | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(380, 360)
        self._partita = time.monotonic()

        fondo = QFrame(self)
        fondo.setObjectName("fondo")
        fondo.setGeometry(0, 0, 380, 360)
        fondo.setStyleSheet("""
            QFrame#fondo { background-color: #FFFFFF; border: 1px solid #E4E7EB; border-radius: 16px; }
            QLabel { background: transparent; border: none; }
            QLabel#versione { color: #8592A0; font-size: 12px; }
            QLabel#stato { color: #52606D; font-size: 12px; }
            QProgressBar { background-color: #E4E7EB; border: none; border-radius: 2px; }
            QProgressBar::chunk { background-color: #E8541E; border-radius: 2px; }
        """)
        lay = QVBoxLayout(fondo)
        lay.setContentsMargins(40, 34, 40, 26)
        lay.setSpacing(0)

        logo = QLabel()
        logo.setPixmap(self._immagine("Spot_cutter_logo.png", 130))
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(logo)
        lay.addSpacing(16)

        nome = QLabel()
        nome.setPixmap(self._immagine("Spot_cutter_text.png", 220))
        nome.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(nome)
        lay.addSpacing(6)

        versione = QLabel(f"Versione {VERSIONE}")
        versione.setObjectName("versione")
        versione.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(versione)
        lay.addStretch()

        self._stato = QLabel("Avvio…")
        self._stato.setObjectName("stato")
        self._stato.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._stato)
        lay.addSpacing(8)

        self._barra = QProgressBar()
        self._barra.setFixedHeight(4)
        self._barra.setTextVisible(False)
        self._barra.setRange(0, 100)
        lay.addWidget(self._barra)

    @staticmethod
    def _immagine(nome: str, larghezza: int) -> QPixmap:
        pm = QPixmap(risorsa(nome))
        if pm.isNull():
            return pm
        # disegnata al doppio e poi dichiarata "ad alta definizione": nitida anche sugli schermi 4K
        pm = pm.scaledToWidth(larghezza * 2, Qt.TransformationMode.SmoothTransformation)
        pm.setDevicePixelRatio(2)
        return pm

    def stato(self, testo: str, percento: int):
        """Aggiorna la riga e la barra; il programma qui è occupato, quindi si ridisegna a mano."""
        self._stato.setText(testo)
        self._barra.setValue(percento)
        QApplication.processEvents()

    def chiudi_quando_pronta(self, finestra):
        """Lascia la schermata almeno DURATA_MINIMA, poi la toglie appena la finestra è visibile."""
        self.stato("Pronto", 100)
        resto = DURATA_MINIMA - (time.monotonic() - self._partita)
        while resto > 0:
            QApplication.processEvents()
            time.sleep(min(resto, 0.02))
            resto = DURATA_MINIMA - (time.monotonic() - self._partita)
        finestra.show()
        finestra.raise_()
        finestra.activateWindow()
        self.close()


def _aspetta_chiusura(pid: int, secondi: float = 120):
    """Aspetta che il processo pid finisca (la versione vecchia che si sta chiudendo)."""
    if sys.platform != "win32" or not pid:
        return
    import ctypes
    k32 = ctypes.windll.kernel32
    h = k32.OpenProcess(0x00100000, False, int(pid))   # SYNCHRONIZE
    if not h:
        return                                         # già chiuso
    try:
        fine = time.monotonic() + secondi
        while time.monotonic() < fine:
            if k32.WaitForSingleObject(h, 100) == 0:   # WAIT_OBJECT_0: chiuso
                return
            QApplication.processEvents()
    finally:
        k32.CloseHandle(h)


def installa(argomenti: list):
    """Sostituisce i file della cartella del programma con quelli di questa versione."""
    import shutil
    import subprocess
    a = {argomenti[i]: argomenti[i + 1] for i in range(0, len(argomenti) - 1, 2)}
    app_dir = a["--installa"]
    esito = a.get("--esito")
    sorgente = os.path.dirname(os.path.abspath(sys.executable))

    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 11))
    schermata = SchermataAvvio()
    schermata.show()
    schermata.raise_()
    schermata.activateWindow()   # il permesso l'ha passato la versione vecchia (passa_primo_piano)
    schermata.stato("Attendo la chiusura di Spot Cutter…", 2)
    _aspetta_chiusura(int(a.get("--pid", 0)))

    def scrivi_esito(testo):
        if esito:
            try:
                os.makedirs(os.path.dirname(esito), exist_ok=True)
                with open(esito, "w", encoding="utf-8") as f:
                    f.write(testo)
            except OSError:
                pass

    vecchio_int = os.path.join(app_dir, "_internal.vecchio")
    vecchio_exe = os.path.join(app_dir, "SpotCutter.exe.vecchio")
    da_copiare = [("SpotCutter.exe", "SpotCutter.exe")]
    for radice, _, files in os.walk(os.path.join(sorgente, "_internal")):
        for f in files:
            rel = os.path.relpath(os.path.join(radice, f), sorgente)
            da_copiare.append((rel, rel))
    if os.path.exists(os.path.join(sorgente, "bin", "README.txt")):
        da_copiare.append((os.path.join("bin", "README.txt"),) * 2)
    totale = sum(os.path.getsize(os.path.join(sorgente, r)) for r, _ in da_copiare) or 1
    try:
        # 1. mette da parte la versione in uso (un file può restare bloccato per qualche istante)
        schermata.stato("Metto da parte la versione precedente…", 5)
        shutil.rmtree(vecchio_int, ignore_errors=True)
        if os.path.exists(vecchio_exe):
            os.remove(vecchio_exe)
        for prova in range(40):
            try:
                os.rename(os.path.join(app_dir, "_internal"), vecchio_int)
                break
            except OSError:
                if prova == 39:
                    raise RuntimeError("la cartella _internal è ancora in uso")
                time.sleep(0.25)
                QApplication.processEvents()
        os.rename(os.path.join(app_dir, "SpotCutter.exe"), vecchio_exe)
        # 2. copia la versione nuova, con l'avanzamento sulla barra
        fatti = 0
        for i, (da, a_rel) in enumerate(da_copiare):
            dest = os.path.join(app_dir, a_rel)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copy2(os.path.join(sorgente, da), dest)
            fatti += os.path.getsize(os.path.join(sorgente, da))
            if i % 5 == 0 or i == len(da_copiare) - 1:
                pc = 5 + int(90 * fatti / totale)
                schermata.stato(f"Installo l'aggiornamento… {int(100 * fatti / totale)}%", pc)
        # 3. tutto a posto: via la versione precedente
        shutil.rmtree(vecchio_int, ignore_errors=True)
        try:
            os.remove(vecchio_exe)
        except OSError:
            pass
        scrivi_esito(f"ok {VERSIONE}")
    except Exception as e:
        # qualcosa non è andato: si rimette la versione di prima
        schermata.stato("Ripristino la versione precedente…", 95)
        if os.path.isdir(vecchio_int):
            shutil.rmtree(os.path.join(app_dir, "_internal"), ignore_errors=True)
            try:
                os.rename(vecchio_int, os.path.join(app_dir, "_internal"))
            except OSError:
                pass
        if os.path.exists(vecchio_exe):
            try:
                if os.path.exists(os.path.join(app_dir, "SpotCutter.exe")):
                    os.remove(os.path.join(app_dir, "SpotCutter.exe"))
                os.rename(vecchio_exe, os.path.join(app_dir, "SpotCutter.exe"))
            except OSError:
                pass
        scrivi_esito(f"errore {e}")
    schermata.stato("Riapro Spot Cutter…", 100)
    proc = subprocess.Popen([os.path.join(app_dir, "SpotCutter.exe")], cwd=app_dir, close_fds=True)
    # la schermata resta finché non compare quella del programma aggiornato, a cui passa il
    # primo piano: senza vuoti in mezzo, Windows non lo dà a un'altra finestra
    import aggiornamento
    aggiornamento.passa_primo_piano(proc.pid)
    aggiornamento.aspetta_finestra(proc.pid, 20, QApplication.processEvents)
    schermata.close()


def avvia():
    if "--installa" in sys.argv:
        installa(sys.argv[sys.argv.index("--installa"):])
        return
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 11))
    schermata = SchermataAvvio()
    schermata.show()
    schermata.activateWindow()
    schermata.stato("Carico il motore di taglio…", 15)

    import main   # la parte lunga: interfaccia, motore, strumenti
    main.avvia(app, schermata)


if __name__ == "__main__":
    avvia()
