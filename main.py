"""
main.py — Spot Cutter 1.0  (PySide6)
Conversione completa da Flet a PySide6.
video_engine.py e utils.py rimangono invariati.

Installazione dipendenze:
    pip install PySide6

Il VideoEngine gira in un QThread dedicato tramite segnali Qt.
La UI non si congela mai durante l'elaborazione.
"""
import json
import os
import sys
import re
import time
import shutil
import asyncio
import threading
import subprocess
import glob

from datetime import datetime

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QTextEdit, QScrollArea,
    QFrame, QSizePolicy, QDialog, QDialogButtonBox, QFileDialog,
    QMessageBox, QProgressBar, QSplitter, QStyle, QPlainTextEdit,
    QTableWidget, QTableWidgetItem, QHeaderView
)
from PySide6.QtCore import (
    Qt, QThread, QObject, Signal, Slot, QTimer, QSize, QSettings
)
from PySide6.QtGui import (
    QFont, QColor, QPalette, QIcon, QTextCursor, QPixmap
)

# ── GESTIONE PERCORSI FFmpeg ───────────────────────────────────────────────
if getattr(sys, 'frozen', False):
    base_path = os.path.dirname(sys.executable)
else:
    base_path = os.path.dirname(os.path.abspath(__file__))

for exe in ("ffmpeg.exe", "ffprobe.exe"):
    if os.path.exists(os.path.join(base_path, exe)):
        os.environ["PATH"] += os.pathsep + base_path
        break

# ── IMPORT MODULI PROGETTO ─────────────────────────────────────────────────
from utils import (
    ESTENSIONI_VIDEO, extract_date_info,
    get_unique_filename, get_video_duration,
    parse_settings, load_settings, save_settings,
)
from video_engine import VideoEngine

def resource_path(relative_path):
    """ Ottiene il percorso assoluto della risorsa, per l'EXE e per il debug """
    # getattr cerca l'attributo e, se non lo trova, usa il secondo parametro (os.path.abspath("."))
    base_path = getattr(sys, '_MEIPASS', os.path.abspath("."))
    return os.path.join(base_path, relative_path)


