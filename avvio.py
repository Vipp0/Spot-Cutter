"""
avvio.py — Punto di partenza del programma compilato (vedi SpotCutter.spec).

Mostra subito la schermata di caricamento con il logo, e solo dopo carica il resto del
programma (main.py, il motore, gli strumenti), che è la parte che richiede tempo. Così tra
il doppio clic e la finestra c'è sempre qualcosa da vedere.
Si può avviare anche "python main.py": parte lo stesso programma, senza schermata.
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


def avvia():
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 11))
    schermata = SchermataAvvio()
    schermata.show()
    schermata.stato("Carico il motore di taglio…", 15)

    import main   # la parte lunga: interfaccia, motore, strumenti
    main.avvia(app, schermata)


if __name__ == "__main__":
    avvia()