# ══════════════════════════════════════════════════════════════════════════
# WORKER — gira il VideoEngine in un thread separato
# I segnali Qt garantiscono aggiornamenti thread-safe alla UI
# ══════════════════════════════════════════════════════════════════════════
class EngineWorker(QObject):
    """
    Wrappa VideoEngine in un QObject per girare in un QThread.
    Comunica con la UI tramite segnali Qt (thread-safe per definizione).
    """
    # Segnali emessi verso la UI
    sig_log            = Signal(str, str)   # (messaggio, colore_hex)
    sig_progress       = Signal(float, str) # (valore 0-1, label)
    sig_global_progress= Signal(int, int)   # (index, total)
    sig_status         = Signal(int, str, str)  # (idx, testo, colore)
    sig_stats_update   = Signal()
    sig_finished       = Signal(bool, float)    # (successo, elapsed)
    sig_queue_update   = Signal()               # richiede render_queue

    def __init__(self, state: dict, settings: tuple):
        super().__init__()
        self.state    = state
        self.settings = settings  # (crf, cusc_i, cusc_f, toll, bth, bdur)

    @Slot()
    def run(self):
        """Punto di ingresso del thread — lancia il loop asyncio."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._run_async())
        finally:
            loop.close()

    async def _run_async(self):
        v_crf, v_cusc_i, v_cusc_f, v_toll, v_bth, v_bdur = self.settings

        # Callback async che emettono segnali Qt (chiamabili da asyncio)
        async def cb_log(msg, color="white"):
            self.sig_log.emit(msg, color)

        async def cb_progress(value, label):
            self.sig_progress.emit(value, label)

        async def cb_global(index, total):
            self.sig_global_progress.emit(index, total)

        async def cb_status(idx, status, color):
            self.sig_status.emit(idx, status, color)

        async def cb_stats():
            self.sig_stats_update.emit()

        self.state["update_stats_cb"] = cb_stats

        engine = VideoEngine(log_cb=cb_log, progress_cb=cb_progress)

        queue = list(self.state["queue_files"])
        self.state["start_time"] = time.time()
        self.state["stats_counts"] = {k: 0 for k in self.state["stats_counts"]}

        await cb_global(0, len(queue))

        await engine.process_all(
            queue, self.state,
            (v_crf, v_cusc_i, v_cusc_f, v_toll, v_bth, v_bdur),
            status_cb=cb_status,
            global_progress_cb=cb_global,
        )

        elapsed  = time.time() - self.state["start_time"]
        successo = self.state["running"]
        self.state["running"] = False
        self.sig_finished.emit(successo, elapsed)
        self.sig_queue_update.emit()


class YTWorker(QObject):
    """Worker per il download YouTube."""
    sig_log      = Signal(str, str)
    sig_progress = Signal(float, str)
    sig_finished = Signal(list)   # lista di (vid, txt) o lista vuota
    
    def __init__(self, url: str, output_dir: str, state: dict, direct_download: bool = False):
        super().__init__()
        self.url            = url
        self.output_dir     = output_dir
        self.state          = state
        self.direct_download = direct_download

    @Slot()
    def run(self):
        # 1. RIMOSSO: self.state["running"] = True 
        # Lo stato deve essere gestito solo dalla UI (es. in _on_yt_download)

        if not hasattr(self, 'result'):
            self.result = []
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # Eseguiamo il download / analisi
            # La logica di recupero file esistente è già gestita dentro _run_async
            loop.run_until_complete(self._run_async())

        except Exception as e:
            if hasattr(self, 'sig_log'):
                self.sig_log.emit(f"❌ Errore critico download: {str(e)}", "red")
        
        finally:
            # Chiusura pulita del loop
            try:
                if loop.is_running():
                    loop.stop()
                loop.close()
            except:
                pass
            
            # 2. RIMOSSO: self.state["running"] = False
            # Sarà la funzione _on_yt_finished nella UI a rimetterlo a False
            
            # 3. Invio dei risultati
            if hasattr(self, 'sig_finished'):
                # Passiamo il risultato trovato (o una lista vuota)
                # Non resettiamo self.result qui per sicurezza finché il segnale non è partito
                self.sig_finished.emit(self.result if self.result else [])
            
            # 4. Pulizia finale dell'istanza
            self.result = []

    async def _run_async(self):
        async def cb_log(msg, color="white"):
            self.sig_log.emit(msg, color)

        async def cb_progress(value, label):
            self.sig_progress.emit(value, label)

        engine = VideoEngine(log_cb=cb_log, progress_cb=cb_progress)
        
        # 1. Chiamiamo il download e ci fidiamo SOLO del motore
        # Il motore ora gestisce internamente sia il download nuovo 
        # sia il caso "già scaricato" se usiamo la logica corretta.
        self.result = await engine.download_youtube(
            self.url, self.output_dir, self.state,
            generate_txt=not self.direct_download
        )
        
        if not self.result:
            await cb_log("❌ Operazione fallita o annullata.", "red")


# ══════════════════════════════════════════════════════════════════════════
# WIDGET CARD — singola riga della coda
# ══════════════════════════════════════════════════════════════════════════
class VideoCard(QFrame):
    sig_move_up   = Signal(int)
    sig_move_down = Signal(int)
    sig_delete    = Signal(int)
    sig_edit_txt  = Signal(str)
    sig_edit_date = Signal(int)
    sig_cut       = Signal(str)

    def __init__(self, idx: int, vid: str, has_txt: bool,
                 status_text: str, status_color: str,
                 is_first: bool, is_last: bool,
                 is_running: bool, parent=None):
        super().__init__(parent)
        self.idx = idx
        self.vid = vid

        self.setObjectName("VideoCard")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        # Layout principale
        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 12, 15, 12)
        layout.setSpacing(15)

        # 1. Badge numero
        badge = QLabel(str(idx + 1))
        badge.setObjectName("badge_index")
        badge.setFixedWidth(25)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(badge)

        # 2. Colonna Titolo e Pillola
        text_col = QVBoxLayout()
        text_col.setSpacing(6)

        title_lbl = QLabel(vid)
        title_lbl.setObjectName("card_title")
        title_lbl.setToolTip(vid)
        text_col.addWidget(title_lbl)

        # Contenitore per la pillola interattiva
        self.pill_container = QWidget()
        pill_layout = QHBoxLayout(self.pill_container)
        pill_layout.setContentsMargins(0, 0, 0, 0)
        pill_layout.setSpacing(0) 

        # PARTE TXT (Sinistra)
        self.txt_part = QLabel()
        self.txt_part.setCursor(Qt.CursorShape.PointingHandCursor)
        self.txt_part.setObjectName("pill_part_txt")
        
        # PARTE DATA (Destra)
        self.date_part = QLabel()
        self.date_part.setCursor(Qt.CursorShape.PointingHandCursor)
        self.date_part.setObjectName("pill_part_date")

        pill_layout.addWidget(self.txt_part)
        pill_layout.addWidget(self.date_part)
        text_col.addWidget(self.pill_container, 0, Qt.AlignmentFlag.AlignLeft)

        layout.addLayout(text_col, stretch=1)

        # 3. Bottoni di controllo
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        def _icon_btn(text, obj_name, tooltip, enabled=True):
            b = QPushButton(text)
            b.setObjectName(obj_name)
            # Aumentiamo leggermente la dimensione per farli stare comodi
            b.setFixedSize(34, 34) 
            b.setToolTip(tooltip)
            b.setEnabled(enabled)
            # Importante: PointingHandCursor per far capire che è cliccabile
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            return b

        # Usiamo simboli PIENI (Solid) per le frecce e una X pesante per cancella
        # (▲, ▼, ✕ sono simboli Unicode Standard con molto corpo)
        self.btn_up   = _icon_btn("▲", "btn_card_move", "Sposta su", not is_first and not is_running)
        self.btn_down = _icon_btn("▼", "btn_card_move", "Sposta giù", not is_last and not is_running)
        self.btn_cut  = _icon_btn("✂️", "btn_card_cut", "Tagli manuali", not is_running)
        self.btn_del  = _icon_btn("✕", "btn_card_delete", "Rimuovi", not is_running)

        self.btn_up.clicked.connect(lambda: self.sig_move_up.emit(self.idx))
        self.btn_down.clicked.connect(lambda: self.sig_move_down.emit(self.idx))
        self.btn_cut.clicked.connect(lambda: self.sig_cut.emit(self.vid))
        self.btn_del.clicked.connect(lambda: self.sig_delete.emit(self.idx))

        btn_layout.addWidget(self.btn_up)
        btn_layout.addWidget(self.btn_down)
        btn_layout.addWidget(self.btn_cut)
        btn_layout.addWidget(self.btn_del)
        layout.addLayout(btn_layout)

        # Impostazione iniziale dei testi e degli stili
        self.txt_part.setText(f"📄 {'TXT OK' if has_txt else 'NO TXT'}")
        self.set_status(status_text, status_color)
        
        # Click eventi
        self.txt_part.mousePressEvent = lambda e: self.sig_edit_txt.emit(self.vid)
        self.date_part.mousePressEvent = lambda e: self.sig_edit_date.emit(self.idx)

    def set_status(self, text: str, color: str):
        """Aggiorna i testi e decide i colori delle due metà della pillola con palette Soft."""
        # Estraiamo la parte della data
        data_display = text.split("Data:")[-1].strip() if "Data:" in text else text
        self.date_part.setText(f"📅 {data_display}")
        
        # Recuperiamo lo stato del TXT dal widget stesso
        has_txt = "TXT OK" in self.txt_part.text()
        
        # --- NUOVA LOGICA COLORI SOFT (v0.86) ---
        COLOR_VERDE   = "#4CAF50" # Verde mela soft
        COLOR_ROSSO   = "#EF5350" # Rosso corallo delicato
        COLOR_ARANCIO = "#FFB74D" # Arancio pesca
        COLOR_BLU     = "#42A5F5" # Blu pastello
        
        # 1. Sinistra (TXT): Verde se OK, Rosso se manca
        txt_bg = COLOR_VERDE if has_txt else COLOR_ROSSO
        
        # 2. Destra (DATA): Basata sulle icone
        if "✅" in text:
            date_bg = COLOR_VERDE
        elif "⚠️" in text:
            date_bg = COLOR_ARANCIO
        elif "⛔" in text or "MANCANTE" in text or "Invalida" in text:
            date_bg = COLOR_ROSSO
        else:
            # Gestione del fallback per il colore passato (se è blu o grigio, lo addolciamo)
            if color.lower() in ["blue", "#2196f3"]:
                date_bg = COLOR_BLU
            else:
                date_bg = color 

        # Applichiamo lo stile CSS (Mantenendo i bordi per l'effetto "badge unico")
        common = "padding: 3px 10px; color: white; font-weight: 800; font-size: 10px; font-family: 'Segoe UI';"
        
        self.txt_part.setStyleSheet(
            f"background-color: {txt_bg}; {common} "
            "border-top-left-radius: 6px; border-bottom-left-radius: 6px; "
            "border-top-right-radius: 0px; border-bottom-right-radius: 0px;"
        )
        self.date_part.setStyleSheet(
            f"background-color: {date_bg}; {common} "
            "border-top-left-radius: 0px; border-bottom-left-radius: 0px; "
            "border-top-right-radius: 6px; border-bottom-right-radius: 6px;"
        )

# ══════════════════════════════════════════════════════════════════════════
# FINESTRA IMPOSTAZIONI
# ══════════════════════════════════════════════════════════════════════════
class SettingsDialog(QDialog):
    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Impostazioni Avanzate")
        self.setFixedSize(780, 400)
        self.setModal(True)

        self._entries = {}
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        def _group(title, fields):
            """Crea un gruppo con bordo e titolo."""
            box = QFrame()
            box.setObjectName("settings_group")
            box.setFrameShape(QFrame.Shape.StyledPanel)
            grp_layout = QVBoxLayout(box)
            grp_layout.setSpacing(6)
            grp_layout.setContentsMargins(12, 8, 12, 8)

            lbl_title = QLabel(title)
            lbl_title.setObjectName("settings_group_title")
            lbl_title.setStyleSheet("font-weight: bold; font-size: 11px; color: #1565C0;")
            grp_layout.addWidget(lbl_title)

            for label, key, tooltip in fields:
                row = QHBoxLayout()
                lbl = QLabel(label)
                lbl.setFixedWidth(170)
                lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if tooltip:
                    lbl.setToolTip(tooltip)
                entry = QLineEdit(str(settings.get(key, "")))
                entry.setFixedWidth(100)
                if tooltip:
                    entry.setToolTip(tooltip)
                row.addWidget(lbl)
                row.addWidget(entry)
                row.addStretch()
                grp_layout.addLayout(row)
                self._entries[key] = entry

            return box

        # Layout a due colonne
        cols = QHBoxLayout()
        cols.setSpacing(12)

        # Colonna sinistra
        col_sx = QVBoxLayout()
        col_sx.setSpacing(12)
        col_sx.addWidget(_group("🎬  QUALITÀ OUTPUT", [
            ("Qualità CRF (0-51)", "crf",
             "Qualità di ricodifica dei tagli finali. 0=lossless, 51=pessima. Default: 20"),
        ]))
        col_sx.addWidget(_group("⬛  BLACKDETECT", [
            ("Sensibilità Nero",     "bth",
             "Soglia di luminosità per considerare un frame nero (0-1). Default: 0.1"),
            ("Durata Min. Nero (s)", "bdur",
             "Durata minima in secondi per considerare una sequenza come nero. Default: 0.1"),
        ]))
        col_sx.addWidget(_group("⚡  PRESTAZIONI", [
            ("Tagli paralleli (0=auto)", "parallel_cuts",
             "Numero di tagli FFmpeg simultanei. 0=automatico (metà core). Default: 0"),
        ]))
        col_sx.addStretch()

        # Colonna destra
        col_dx = QVBoxLayout()
        col_dx.setSpacing(12)
        col_dx.addWidget(_group("✂️  TAGLIO", [
            ("Cuscinetto Inizio (s)", "cusc_i",
             "Anticipo in secondi rispetto al punto di taglio iniziale. Default: 0.05"),
            ("Cuscinetto Fine (s)",   "cusc_f",
             "Ritardo in secondi rispetto al punto di taglio finale. Default: 0.12"),
            ("Tolleranza Nero (s)",   "toll",
             "Distanza massima in secondi tra il timestamp TXT e il nero rilevato. Default: 2.0"),
        ]))
        col_dx.addWidget(_group("🔇  SILENCEDETECT", [
            ("Soglia Silenzio (dB)",     "silence_thresh",
             "Livello audio sotto cui si considera silenzio. Es: -35dB. Default: -35dB"),
            ("Durata Min. Silenzio (s)", "silence_dur",
             "Durata minima in secondi per considerare un tratto come silenzio. Default: 0.1"),
        ]))
        col_dx.addStretch()

        cols.addLayout(col_sx)
        cols.addLayout(col_dx)
        layout.addLayout(cols)

        # Bottoni
        btn_row = QHBoxLayout()
        btn_save  = QPushButton("💾 Salva")
        btn_reset = QPushButton("Ripristina default")
        btn_save.setObjectName("btn_dlg_save")
        btn_reset.setObjectName("btn_dlg_reset")
        btn_save.clicked.connect(self.accept)
        btn_reset.clicked.connect(self._reset)
        btn_row.addWidget(btn_save)
        btn_row.addWidget(btn_reset)
        btn_row.addStretch()
        layout.addLayout(btn_row)

    def _reset(self):
        defs = {"crf": "20", "cusc_i": "0.05", "cusc_f": "0.12",
                "toll": "2.0", "bth": "0.1", "bdur": "0.1",
                "parallel_cuts": "0", "silence_thresh": "-35dB",
                "silence_dur": "0.1"}
        for k, e in self._entries.items():
            e.setText(defs[k])

    def get_values(self) -> dict:
        return {k: e.text() for k, e in self._entries.items()}


# ══════════════════════════════════════════════════════════════════════════
# FINESTRA EDITOR TXT
# ══════════════════════════════════════════════════════════════════════════
class TxtEditorDialog(QDialog):
    def __init__(self, title: str, content: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(900, 680)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        self._editor = QTextEdit()
        self._editor.setObjectName("txt_editor")
        self._editor.setPlainText(content)
        layout.addWidget(self._editor)

        btn_row = QHBoxLayout()
        btn_save   = QPushButton("💾 Salva modifiche")
        btn_cancel = QPushButton("Annulla")
        btn_save.setObjectName("btn_txt_save")
        btn_cancel.setObjectName("btn_dlg_cancel")
        btn_save.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_save)
        btn_row.addWidget(btn_cancel)
        btn_row.addStretch()
        layout.addLayout(btn_row)

    def get_text(self) -> str:
        return self._editor.toPlainText()


# ══════════════════════════════════════════════════════════════════════════
# FINESTRA EDITOR DATA
# ══════════════════════════════════════════════════════════════════════════
class DateEditorDialog(QDialog):
    def __init__(self, vid_name, current_date, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Correggi Data")
        self.setFixedSize(350, 180) # Leggermente più grande per l'errore
        
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Inserisci la data corretta per:\n{vid_name}"))
        
        self.date_input = QLineEdit()
        self.date_input.setInputMask("99-99-9999") 
        # Puliamo la data se contiene placeholder strani
        clean_date = current_date if current_date and "-" in current_date else "01-01-2000"
        self.date_input.setText(clean_date)
        self.date_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.date_input.setStyleSheet("font-size: 14px; font-weight: bold; padding: 5px;")
        layout.addWidget(self.date_input)

        # Etichetta per messaggi di errore (inizialmente vuota)
        self.error_lbl = QLabel("")
        self.error_lbl.setStyleSheet("color: #FF3B30; font-size: 10px;")
        self.error_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.error_lbl)
        
        btn_layout = QHBoxLayout()
        btn_ok = QPushButton("Salva")
        btn_ok.setObjectName("btn_save_date") # Per stile eventuale
        btn_ok.clicked.connect(self.validate_and_accept) # <--- CAMBIATO QUI
        
        btn_cancel = QPushButton("Annulla")
        btn_cancel.clicked.connect(self.reject)
        
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_ok)
        layout.addLayout(btn_layout)

    def validate_and_accept(self):
        """Controlla se la data esiste davvero prima di chiudere."""
        date_str = self.date_input.text()
        try:
            # Prova a trasformare il testo in una data reale
            datetime.strptime(date_str, "%d-%m-%Y")
            # Se ci riesce, la data è valida!
            self.accept()
        except ValueError:
            # Se fallisce (es. 31-02-2024), mostriamo l'errore
            self.date_input.setStyleSheet("border: 2px solid #FF3B30; font-size: 14px; padding: 5px;")
            self.error_lbl.setText("⚠️ Data non valida! Controlla giorno e mese.")

    def get_date(self):
        return self.date_input.text()

# ══════════════════════════════════════════════════════════════════════════
# DIALOG STORICO ELABORAZIONI
# ══════════════════════════════════════════════════════════════════════════
class StoricoDialog(QDialog):
    def __init__(self, storico_path: str, parent=None):
        super().__init__(parent)
        self.storico_path = storico_path
        self.setWindowTitle("📋 Storico elaborazioni")
        self.setMinimumSize(780, 480)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # Titolo
        lbl = QLabel("Storico dei video elaborati — clicca 🗑 per rimuovere una voce")
        lbl.setStyleSheet("font-size: 12px; color: grey;")
        layout.addWidget(lbl)

        # Tabella
        self._table = QTableWidget()
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels(["Data", "File", "Canale", "Spot", ""])
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        layout.addWidget(self._table)

        # Bottoni
        btn_row = QHBoxLayout()
        btn_close = QPushButton("Chiudi")
        btn_close.clicked.connect(self.accept)
        btn_row.addStretch()
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

        self._load()

    def _load(self):
        """Carica lo storico dalla tabella."""
        self._table.setRowCount(0)
        if not os.path.exists(self.storico_path):
            return
        try:
            with open(self.storico_path, "r", encoding="utf-8") as f:
                storico = json.load(f)
        except Exception:
            return

        for vid, entry in sorted(storico.items(),
                                  key=lambda x: x[1].get("data_elaborazione", ""),
                                  reverse=True):
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setItem(row, 0, QTableWidgetItem(entry.get("data_elaborazione", "?")))
            self._table.setItem(row, 1, QTableWidgetItem(vid))
            self._table.setItem(row, 2, QTableWidgetItem(entry.get("canale", "")))
            self._table.setItem(row, 3, QTableWidgetItem(str(entry.get("n_spot", ""))))

            # Bottone elimina riga
            btn_del = QPushButton("🗑")
            btn_del.setFixedSize(30, 28)
            btn_del.setToolTip("Rimuovi dal storico")
            btn_del.clicked.connect(lambda checked, v=vid: self._delete_entry(v))
            self._table.setCellWidget(row, 4, btn_del)

    def _delete_entry(self, vid: str):
        """Rimuove una voce dallo storico."""
        try:
            with open(self.storico_path, "r", encoding="utf-8") as f:
                storico = json.load(f)
            storico.pop(vid, None)
            with open(self.storico_path, "w", encoding="utf-8") as f:
                json.dump(storico, f, indent=2, ensure_ascii=False)
        except Exception:
            pass
        self._load()  # ricarica la tabella


# ══════════════════════════════════════════════════════════════════════════
# DIALOG TAGLI MANUALI CON BLACKDETECT
# ══════════════════════════════════════════════════════════════════════════
class BlackdetectDialog(QDialog):
    """
    Dialog per la creazione/modifica manuale del TXT degli spot.
    Lancia il blackdetect sul file originale e mostra i timestamp
    come bottoni cliccabili. Il click inserisce il timestamp nell'editor.
    """
    _sig_blacks_ready = Signal(list)  # segnale thread-safe per risultato blackdetect

    def __init__(self, vid_path: str, txt_path: str, settings: dict, parent=None):
        super().__init__(parent)
        self.vid_path  = vid_path
        self.txt_path  = txt_path
        self.settings  = settings
        self.setWindowTitle(f"Tagli manuali — {os.path.basename(vid_path)}")
        self.setMinimumSize(820, 520)
        self.setModal(True)

        # Layout principale orizzontale: sinistra=neri, destra=editor
        root = QHBoxLayout(self)
        root.setSpacing(16)
        root.setContentsMargins(16, 16, 16, 16)

        # ── COLONNA SINISTRA: lista neri ──────────────────────────────────
        left = QVBoxLayout()
        left.setSpacing(8)

        lbl_neri = QLabel("🕳️ Neri trovati — clicca per inserire")
        lbl_neri.setStyleSheet("font-weight: bold; font-size: 12px;")
        left.addWidget(lbl_neri)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)   # modalità indeterminata (spinning)
        self._progress.setTextVisible(False)
        self._progress.setFixedHeight(6)
        left.addWidget(self._progress)

        self._status_lbl = QLabel("Analisi in corso...")
        self._status_lbl.setStyleSheet("color: grey; font-size: 11px;")
        left.addWidget(self._status_lbl)

        # Area scrollabile per i bottoni timestamp
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFixedWidth(230)
        scroll.setStyleSheet("border: none;")
        self._btn_container = QWidget()
        self._btn_layout    = QVBoxLayout(self._btn_container)
        self._btn_layout.setSpacing(5)
        self._btn_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(self._btn_container)
        left.addWidget(scroll, stretch=1)

        root.addLayout(left)

        # ── COLONNA DESTRA: editor TXT ────────────────────────────────────
        right = QVBoxLayout()
        right.setSpacing(8)

        lbl_editor = QLabel("📄 Editor TXT — scrivi il nome dopo il timestamp")
        lbl_editor.setStyleSheet("font-weight: bold; font-size: 12px;")
        right.addWidget(lbl_editor)

        self._editor = QPlainTextEdit()
        self._editor.setPlaceholderText(
            "Clicca un timestamp a sinistra per inserirlo,\n"
            "poi scrivi il nome dello spot.\n\n"
            "Formato: 00:01:23 - Nome Spot"
        )
        self._editor.setStyleSheet("font-family: 'Consolas', monospace; font-size: 12px;")

        # Carica il TXT esistente se presente
        if os.path.exists(txt_path):
            try:
                with open(txt_path, "r", encoding="utf-8") as f:
                    self._editor.setPlainText(f.read())
            except Exception:
                pass
        else:
            self._editor.setPlainText("00:00 - ")
            # Posiziona il cursore alla fine così l'utente scrive subito il nome
            cursor = self._editor.textCursor()
            cursor.movePosition(cursor.MoveOperation.End)
            self._editor.setTextCursor(cursor)

        right.addWidget(self._editor, stretch=1)

        # Bottoni salva/annulla
        btn_row = QHBoxLayout()
        btn_save   = QPushButton("💾 Salva TXT")
        btn_cancel = QPushButton("Annulla")
        btn_save.setObjectName("btn_txt_save")
        btn_cancel.setObjectName("btn_dlg_cancel")
        btn_save.clicked.connect(self._save)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_save)
        btn_row.addWidget(btn_cancel)
        btn_row.addStretch()
        right.addLayout(btn_row)

        root.addLayout(right, stretch=1)

        # Collega il segnale thread-safe al metodo UI
        self._sig_blacks_ready.connect(self._on_blacks_ready)
        # Avvia il blackdetect in background dopo che il dialog è visibile
        QTimer.singleShot(100, self._run_blackdetect)

    def _run_blackdetect(self):
        """Lancia il blackdetect in un thread separato per non bloccare la UI."""
        import threading

        bth  = self.settings.get("bth",  "0.1")
        bdur = self.settings.get("bdur", "0.1")

        def _worker():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                from video_engine import VideoEngine

                async def _nop(*_): pass
                engine   = VideoEngine(log_cb=_nop, progress_cb=_nop)
                b_starts = loop.run_until_complete(
                    engine.detect_blacks_standalone(self.vid_path, bth, bdur)
                )
                # Torna sulla UI via Signal Qt (thread-safe)
                self._sig_blacks_ready.emit(b_starts)
            except Exception as e:
                self._sig_blacks_ready.emit([])
            finally:
                loop.close()

        threading.Thread(target=_worker, daemon=True).start()

    def _on_blacks_ready(self, b_starts: list[float]):
        """Chiamato sul thread UI quando il blackdetect è finito."""
        self._progress.setRange(0, 1)
        self._progress.setValue(1)

        if not b_starts:
            self._status_lbl.setText("Nessun nero trovato.")
            return

        self._status_lbl.setText(f"{len(b_starts)} neri trovati — clicca per inserire")

        for ts in b_starts:
            # Converte secondi in HH:MM:SS
            h  = int(ts) // 3600
            m  = (int(ts) % 3600) // 60
            s  = int(ts) % 60
            ts_str = f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"

            btn = QPushButton(f"+ {ts_str}")
            btn.setStyleSheet(
                "text-align: left; padding: 4px 8px; "
                "background: #E3F2FD; border: 1px solid #90CAF9; "
                "border-radius: 4px; font-family: 'Consolas', monospace;"
            )
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            # Cattura ts_str per valore nel lambda
            btn.clicked.connect(lambda checked, t=ts_str: self._insert_timestamp(t))
            self._btn_layout.addWidget(btn)

    def _insert_timestamp(self, ts_str: str):
        """Inserisce il timestamp nella riga corrente dell'editor."""
        cursor = self._editor.textCursor()
        # Va all'inizio della riga corrente
        cursor.movePosition(cursor.MoveOperation.StartOfLine)
        cursor.movePosition(cursor.MoveOperation.EndOfLine,
                            cursor.MoveMode.KeepAnchor)
        # Se la riga è vuota inserisce il timestamp, altrimenti va a capo
        line_text = cursor.selectedText().strip()
        if line_text:
            # Riga non vuota: vai alla fine e aggiungi nuova riga
            cursor.movePosition(cursor.MoveOperation.EndOfLine)
            cursor.insertText(f"\n{ts_str} - ")
        else:
            # Riga vuota: inserisci qui
            cursor.insertText(f"{ts_str} - ")
        self._editor.setTextCursor(cursor)
        self._editor.setFocus()

    def _save(self):
        """Salva il contenuto dell'editor nel file TXT."""
        txt = self._editor.toPlainText().strip()
        try:
            with open(self.txt_path, "w", encoding="utf-8") as f:
                f.write(txt)
            self.accept()
        except Exception as e:
            QMessageBox.warning(self, "Errore salvataggio",
                                f"Impossibile salvare il file:\n{e}")


# ══════════════════════════════════════════════════════════════════════════
# FINESTRA PRINCIPALE
# ══════════════════════════════════════════════════════════════════════════
class SpotCutterApp(QMainWindow):
    
    # Segnali interni per aggiornamenti thread-safe (emessi dai Worker)
    _sig_log             = Signal(str, str)
    _sig_progress        = Signal(float, str)
    _sig_global_progress = Signal(int, int)
    _sig_status          = Signal(int, str, str)
    _sig_stats           = Signal()
    _sig_finished        = Signal(bool, float)
    _sig_render_queue    = Signal()
    _sig_yt_finished     = Signal(list)
    _sig_yt_info         = Signal(str, object)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Spot Cutter - Organizzatore Spot TV")
        self.setWindowIcon(QIcon(resource_path("Spot_Cutter.ico")))
        self.resize(1200, 900)
        self.setMinimumSize(1000, 700)

        # 1. Inizializza lo STATO (Incluso il caricamento impostazioni)
        base_folder = os.path.dirname(os.path.abspath(__file__))
        # Usa la cartella Video di Windows come default, con fallback a Documenti
        _home = os.path.expanduser("~")
        _videos = os.path.join(_home, "Videos")
        _docs   = os.path.join(_home, "Documents")
        _base   = _videos if os.path.exists(_videos) else _docs if os.path.exists(_docs) else _home
        default_path = os.path.join(_base, "Libreria Spot")
        
        self.settings_storage = QSettings("MioApp", "SpotOrganizer")
        self.work_dir = str(self.settings_storage.value("work_dir", default_path))

        self.state = {
            "running":       False,
            "queue_files":   [],
            "stats_counts":  {"spot": 0, "promo": 0, "bumper": 0,
                              "annunci": 0, "cartelli": 0,
                              "videosigle": 0, "telegiornali": 0,
                              "natale": 0},
            "start_time":    0,
            "current_dir":   "",
            "status_labels": {}, 
            "work_dir":      self.work_dir
        }
        self._s = load_settings()

        # 2. Carica lo STILE (usando resource_path per l'EXE)
        self.load_stylesheet(resource_path("style.qss"))

        # 3. Costruzione UI
        self._build_ui()
        self.setAcceptDrops(True)

        # 4. Connessione SEGNALI (Spostati qui per evitare doppioni)
        self._sig_log.connect(self._on_log)
        self._sig_progress.connect(self._on_progress)
        self._sig_global_progress.connect(self._on_global_progress)
        self._sig_status.connect(self._on_status)
        self._sig_stats.connect(self._on_stats_update)
        self._sig_finished.connect(self._on_finished)
        self._sig_render_queue.connect(self.render_queue)
        self._sig_yt_finished.connect(self._on_yt_finished)
        self._sig_yt_info.connect(self._yt_after_info) # Aggiunto qui

        # 5. Threading
        self._worker_thread = None
        self._yt_thread     = None 

        # 6. Check iniziali
        if not os.path.exists(self.work_dir):
            try: os.makedirs(self.work_dir)
            except: pass

        QTimer.singleShot(800, self._startup_checks) 

    def _on_open_storico(self):
        """Apre il dialog dello storico elaborazioni."""
        storico_path = os.path.join(
            self.state.get("work_dir", self.state.get("current_dir", "")),
            "storico.json"
        )
        dlg = StoricoDialog(storico_path, parent=self)
        dlg.exec()
        # Ricarica la coda per aggiornare eventuali voci rimosse
        self.render_queue()

    def _on_choose_work_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Seleziona cartella di destinazione", self.work_dir)
        if d:
            self.work_dir = d
            self.state["work_dir"] = d
            # Aggiorna il testo del bottone per mostrare la nuova cartella
            self._btn_work_dir.setText(f"📂  {os.path.basename(d) if os.path.basename(d) else d}")
            self._on_log(f"Cartella destinazione cambiata in: {d}", "cyan")
            self.settings_storage.setValue("work_dir", d)


    def load_stylesheet(self, file_name):
        """Legge il file .qss e lo applica forzando il refresh della grafica"""
        # MODIFICA: Usa il base_path per trovare il file .qss ovunque sia l'app
        # file_name può essere già un percorso assoluto (da resource_path)
        # oppure un nome file semplice — gestiamo entrambi i casi
        full_path = file_name if os.path.isabs(file_name) else os.path.join(base_path, file_name)
        try:
            if os.path.exists(full_path):
                with open(full_path, "r", encoding="utf-8") as f:
                    style_data = f.read()
                    self.setStyleSheet(style_data)
                    
                    # FORZA IL REFRESH: Questo dice a Qt di rileggere i nomi degli oggetti
                    self.style().unpolish(self)
                    self.style().polish(self)
                    print(f"✅ Stile caricato correttamente da {file_name}")
            else:
                print(f"⚠️ Attenzione: {file_name} non trovato!")
        except Exception as e:
            print(f"❌ Errore nel caricamento dello stile: {e}")

        # ── Drag & Drop Logic ──────────────────────────────────────────────────
    def dragEnterEvent(self, event):
        """Si attiva quando trascini dei file sopra la finestra."""
        if event.mimeData().hasUrls():
            # Controlliamo se almeno uno dei file è un video supportato
            urls = event.mimeData().urls()
            if any(url.toLocalFile().lower().endswith(ESTENSIONI_VIDEO) for url in urls):
                event.acceptProposedAction()

    def dragMoveEvent(self, event):
        """Necessario per confermare l'accettazione durante il movimento."""
        event.acceptProposedAction()

    def dropEvent(self, event):
        """Si attiva quando rilasci i file."""
        files = [u.toLocalFile() for u in event.mimeData().urls()]
        video_files = [f for f in files if f.lower().endswith(ESTENSIONI_VIDEO)]
        
        if not video_files:
            return

        # Aggiorna sempre current_dir con la cartella del primo video trascinato
        self.state["current_dir"] = os.path.dirname(video_files[0])
        os.chdir(self.state["current_dir"])

        added_count = 0
        for path in video_files:
            fname = os.path.basename(path)
            # Evitiamo duplicati in coda
            if not any(q[0] == fname for q in self.state["queue_files"]):
                d = os.path.dirname(path)
                base = os.path.splitext(fname)[0]
                txt_name = base + ".txt"
                has_txt = os.path.exists(os.path.join(d, txt_name))
                
                self.state["queue_files"].append((
                    fname, 
                    txt_name if has_txt else None, 
                    None
                ))
                added_count += 1

        if added_count > 0:
            self._on_log(f"Trascinati {added_count} video nella coda.", "cyan")
            self.render_queue()

    # ══════════════════════════════════════════════════════════════════════
    # COSTRUZIONE UI
    # ══════════════════════════════════════════════════════════════════════

    def _build_ui(self):
        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self._build_sidebar(root_layout)
        self._build_main_area(root_layout)

    # ── Sidebar ───────────────────────────────────────────────────────────
    def _build_sidebar(self, parent_layout):
        sb = QWidget()
        sb.setObjectName("sidebar")
        sb.setFixedWidth(270)
        layout = QVBoxLayout(sb)
        layout.setContentsMargins(15, 25, 15, 20)
        layout.setSpacing(8)
       
        # Logo centrato
        lbl_logo = QLabel()
        lbl_logo.setPixmap(
            QPixmap(resource_path("Spot_cutter_logo.png")).scaled(
                78, 80,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
        )
        lbl_logo.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(lbl_logo)

        # Scritta centrata sotto il logo
        lbl_text = QLabel()
        lbl_text.setPixmap(
            QPixmap(resource_path("Spot_cutter_text.png")).scaled(
                200, 44,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
        )
        lbl_text.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(lbl_text)

        layout.addSpacing(8)

        # Sezione YOUTUBE
        yt_lbl = QLabel("📺  YOUTUBE")
        yt_lbl.setObjectName("lbl_section")
        layout.addWidget(yt_lbl)

        # --- Layout orizzontale "BARRA UNICA" ---
        yt_input_layout = QHBoxLayout()
        yt_input_layout.setSpacing(0) 
        yt_input_layout.setContentsMargins(0, 0, 0, 0)
        yt_input_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        
        self._yt_entry = QLineEdit()
        self._yt_entry.setObjectName("yt_entry")
        self._yt_entry.setPlaceholderText("Incolla link...")
        self._yt_entry.setFixedHeight(36)
        
        # Pulsante Incolla
        self._btn_paste = QPushButton()
        self._btn_paste.setObjectName("btn_paste")
        self._btn_paste.setFixedHeight(36)
        self._btn_paste.setFixedWidth(40)
        self._btn_paste.setToolTip("Incolla link dagli appunti")
        self._btn_paste.clicked.connect(self._paste_url)

        # --- FIX BUG 4: CROSS-PLATFORM ICONS ---
        import platform
        is_win11 = platform.system() == "Windows" and platform.release() == "11"
        
        if is_win11:
            self._btn_paste.setText("\ue77f") # Segoe Fluent (Win 11)
            self._btn_paste.setFont(QFont("Segoe Fluent Icons", 12))
        else:
            self._btn_paste.setText("📋") # Fallback Emoji (Win 10 / Altri)
            self._btn_paste.setFont(QFont("Segoe UI Emoji", 12))

        yt_input_layout.addWidget(self._yt_entry)
        yt_input_layout.addWidget(self._btn_paste)
        layout.addLayout(yt_input_layout)

        # --- PILLOLA YOUTUBE (IMPORTA + DOWNLOAD DIRETTO) ---
        pill_layout = QHBoxLayout()
        pill_layout.setSpacing(0)

        # Pulsante Importa (Sinistro)
        self._btn_yt = QPushButton("▶ IMPORTA DA YT")
        self._btn_yt.setObjectName("btn_yt_left")
        self._btn_yt.setFixedHeight(40)
        self._btn_yt.clicked.connect(self._on_yt_download)
        
        # Pulsante Download Diretto (Destro)
        self._btn_dl = QPushButton()
        self._btn_dl.setObjectName("btn_yt_right")
        self._btn_dl.setFixedHeight(40)
        self._btn_dl.setFixedWidth(45)
        self._btn_dl.setToolTip("Scarica video intero senza metterlo in coda")
        self._btn_dl.clicked.connect(self._on_yt_direct_download)

        if is_win11:
            self._btn_dl.setText("\ue896") # Icona Download Win11
            self._btn_dl.setFont(QFont("Segoe Fluent Icons", 11))
        else:
            self._btn_dl.setText("⬇️")

        pill_layout.addWidget(self._btn_yt)
        pill_layout.addWidget(self._btn_dl)
        layout.addLayout(pill_layout)

        sep1 = QFrame()
        sep1.setObjectName("separator")
        sep1.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sep1)

        # Sezione FILE LOCALI
        lbl_local = QLabel("📂  FILE LOCALI")
        lbl_local.setObjectName("lbl_section")
        layout.addWidget(lbl_local)

        # Bottoni file
        btn_folder = self._make_btn("📁  Sfoglia Cartella", "btn_folder")
        btn_folder.clicked.connect(self._on_browse_folder)
        layout.addWidget(btn_folder)

        btn_files = self._make_btn("🎬  Aggiungi Video", "btn_files")
        btn_files.clicked.connect(self._on_add_files)
        layout.addWidget(btn_files)

        self._btn_clear = self._make_btn("🗑  Svuota Coda", "btn_clear")
        self._btn_clear.setEnabled(False)
        self._btn_clear.clicked.connect(self._on_clear_queue)
        layout.addWidget(self._btn_clear)

        sep2 = QFrame()
        sep2.setObjectName("separator")
        sep2.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sep2)

        lbl_folder = QLabel("📁  DESTINAZIONE")
        lbl_folder.setObjectName("lbl_section")
        layout.addWidget(lbl_folder)

        self._btn_work_dir = self._make_btn("📂  Libreria Spot", "btn_work_dir", h=40)
        self._btn_work_dir.setToolTip("Cambia la cartella dove verranno salvati i tagli")
        self._btn_work_dir.clicked.connect(self._on_choose_work_dir)
        layout.addWidget(self._btn_work_dir)

        btn_storico = self._make_btn("📋  Storico elaborazioni", "btn_storico", h=36)
        btn_storico.setToolTip("Visualizza e gestisci lo storico dei video elaborati")
        btn_storico.clicked.connect(self._on_open_storico)
        layout.addWidget(btn_storico)

        btn_settings = self._make_btn("⚙️  Impostazioni", "btn_settings", h=36)
        btn_settings.setToolTip("Impostazioni Avanzate")
        btn_settings.clicked.connect(self._open_settings)
        layout.addWidget(btn_settings)

        layout.addStretch()

        # AVVIA / STOP
        self._btn_run = self._make_btn("▶  AVVIA", "btn_run", h=55)
        self._btn_run.setEnabled(False)
        self._btn_run.clicked.connect(self._on_run)
        layout.addWidget(self._btn_run)

        self._btn_stop = self._make_btn("⏹  STOP", "btn_stop", h=45)
        self._btn_stop.clicked.connect(self._on_stop)
        self._btn_stop.hide()
        layout.addWidget(self._btn_stop)

        parent_layout.addWidget(sb)

    def _make_btn(self, text, obj_name, h=40):
        """Crea un bottone sidebar — lo stile è definito nel QSS tramite objectName."""
        btn = QPushButton(text)
        btn.setObjectName(obj_name)
        btn.setFixedHeight(h)
        return btn

    # ── Area principale ────────────────────────────────────────────────────
    def _build_main_area(self, parent_layout):
        main = QWidget()
        main.setObjectName("main_area")
        layout = QVBoxLayout(main)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        # Statistiche (Ora più carine con icone)
        stats_bar = QWidget()
        stats_bar.setObjectName("stats_bar")
        stats_layout = QHBoxLayout(stats_bar)
        stats_layout.setContentsMargins(15, 8, 15, 8)
        
        self._main_stat_labels = {}
        # Definiamo le icone per ogni categoria
        cats = [
            ("spot", "📺 Spot"), ("promo", "📣 Promo"), ("bumper", "🎬 Bumper"),
            ("annunci", "🎤 Annunci"), ("natale", "🎄 Natale"),
            ("cartelli", "🖼️ Cartelli"), ("videosigle", "🎵 Sigle"), ("telegiornali", "📰 TG")
        ]
        
        for key, label_text in cats:
            lbl = QLabel(f"{label_text}: 0")
            lbl.setObjectName(f"lbl_stat_{key}") # ID specifico per colorarli nel QSS
            if key == "promo":
                lbl.setToolTip("Include automaticamente anche i Trailer")
            if key == "natale":
                lbl.setToolTip("Include automaticamente anche i contenuti natalizi")
            stats_layout.addWidget(lbl)
            stats_layout.addSpacing(15) # Spazio tra i badge
            self._main_stat_labels[key] = lbl
            
        stats_layout.addStretch()
        layout.addWidget(stats_bar)

        # Area coda (scrollabile)
        self._queue_scroll = QScrollArea()
        self._queue_scroll.setWidgetResizable(True)
        self._queue_scroll.setObjectName("queue_scroll")

        self._queue_container = QWidget()
        self._queue_container.setObjectName("queue_container")
        self._queue_layout = QVBoxLayout(self._queue_container)
        self._queue_layout.setContentsMargins(8, 8, 8, 8)
        self._queue_layout.setSpacing(4)
        self._queue_layout.addStretch()

        self._queue_scroll.setWidget(self._queue_container)
        layout.addWidget(self._queue_scroll, stretch=1)

        # Barra progresso corrente
        self._pb_label = QLabel("Progresso: 0%")
        self._pb_label.setObjectName("lbl_progress")
        layout.addWidget(self._pb_label)

        self._pb = QProgressBar()
        self._pb.setObjectName("pb_current")
        self._pb.setRange(0, 1000)
        self._pb.setValue(0)
        self._pb.setFixedHeight(10)
        self._pb.setTextVisible(False)
        layout.addWidget(self._pb)

        # Barra progresso globale
        self._pb_global_label = QLabel("Progresso Totale: 0/0 video")
        self._pb_global_label.setObjectName("lbl_progress")
        layout.addWidget(self._pb_global_label)

        self._pb_global = QProgressBar()
        self._pb_global.setObjectName("pb_global")
        self._pb_global.setRange(0, 1000)
        self._pb_global.setValue(0)
        self._pb_global.setFixedHeight(10)
        self._pb_global.setTextVisible(False)
        layout.addWidget(self._pb_global)

        # Log console
        self._log = QTextEdit()
        self._log.setObjectName("log_box")
        self._log.setReadOnly(True)
        self._log.setFixedHeight(130)
        layout.addWidget(self._log)

        parent_layout.addWidget(main, stretch=1)

        self.render_queue()

    # ══════════════════════════════════════════════════════════════════════
    # RENDER CODA
    # ══════════════════════════════════════════════════════════════════════

    @Slot()
    def render_queue(self):
        # Pulizia sicura della coda
        while self._queue_layout.count() > 1:
            item = self._queue_layout.takeAt(0)
            if item:
                w = item.widget()
                if w is not None:  # Controllo esplicito per far felice VS Code
                    w.deleteLater()

        self.state["status_labels"] = {}
        queue = self.state.get("queue_files", [])
        total = len(queue)
        running = self.state.get("running", False)

        if not queue:
            empty = QLabel("Nessun video in coda.\nTrascina i file qui o usa i tasti laterali.")
            empty.setObjectName("lbl_empty_queue")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._queue_layout.insertWidget(0, empty)
            self._sync_buttons()
            return

        for i, (vid, txt, manual_date) in enumerate(queue):
            has_txt = txt is not None
            
            # 1. Recuperiamo info sulla data
            ext_date, _, auto_color = extract_date_info(vid)
            
            # 2. Validazione rigorosa (usa datetime internamente)
            # Se c'è una data manuale, usiamo quella, altrimenti quella estratta
            date_to_check = manual_date if (manual_date and manual_date.strip() not in ("", "--")) else ext_date
            
            # Verifichiamo se la data è REALE (es. non 31-02)
            is_valid = False
            if date_to_check:
                try:
                    datetime.strptime(date_to_check, "%d-%m-%Y")
                    is_valid = True
                except:
                    is_valid = False

            # --- 3. Decisione Semaforo ---
            if not is_valid:
                st, sc = f"⛔ Invalida: {date_to_check}", "#FF3B30"
            elif not date_to_check or date_to_check == "00-00-0000":
                st, sc = "⚠️ Data: MANCANTE", "#FF9500"
            elif manual_date:
                st, sc = f"✅ Data: {manual_date}", "#4CD964"
            elif auto_color == "green":
                st, sc = f"✅ Data: {ext_date}", "#4CD964"
            else:
                st, sc = f"⚠️ Data: {ext_date}", "#FF9500"

            # Se manca il TXT, il colore globale della card è Rosso, ma il testo 'st' resta quello della data
            if not has_txt:
                sc = "#FF3B30"

            # Controlla storico: se il video è già stato elaborato, mostra verde
            storico_path = os.path.join(
                self.state.get("work_dir", self.state.get("current_dir", "")),
                "storico.json"
            )
            is_done = False
            if os.path.exists(storico_path):
                try:
                    with open(storico_path, "r", encoding="utf-8") as _sf:
                        _storico = json.load(_sf)
                    if vid in _storico:
                        is_done = True
                        entry   = _storico[vid]
                        st = f"✅ Elaborato il {entry.get('data_elaborazione', '?')}"
                        sc = "#4CAF50"
                except Exception:
                    pass

            card = VideoCard(
                idx=i, vid=vid, has_txt=has_txt,
                status_text=st, status_color=sc,
                is_first=(i == 0), is_last=(i == total - 1),
                is_running=running)

            card.sig_move_up.connect(self._move_item_up)
            card.sig_move_down.connect(self._move_item_down)
            card.sig_delete.connect(self._remove_item)
            card.sig_edit_txt.connect(self._open_txt_editor)
            card.sig_edit_date.connect(self._open_date_editor)
            card.sig_cut.connect(self._on_cut_manual)

            self._queue_layout.insertWidget(i, card)
            self.state["status_labels"][i] = card

        self._sync_buttons()

    def _sync_buttons(self):
        """Disabilita AVVIA se ci sono errori (TXT mancanti o date invalide)."""
        queue = self.state.get("queue_files", [])
        running = self.state.get("running", False)
        
        can_start = bool(queue) and not running
        
        if can_start:
            for vid, txt, manual_date in queue:
                ext_date, _, auto_color = extract_date_info(vid)
                date_to_check = manual_date if (manual_date and manual_date.strip() not in ("", "--")) else ext_date
                
                # Controllo validità reale
                is_valid = False
                try:
                    datetime.strptime(date_to_check, "%d-%m-%Y")
                    is_valid = True
                except:
                    is_valid = False

                # Se manca il TXT o la data è invalida o la data è arancione (incerta), NON partire
                if not txt or not is_valid or (not manual_date and auto_color != "green"):
                    can_start = False
                    break

        if running:
            self._btn_run.hide()
            self._btn_stop.show()
        else:
            self._btn_stop.hide()
            self._btn_run.show()
            self._btn_run.setEnabled(can_start)
            # Aggiorna lo stile visuale del tasto
            self._btn_run.setProperty("stato", "pronto" if can_start else "disabilitato")
            self._btn_run.style().unpolish(self._btn_run)
            self._btn_run.style().polish(self._btn_run)

        self._btn_clear.setEnabled(bool(queue) and not running)

    # ══════════════════════════════════════════════════════════════════════
    # SLOT — aggiornamenti da Worker (thread-safe via segnali)
    # ══════════════════════════════════════════════════════════════════════

    @Slot(str, str)
    def _on_log(self, msg: str, color: str):
        """Aggiunge una riga al log con il colore specificato."""
        cursor = self._log.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)

        fmt = cursor.charFormat()
        # Converte nomi colore comuni in hex
        color_map = {
            "white": "#E0E0E0", "grey": "#9E9E9E", "gray": "#9E9E9E",
            "cyan": "#00BCD4", "blue": "#42A5F5", "green": "#66BB6A",
            "orange": "#FFA726", "red": "#EF5350", "yellow": "#FFEE58",
            "magenta": "#CE93D8",
        }
        hex_color = color_map.get(color.lower(), color
                                   if color.startswith("#") else "#E0E0E0")
        fmt.setForeground(QColor(hex_color))
        cursor.setCharFormat(fmt)
        cursor.insertText(f"> {msg}\n")

        # Limita a 150 righe
        doc = self._log.document()
        if doc.blockCount() > 150:
            cur = QTextCursor(doc)
            cur.movePosition(QTextCursor.MoveOperation.Start)
            cur.select(QTextCursor.SelectionType.BlockUnderCursor)
            cur.removeSelectedText()
            cur.deleteChar()

        self._log.setTextCursor(cursor)
        self._log.ensureCursorVisible()

    @Slot(float, str)
    def _on_progress(self, value: float, label: str):
        self._pb.setValue(int(value * 1000))
        self._pb_label.setText(label)

    @Slot(int, int)
    def _on_global_progress(self, index: int, total: int):
        v = int((index / total * 1000)) if total > 0 else 0
        self._pb_global.setValue(v)
        self._pb_global_label.setText(
            f"Progresso Totale: {index}/{total} video")

    @Slot(int, str, str)
    def _on_status(self, idx: int, status: str, color: str):
        card = self.state["status_labels"].get(idx)
        if card and isinstance(card, VideoCard):
            card.set_status(status, color)

    @Slot()
    def _on_stats_update(self):
        """Aggiorna i contatori delle statistiche nell'interfaccia"""
        # Definiamo i nomi visualizzati con le icone (coerenti con _build_main_area)
        display_names = {
            "spot": "📺 Spot",
            "promo": "📣 Promo",
            "bumper": "🎬 Bumper",
            "annunci": "🎤 Annunci",
            "natale": "🎄 Natale",
            "cartelli": "🖼️ Cartelli",
            "videosigle": "🎵 Sigle",
            "telegiornali": "📰 TG"
        }

        # Aggiorna solo le etichette dell'area principale
        for key, lbl in self._main_stat_labels.items():
            n = self.state["stats_counts"].get(key, 0)
            label_text = display_names.get(key, key.capitalize())
            lbl.setText(f"{label_text}: {n}")

    @Slot(bool, float)
    def _on_finished(self, successo: bool, elapsed: float):
        m, s_ = divmod(int(elapsed), 60)
        counts = self.state["stats_counts"]
        
        # Creiamo la stringa di riepilogo (es: "12 spot, 1 natale")
        riepilogo = ", ".join([f"{v} {k}" for k, v in counts.items() if v > 0])
        
        # --- Log nel pannello ---
        if successo:
            if riepilogo:
                self._on_log(f"📊 RIEPILOGO: {riepilogo}", "cyan")
            self._on_log(f"✅ ELABORAZIONE TERMINATA in {m}m {s_}s", "white")
        else:
            self._on_log(f"🛑 INTERROTTA dopo {m}m {s_}s", "orange")

        # Rimuove dalla coda i video completati con successo (presenti nello storico)
        if successo:
            storico_path = os.path.join(
                self.state.get("work_dir", self.state.get("current_dir", "")),
                "storico.json"
            )
            storico = {}
            if os.path.exists(storico_path):
                try:
                    with open(storico_path, "r", encoding="utf-8") as _sf:
                        storico = json.load(_sf)
                except Exception:
                    pass
            self.state["queue_files"] = [
                (v, t, d) for v, t, d in self.state["queue_files"]
                if v not in storico
            ]
            self._on_stats_update()


        # Reset UI
        self._on_progress(0, "Progresso: 0%")
        self._on_global_progress(0, 0)
        self._sync_buttons()
        self.render_queue()

        # --- Dialogo Finale con Riepilogo ---
        if elapsed > 1:
            QTimer.singleShot(50, lambda: self._show_finished_dialog(successo, m, s_, riepilogo))

    def _show_finished_dialog(self, successo: bool, m: int, s_: int, riepilogo: str):
        stato = "Completato! ✅" if successo else "Interrotto 🛑"
        
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Elaborazione terminata")
        msg_box.setIcon(QMessageBox.Icon.Information if successo else QMessageBox.Icon.Warning)
        
        testo_box = f"Lavoro {stato}\nTempo totale: {m}m {s_}s"
        if riepilogo:
            testo_box += f"\n\nCategorie elaborate:\n{riepilogo}"
        
        msg_box.setText(testo_box)
        
        btn_open = msg_box.addButton("📂 Apri Cartella", QMessageBox.ButtonRole.ActionRole)
        btn_ok = msg_box.addButton("OK", QMessageBox.ButtonRole.AcceptRole)
        
        msg_box.exec()
        
        if msg_box.clickedButton() == btn_open:
            self._open_output_folder()
        elif msg_box.clickedButton() == btn_ok:
            self.close()


    def _open_output_folder(self, path: str = ""):
        """Apre la cartella di lavoro nel file explorer del sistema."""
        if not path:
            path = self.state.get("work_dir", os.getcwd())
        if not os.path.exists(path):
            return

        import platform
        import subprocess

        try:
            if platform.system() == "Windows":
                os.startfile(path)
            elif platform.system() == "Darwin":  # macOS
                subprocess.run(["open", path])
            else:  # Linux
                subprocess.run(["xdg-open", path])
        except Exception as e:
            self._on_log(f"⚠️ Errore apertura cartella: {e}", "orange")

    def _on_yt_direct_download(self):
        """Avvia il download senza passare per la coda dei tagli."""
        url = self._yt_entry.text().strip()
        if not url:
            self._on_log("⚠️ Inserisci un link prima di scaricare!", "orange")
            return
            
        self._btn_yt.setEnabled(False)
        self._btn_dl.setEnabled(False)
        self._is_direct_download = True # Flag per il popup finale
        
        self._on_log(f"🌐 Scaricando video intero: {url}", "cyan")
        self._start_yt_download(url)

    @Slot(list)
    def _on_yt_finished(self, result: list):
        self.state["running"] = False
        self._btn_yt.setEnabled(True)
        # Fix: riabilita anche il tasto pillola destro (download)
        if hasattr(self, "_btn_dl"):
            self._btn_dl.setEnabled(True)
            
        self._btn_yt.setText("▶ IMPORTA DA YT")
        self._on_progress(0, "Pronto.")
        
        # --- LOGICA DOWNLOAD DIRETTO (Pillola Destra) ---
        is_direct = getattr(self, "_is_direct_download", False)
        self._is_direct_download = False # Reset immediato del flag
        
        if is_direct and result:
            vid_basename = result[0][0]   # es. "Titolo Video.mp4"
            # Costruisce il percorso completo: current_dir è la cartella di download
            work_dir   = self.state.get("work_dir") or self.state.get("current_dir", "")
            output_dir = os.path.join(work_dir, "Download YT")
            vid_path   = os.path.join(output_dir, vid_basename) if output_dir else vid_basename
            vid_title  = os.path.splitext(vid_basename)[0]   # nome senza estensione

            msg = QMessageBox(self)
            msg.setWindowTitle("Download Completato")
            msg.setIcon(QMessageBox.Icon.Information)
            msg.setText("<b>Video scaricato con successo!</b>")
            msg.setInformativeText(f"File: {vid_basename}\n\nIl file è disponibile nella cartella di destinazione.")

            btn_open = msg.addButton("📂 Apri Cartella", QMessageBox.ButtonRole.AcceptRole)
            msg.addButton("Chiudi", QMessageBox.ButtonRole.RejectRole)

            msg.exec()

            if msg.clickedButton() == btn_open:
                self._open_output_folder(output_dir)

            # Esce qui: download diretto NON va nella coda di taglio
            self._sync_buttons()
            self.render_queue()
            return 
        # ------------------------------------------------

        # Logica standard per IMPORTA (Pillola Sinistra)
        if result:
            added_count = 0
            for vid, txt in result:
                if any(item[0] == vid for item in self.state["queue_files"]):
                    self._on_log(f"⚠️ {vid} è già presente nella lista attuale.", "orange")
                    continue
                    
                self.state["queue_files"].append((vid, txt, None))
                added_count += 1
            
            if added_count > 0:
                s = "o" if added_count == 1 else "i"
                msg = f"✅ {added_count} vide{s} aggiunt{s} alla coda con successo."
                self._on_log(msg, "green")
        else:
            self._on_log("ℹ️ Nessun nuovo video aggiunto (già scaricato o file non trovato).", "gray")
                
        self._sync_buttons()
        self.render_queue()

    # ══════════════════════════════════════════════════════════════════════
    # HANDLERS — Bottoni
    # ══════════════════════════════════════════════════════════════════════

    def _on_browse_folder(self):
        d = QFileDialog.getExistingDirectory(
            self, "Seleziona cartella video")
        if not d:
            return
        self.state["current_dir"] = d
        os.chdir(d)
        self.state["queue_files"] = []
        vids = sorted(f for f in os.listdir(d)
                      if f.lower().endswith(ESTENSIONI_VIDEO))
        for vid in vids:
            base = os.path.splitext(vid)[0]
            txt  = base + ".txt"
            self.state["queue_files"].append(
                (vid, txt if os.path.exists(os.path.join(d, txt)) else None, None))
        self._on_log(f"Cartella caricata: {len(vids)} video.", "cyan")
        self.render_queue()

    def _on_add_files(self):
        ext_filter = "Video (" + " ".join(
            f"*{e}" for e in ESTENSIONI_VIDEO) + ")"
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Seleziona video", "", ext_filter)
        if not paths:
            return
        d = os.path.dirname(paths[0])
        if not self.state["current_dir"]:
            self.state["current_dir"] = d
        added = 0
        for path in paths:
            fname = os.path.basename(path)
            if not any(q[0] == fname for q in self.state["queue_files"]):
                base = os.path.splitext(fname)[0]
                txt  = base + ".txt"
                self.state["queue_files"].append(
                    (fname,
                     txt if os.path.exists(os.path.join(d, txt)) else None,
                     None))
                added += 1
        self._on_log(f"Aggiunti {added} video.", "cyan")
        self.render_queue()

    def _on_clear_queue(self):
        if self.state["running"]:
            return
        self.state["queue_files"] = []
        self._on_log("Coda svuotata.", "orange")
        self.render_queue()

    def _on_run(self):
        if self.state["running"]:
            return

        # 1. FIX SICUREZZA: Controllo coda vuota per evitare crash nel worker
        if not self.state.get("queue_files"):
            self._on_log("⚠️ Coda vuota. Nulla da elaborare.", "orange")
            return

        # 2. FIX MEMORIA: Resettiamo il dizionario delle label di stato.
        # Questo evita che il Worker cerchi di aggiornare graficamente dei widget 
        # che sono stati cancellati/ricreati durante il balletto "scarica-togli-riscarica".
        self.state["status_labels"] = {}

        # ── Pulizia thread precedente ─────────────────────────────────────
        if self._worker_thread is not None:
            try:
                if self._worker_thread.isRunning():
                    self._worker_thread.quit()
                    if not self._worker_thread.wait(3000):
                        self._worker_thread.terminate()
                        self._worker_thread.wait()
                self._worker_thread.deleteLater()
            except RuntimeError:
                # Il thread è già stato distrutto da Qt — ignoriamo
                pass
            finally:
                self._worker_thread = None

        # Legge impostazioni
        class _V:
            def __init__(self, v): self.value = str(v)

        s = self._s
        v_crf, v_cusc_i, v_cusc_f, v_toll, v_bth, v_bdur, errs = \
            parse_settings(_V(s["crf"]),    _V(s["cusc_i"]), _V(s["cusc_f"]),
                           _V(s["toll"]),   _V(s["bth"]),    _V(s["bdur"]))
        for e in errs:
            self._on_log(f"⚠️ {e}", "orange")

        self.state["running"] = True
        self.state["stats_counts"] = {k: 0 for k in self.state["stats_counts"]}
        self.state["parallel_cuts"] = int(self._s.get("parallel_cuts", 0))
        self.state["silence_thresh"] = self._s.get("silence_thresh", "-35dB")
        self.state["silence_dur"] = self._s.get("silence_dur", "0.1")
        self._sync_buttons()

        # Crea worker e thread
        self._worker = EngineWorker(self.state,
                                    (v_crf, v_cusc_i, v_cusc_f,
                                     v_toll, v_bth, v_bdur))
        self._worker_thread = QThread()
        self._worker.moveToThread(self._worker_thread)

        # Connette segnali (Assicurati che questi segnali esistano nella classe!)
        self._worker.sig_log.connect(self._on_log)
        self._worker.sig_progress.connect(self._on_progress)
        self._worker.sig_global_progress.connect(self._on_global_progress)
        self._worker.sig_status.connect(self._on_status)
        self._worker.sig_stats_update.connect(self._on_stats_update)
        self._worker.sig_finished.connect(self._on_finished)
        self._worker.sig_queue_update.connect(self.render_queue)
        
        self._worker_thread.started.connect(self._worker.run)
        self._worker.sig_finished.connect(self._worker_thread.quit)
        self._worker_thread.finished.connect(self._worker_thread.deleteLater)
        self._worker_thread.finished.connect(lambda: setattr(self, "_worker_thread", None))

        self._worker_thread.start()

    def _on_stop(self):
        self.state["running"] = False
        self._on_log("🛑 Stop richiesto...", "orange")

    @Slot(int)
    def _move_item_up(self, idx: int):
        if self.state["running"]:
            return
        q = self.state["queue_files"]
        if idx > 0:
            q[idx], q[idx - 1] = q[idx - 1], q[idx]
            self.render_queue()

    @Slot(int)
    def _move_item_down(self, idx: int):
        if self.state["running"]:
            return
        q = self.state["queue_files"]
        if idx < len(q) - 1:
            q[idx], q[idx + 1] = q[idx + 1], q[idx]
            self.render_queue()

    @Slot(int)
    def _remove_item(self, idx: int):
        if self.state["running"]:
            return
        if 0 <= idx < len(self.state["queue_files"]):
            vid = self.state["queue_files"].pop(idx)[0]
            self._on_log(f"Rimosso: {vid}", "orange")
            self.render_queue()

    def _on_cut_manual(self, vid: str):
        """Apre il dialog di taglio manuale con blackdetect per il video selezionato."""
        vid_path = os.path.join(self.state["current_dir"], vid)
        txt_name = os.path.splitext(vid)[0] + ".txt"
        txt_path = os.path.join(self.state["current_dir"], txt_name)

        if not os.path.exists(vid_path):
            QMessageBox.warning(self, "File non trovato",
                                f"Il file video non è stato trovato:\n{vid_path}")
            return

        dlg = BlackdetectDialog(vid_path, txt_path, self._s, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            # Aggiorna la coda: imposta il txt per questo video
            for i, (v, t, d) in enumerate(self.state["queue_files"]):
                if v == vid:
                    self.state["queue_files"][i] = (v, txt_name, d)
                    break
            self.render_queue()
            self._on_log(f"✅ TXT salvato per {vid}", "green")

    # ══════════════════════════════════════════════════════════════════════
    # EDITOR TXT
    # ══════════════════════════════════════════════════════════════════════

    @Slot(str)
    def _open_txt_editor(self, vid_name: str):
        if not self.state["current_dir"]:
            QMessageBox.warning(self, "Errore", "Carica prima una cartella o dei video!")
            return
        base = os.path.splitext(vid_name)[0]
        file_path = os.path.join(self.state["current_dir"], f"{base}.txt")
        contenuto = ""
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                contenuto = f.read()

        dlg = TxtEditorDialog(f"Editor — {base}.txt", contenuto, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        content = dlg.get_text()
        path = os.path.abspath(os.path.join(self.state.get("current_dir", os.getcwd()), f"{base}.txt"))
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

        # Aggiorna coda (rispettando il nuovo formato data)
        for i, item in enumerate(self.state["queue_files"]):
            if os.path.splitext(item[0])[0] == base:
                # Riprendiamo la data manuale già esistente (item[2])
                self.state["queue_files"][i] = (item[0], f"{base}.txt", item[2])

        self._on_log(f"✅ TXT salvato: {base}.txt", "green")
        self.render_queue()

    # ══════════════════════════════════════════════════════════════════════
    # EDITOR DATA
    # ══════════════════════════════════════════════════════════════════════

    @Slot(int)
    def _open_date_editor(self, idx: int):
        vid_name = self.state["queue_files"][idx][0]
        current_manual_date = self.state["queue_files"][idx][2]
        ext_date, _, _ = extract_date_info(vid_name)
        
        # Passiamo la data corrente (manuale se esiste, sennò quella estratta)
        start_date = current_manual_date if current_manual_date else ext_date

        dlg = DateEditorDialog(vid_name, start_date, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        
        val = dlg.get_date()
        vid, tp, _ = self.state["queue_files"][idx]
        self.state["queue_files"][idx] = (vid, tp, val)
        self._on_log(f"✅ Data {val} salvata per → {vid_name}", "cyan")
        self.render_queue()

    # ══════════════════════════════════════════════════════════════════════
    # IMPOSTAZIONI
    # ══════════════════════════════════════════════════════════════════════

    def _open_settings(self):
        dlg = SettingsDialog(self._s, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        vals = dlg.get_values()
        save_settings(vals["crf"], vals["cusc_i"], vals["cusc_f"],
                      vals["toll"], vals["bth"], vals["bdur"],
                      vals.get("parallel_cuts", "0"),
                      vals.get("silence_thresh", "-35dB"),
                      vals.get("silence_dur", "0.1"))
        self._s = load_settings()
        self._on_log("✅ Impostazioni salvate.", "cyan")

    # ══════════════════════════════════════════════════════════════════════
    # YOUTUBE DOWNLOAD
    # ══════════════════════════════════════════════════════════════════════

    def _on_yt_download(self):
        url = self._yt_entry.text().strip()
        if not url:
            return
            
        from video_engine import get_ytdlp_path
        ytdlp_path = get_ytdlp_path()
        # get_ytdlp_path ritorna "yt-dlp" come fallback se non trovato —
        # verifichiamo che sia un file reale oppure che esista nel PATH
        import shutil
        if not os.path.isfile(ytdlp_path) and not shutil.which(ytdlp_path):
            QMessageBox.warning(self, "yt-dlp mancante",
                                "yt-dlp.exe non trovato.\n"
                                "Metti yt-dlp.exe nella stessa cartella del programma.")
            return

        # ─── FIX ANTI-CRASH ──────────────────────────────────────────────────
        # Controlliamo se esiste già un thread di YouTube attivo.
        # Se lo sovrascriviamo mentre corre, Qt crasha con "Destroyed while running".
        if hasattr(self, "_yt_thread") and self._yt_thread is not None:
            if self._yt_thread.isRunning():
                # Se è già in corso, avvisiamo l'utente e usciamo
                self._on_log("⚠️ C'è già un'operazione YouTube in corso. Attendi...", "orange")
                return
            
            # Se il thread esiste ma ha finito, lo puliamo prima di ricrearlo
            self._yt_thread.deleteLater()
            self._yt_thread = None
        # ──────────────────────────────────────────────────────────────────────

        self._btn_yt.setEnabled(False)
        self._btn_yt.setText("Analisi link...")
        self._on_progress(0, "Analisi link YouTube...")

        # Nota: il QMessageBox nel thread non-UI è rischioso su Windows,
        # usiamo QTimer.singleShot per eseguire la check sul thread UI
        # tramite un piccolo trucco con threading.Event
        threading.Thread(target=self._yt_info_and_confirm,
                         args=(url,), daemon=True).start()
        
    def _paste_url(self):
        """Preleva il testo dagli appunti e lo inserisce nel campo URL."""
        clipboard = QApplication.clipboard()
        text = clipboard.text().strip()
        
        if text:
            self._yt_entry.setText(text)
            self._on_log("📋 Link incollato correttamente.", "gray")
        else:
            self._on_log("⚠️ Appunti vuoti o nessun testo trovato.", "orange")

    def _yt_info_and_confirm(self, url):
        """Questa funzione gira nel thread di lavoro del worker YT"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            async def _nop(*_): pass
            engine = VideoEngine(log_cb=_nop, progress_cb=_nop)
            # Qui viene creata la variabile info
            info = loop.run_until_complete(engine.get_url_info(url))
        except Exception as e:
            print(f"Errore analisi YT: {e}") # Per debug tuo a terminale
            info = None
        finally:
            loop.close()

        self._sig_yt_info.emit(url, info)

    def _yt_after_info(self, url: str, info):
        """Chiamato sul thread UI dopo l'analisi del link."""
        if not info:
            self._on_log("❌ Impossibile analizzare il link.", "red")
            self._btn_yt.setEnabled(True)
            if hasattr(self, "_btn_dl"): self._btn_dl.setEnabled(True) # Fix pillola
            self._btn_yt.setText("▶ IMPORTA DA YT")
            self._on_progress(0, "Errore link.")
            return

        final_url = url

        # CASO 1: Link Misto (Video + Playlist)
        if "watch?v=" in url and "&list=" in url:
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("Opzioni di Download")
            msg_box.setIcon(QMessageBox.Icon.Question)
            msg_box.setText(f"Il video fa parte della playlist:\n'{info.get('title', 'Playlist')}'")
            msg_box.setInformativeText("Cosa desideri scaricare?")
            
            btn_single = msg_box.addButton("Solo Video Singolo", QMessageBox.ButtonRole.ActionRole)
            btn_playlist = msg_box.addButton("Intera Playlist", QMessageBox.ButtonRole.ActionRole)
            btn_cancel = msg_box.addButton("Annulla", QMessageBox.ButtonRole.RejectRole)
            
            msg_box.exec()
            
            if msg_box.clickedButton() == btn_single:
                final_url = url.split('&list=')[0]
                self._on_log("🔗 Scelta: Video singolo.", "cyan")
            elif msg_box.clickedButton() == btn_playlist:
                final_url = url
                self._on_log("🔗 Scelta: Intera playlist.", "cyan")
            else:
                # Annullato: ripristina entrambi i bottoni
                self._btn_yt.setEnabled(True)
                if hasattr(self, "_btn_dl"): self._btn_dl.setEnabled(True)
                self._btn_yt.setText("▶ IMPORTA DA YT")
                self._on_progress(0, "Pronto.")
                self._is_direct_download = False # Reset flag di sicurezza
                return

        # CASO 2: Playlist Pura (senza watch?v=)
        elif info["is_playlist"]:
            reply = QMessageBox.question(
                self, "Conferma Playlist",
                f"La playlist '{info['title']}' contiene "
                f"{info['count']} video.\nVuoi scaricarli tutti?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            
            if reply != QMessageBox.StandardButton.Yes:
                self._btn_yt.setEnabled(True)
                if hasattr(self, "_btn_dl"): self._btn_dl.setEnabled(True)
                self._btn_yt.setText("▶ IMPORTA DA YT")
                self._on_progress(0, "Download annullato.")
                self._is_direct_download = False
                return

        # Avviamo il download con il link definitivo
        self._start_yt_download(final_url)

    def _start_yt_download(self, url: str):
        # url qui è già stato filtrato/pulito da _yt_after_info
        if not self.state["current_dir"]:
            self.state["current_dir"] = os.getcwd()

        self.state["running"] = True
        self._yt_entry.clear()
        self._sync_buttons()

        # Passiamo l'URL pulito al Worker
        is_direct = getattr(self, "_is_direct_download", False)
        if is_direct:
            output_dir = os.path.join(self.state.get("work_dir", self.state["current_dir"]), "Download YT")
            os.makedirs(output_dir, exist_ok=True)
        else:
            output_dir = self.state["current_dir"]
        self._yt_worker = YTWorker(url, output_dir, self.state, direct_download=is_direct)
        self._yt_thread = QThread()
        self._yt_worker.moveToThread(self._yt_thread)

        # ─── FIX BUG 3: RELAY THREAD-SAFE ────────────────────────────────────
        # Invece di connettere il segnale del worker direttamente al segnale della UI,
        # lo connettiamo alla funzione .emit del segnale della UI.
        self._yt_worker.sig_log.connect(self._sig_log.emit)
        self._yt_worker.sig_progress.connect(self._sig_progress.emit)
        self._yt_worker.sig_finished.connect(self._sig_yt_finished.emit)
        # ──────────────────────────────────────────────────────────────────────

        # Gestione chiusura thread (rimane invariata)
        self._yt_worker.sig_finished.connect(self._yt_thread.quit)
        self._yt_thread.finished.connect(self._yt_thread.deleteLater)
        self._yt_thread.finished.connect(lambda: setattr(self, "_yt_thread", None))

        self._yt_thread.started.connect(self._yt_worker.run)
        self._yt_thread.start()

    # ══════════════════════════════════════════════════════════════════════
    # AVVIO — controlli iniziali
    # ══════════════════════════════════════════════════════════════════════

    def _startup_checks(self):
        from utils import get_tool_path
        ffmpeg_ok  = os.path.isfile(get_tool_path("ffmpeg"))  or shutil.which("ffmpeg")
        ffprobe_ok = os.path.isfile(get_tool_path("ffprobe")) or shutil.which("ffprobe")
        if not ffmpeg_ok or not ffprobe_ok:
            QMessageBox.warning(
                self, "FFmpeg non trovato",
                "FFmpeg o FFprobe non trovati!\n"
                "Il taglio video non funzionerà.\n\n"
                "Metti ffmpeg.exe e ffprobe.exe nella cartella del programma "
                "o nella sottocartella bin/, oppure aggiungili al PATH di sistema.")

        from video_engine import get_ytdlp_path
        ytdlp_bin = get_ytdlp_path()
        
        if os.path.exists(ytdlp_bin):
            threading.Thread(target=self._update_ytdlp, daemon=True).start()
        else:
            self._sig_log.emit("⚠️ yt-dlp.exe non trovato nella cartella. Il download YouTube non funzionerà.", "orange")

    @Slot()
    def _update_ytdlp(self):
        """Versione aggiornata: usa il binario .exe tramite VideoEngine invece di pip"""
        # Aspettiamo che l'app sia ben avviata prima di loggare
        time.sleep(2.0)
        
        def run_update():
            from video_engine import VideoEngine
            
            # Callback per loggare dal thread alla UI
            async def log_bridge(msg, color):
                self._sig_log.emit(msg, color)
            async def prog_bridge(val, lbl):
                pass

            engine = VideoEngine(log_cb=log_bridge, progress_cb=prog_bridge)
            
            try:
                # Creiamo il loop per gestire l'asyncio dell'engine
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(engine.update_ytdlp())
                loop.close()
            except Exception as e:
                self._sig_log.emit(f"⚠️ Errore aggiornamento: {str(e)}", "orange")

        threading.Thread(target=run_update, daemon=True).start()

    def closeEvent(self, event):
        """Gestisce la chiusura pulita dell'app e dei thread con pulsanti in italiano."""
        
        # 1. Creiamo la box manualmente per tradurre i tasti
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle('Esci')
        msg_box.setText("Vuoi davvero uscire? Le operazioni in corso verranno interrotte.")
        msg_box.setIcon(QMessageBox.Icon.Question)
        
        # Pulsanti personalizzati
        si_button = msg_box.addButton("Sì", QMessageBox.ButtonRole.YesRole)
        no_button = msg_box.addButton("No", QMessageBox.ButtonRole.NoRole)
        msg_box.setDefaultButton(no_button)
        
        msg_box.exec()

        if msg_box.clickedButton() == si_button:
            # --- AZIONE CRITICA ---
            # Comunichiamo immediatamente a tutti i cicli (Video e YouTube) di fermarsi
            self.state["running"] = False 
            
            # 2. Ferma il Worker Video (Taglio spot)
            if hasattr(self, "_worker_thread") and self._worker_thread:
                try:
                    if self._worker_thread.isRunning():
                        # Diamo tempo al thread di leggere running=False e chiudersi bene
                        self._worker_thread.quit()
                        if not self._worker_thread.wait(2000): # Aspetta 2 secondi
                            self._worker_thread.terminate() # Forza se bloccato
                except RuntimeError:
                    pass
            
            # 3. Ferma il Worker YouTube (Download/Analisi)
            if hasattr(self, "_yt_thread") and self._yt_thread:
                try:
                    if self._yt_thread.isRunning():
                        self._yt_thread.quit()
                        if not self._yt_thread.wait(2000):
                            self._yt_thread.terminate()
                except RuntimeError:
                    pass
                
            event.accept()
        else:
            # Se preme "No", annulliamo la chiusura
            event.ignore()


# ══════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"
    os.environ["QT_FONT_DPI"] = "96"
    os.environ["QT_USE_DIRECTWRITE"] = "1"
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 11))
    win = SpotCutterApp()
    win.show()
    sys.exit(app.exec())
