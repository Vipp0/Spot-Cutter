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
import html

from datetime import datetime

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QTextEdit, QScrollArea,
    QFrame, QSizePolicy, QDialog, QDialogButtonBox, QFileDialog,
    QMessageBox, QProgressBar, QSplitter, QStyle, QPlainTextEdit,
    QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox
)
from PySide6.QtCore import (
    Qt, QThread, QObject, Signal, Slot, QTimer, QSize, QSettings,
    QPropertyAnimation, QEasingCurve
)
from PySide6.QtGui import (
    QFont, QColor, QPalette, QIcon, QTextCursor, QPixmap
)

# ── GESTIONE PERCORSI FFmpeg ───────────────────────────────────────────────
if getattr(sys, 'frozen', False):
    base_path = os.path.dirname(sys.executable)
else:
    base_path = os.path.dirname(os.path.abspath(__file__))

# ── IMPORT MODULI PROGETTO ─────────────────────────────────────────────────
from utils import (
    ESTENSIONI_VIDEO, extract_date_info,
    get_unique_filename, get_video_duration, righe_txt_ignorate, righe_txt_fuori_ordine,
    get_seconds, get_tool_path, motivo_non_pronto, parse_settings, load_settings, save_settings,
    aggiungi_strumenti_al_path, strumento_presente, scarica_ytdlp,
)
aggiungi_strumenti_al_path()   # ffmpeg nella cartella o in bin/: lo vedono anche yt-dlp e ffplay
from video_engine import VideoEngine

def resource_path(relative_path):
    """ Ottiene il percorso assoluto della risorsa, per l'EXE e per il debug """
    # getattr cerca l'attributo e, se non lo trova, usa il secondo parametro (os.path.abspath("."))
    base_path = getattr(sys, '_MEIPASS', os.path.abspath("."))
    return os.path.join(base_path, relative_path)


# ══════════════════════════════════════════════════════════════════════════
# ICONE — dal carattere di icone di Windows (Fluent su 11, MDL2 su 10): tutte
# dello stesso disegno, al posto delle emoji che cambiano aspetto da un PC all'altro
# ══════════════════════════════════════════════════════════════════════════
_GLIFI = {
    "cartella": "\ue8b7", "cartella_aperta": "\ue838", "video": "\ue714", "cestino": "\ue74d",
    "storico": "\ue81c", "impostazioni": "\ue713", "avvia": "\ue768", "scarica": "\ue896",
    "incolla": "\ue77f", "salva": "\ue74e", "apri": "\ue8e5", "su": "\ue70e", "giu": "\ue70d",
    "forbici": "\ue8c6", "chiudi": "\ue711", "cerca": "\ue721", "espandi": "\ue740",
    "indietro": "\ue892", "avanti": "\ue893",
}
_font_icone_trovato = []

def _font_icone() -> str:
    """Nome del carattere di icone installato ("" se non c'è: si ripiega sulle emoji)."""
    if not _font_icone_trovato:
        from PySide6.QtGui import QFontDatabase
        famiglie = set(QFontDatabase.families())
        _font_icone_trovato.append(next((f for f in ("Segoe Fluent Icons", "Segoe MDL2 Assets")
                                         if f in famiglie), ""))
    return _font_icone_trovato[0]

def glifo(nome: str, riserva: str = "") -> str:
    """Il carattere dell'icona, per i pulsanti di sola icona (il font lo dà lo stile); riserva = emoji."""
    return _GLIFI[nome] if _font_icone() else riserva

def icona(nome: str, colore: str = "#52606D", px: int = 16) -> QIcon:
    """Icona da mettere accanto al testo di un pulsante; grigia quando il pulsante è spento."""
    from PySide6.QtGui import QPainter
    ic = QIcon()
    if not _font_icone():
        return ic
    for modo, col in ((QIcon.Mode.Normal, colore), (QIcon.Mode.Disabled, "#B8C0C9")):
        pm = QPixmap(px * 2, px * 2)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        f = QFont(_font_icone())
        f.setPixelSize(px * 2)
        p.setFont(f)
        p.setPen(QColor(col))
        p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, _GLIFI[nome])
        p.end()
        pm.setDevicePixelRatio(2)
        ic.addPixmap(pm, modo)
    return ic


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
    sig_video    = Signal(list)   # playlist: [(vid, txt)] appena ogni video è scaricato

    def __init__(self, url: str, output_dir: str, state: dict, direct_download: bool = False,
                 playlist: bool = False):
        super().__init__()
        self.url            = url
        self.output_dir     = output_dir
        self.state          = state
        self.direct_download = direct_download
        self.playlist       = playlist

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

        if self.playlist:
            # Un video alla volta: ognuno va subito in coda (import) o nell'elenco finale
            # (download diretto); il riepilogo lo scrive il motore nel log
            scaricati = []

            async def cb_video(res):
                scaricati.extend(res)
                self.sig_video.emit(res)

            await engine.download_playlist(self.url, self.output_dir, self.state,
                                           not self.direct_download, cb_video)
            self.result = scaricati if self.direct_download else []
            return

        # 1. Chiamiamo il download e ci fidiamo SOLO del motore
        # Il motore ora gestisce internamente sia il download nuovo 
        # sia il caso "già scaricato" se usiamo la logica corretta.
        self.result = await engine.download_youtube(
            self.url, self.output_dir, self.state,
            generate_txt=not self.direct_download
        )
        
        if not self.result:
            await cb_log("❌ Operazione fallita o annullata.", "red")


class TxtSearchWorker(QObject):
    """Cerca su YouTube il txt di uno o più video già scaricati, uno alla volta."""
    sig_uno  = Signal(str, dict)   # (nome video, risultato di VideoEngine.cerca_txt_youtube)
    sig_fine = Signal()

    def __init__(self, video: list, solo_data: bool = False):
        super().__init__()
        self.video = video
        self.solo_data = solo_data   # solo la data del titolo (verifica online)

    @Slot()
    def run(self):
        async def nop(*a):
            pass

        async def _cerca():
            engine = VideoEngine(log_cb=nop, progress_cb=nop)
            for vid in self.video:
                self.sig_uno.emit(vid, await engine.cerca_txt_youtube(vid, self.solo_data))

        try:
            asyncio.run(_cerca())
        except Exception as e:
            self.sig_uno.emit("", {"esito": "errore", "messaggio": str(e)})
        finally:
            self.sig_fine.emit()


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
                 is_running: bool, current_dir: str = "", parent=None,
                 date_tooltip: str | None = None, txt_in_ricerca: bool = False):
        super().__init__(parent)
        self.idx = idx
        self.vid = vid
        self.current_dir = current_dir

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
        self.btn_up   = _icon_btn(glifo("su", "▲"), "btn_card_move", "Sposta su", not is_first and not is_running)
        self.btn_down = _icon_btn(glifo("giu", "▼"), "btn_card_move", "Sposta giù", not is_last and not is_running)
        self.btn_cut  = _icon_btn(glifo("forbici", "✂"), "btn_card_cut", "Tagli manuali", not is_running)
        self.btn_del  = _icon_btn(glifo("chiudi", "✕"), "btn_card_delete", "Rimuovi", not is_running)

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
        self.txt_part.setText(f"{'TXT OK' if has_txt else 'TXT ⏳' if txt_in_ricerca else 'NO TXT'}")
        # Tooltip anteprima TXT (prima dei colori: trova anche le righe ignorate)
        self._txt_ignorate = []
        self._txt_fuori_ordine = []
        self._update_txt_tooltip()
        self.set_status(status_text, status_color)
        if date_tooltip:
            self.date_part.setToolTip(date_tooltip)

        # Click eventi
        self.txt_part.mousePressEvent = lambda e: self.sig_edit_txt.emit(self.vid)
        self.date_part.mousePressEvent = lambda e: self.sig_edit_date.emit(self.idx)

    def _update_txt_tooltip(self):
        """Mostra le prime 8 righe del TXT come tooltip sulla pillola sinistra."""
        if "⏳" in self.txt_part.text():
            self.txt_part.setToolTip("⏳ Ricerca del txt su YouTube in corso…\n"
                                     "Se il video si trova, il txt arriva da solo dalla descrizione.")
            return
        if "NO TXT" in self.txt_part.text():
            self.txt_part.setToolTip("Nessun file TXT associato.\nClicca per crearne uno.")
            return
        txt_path = os.path.join(
            self.current_dir,
            os.path.splitext(self.vid)[0] + ".txt"
        )
        if not os.path.exists(txt_path):
            self.txt_part.setToolTip("File TXT non trovato sul disco.")
            return
        try:
            with open(txt_path, "r", encoding="utf-8", errors="replace") as f:
                lines = [l.rstrip() for l in f.readlines() if l.strip()]
            preview = "\n".join(lines[:8])
            if len(lines) > 8:
                preview += f"\n... ({len(lines) - 8} righe in più)"
            # Righe che non diventano un taglio: pillola arancione ed elenco nel tooltip
            self._txt_ignorate = righe_txt_ignorate(txt_path)
            if self._txt_ignorate:
                self.txt_part.setText("TXT OK ⚠️")
                elenco = "\n".join(f"  · {r}" for r in self._txt_ignorate[:8])
                if len(self._txt_ignorate) > 8:
                    elenco += f"\n  · ... e altre {len(self._txt_ignorate) - 8}"
                preview = (f"⚠️ Righe ignorate, non nel formato \"mm:ss - Nome\" "
                           f"({len(self._txt_ignorate)}):\n{elenco}\n"
                           f"Se sono spot, restano attaccati al precedente. "
                           f"Clicca per correggere.\n\n{preview}")
            # Orari doppi o che tornano indietro: può essere giusto, ma spesso è un errore
            self._txt_fuori_ordine = righe_txt_fuori_ordine(txt_path)
            if self._txt_fuori_ordine:
                self.txt_part.setText("TXT OK ⚠️")
                elenco = "\n".join(f"  · {r}" for r in self._txt_fuori_ordine[:8])
                if len(self._txt_fuori_ordine) > 8:
                    elenco += f"\n  · ... e altre {len(self._txt_fuori_ordine) - 8}"
                preview = (f"⚠️ Orario uguale o precedente alla riga prima "
                           f"({len(self._txt_fuori_ordine)}):\n{elenco}\n"
                           f"Va bene solo se iniziano davvero nello stesso secondo: "
                           f"altrimenti clicca e correggi l'orario.\n\n{preview}")
            self.txt_part.setToolTip(preview)
        except Exception:
            self.txt_part.setToolTip("Impossibile leggere il file TXT.")

    def set_status(self, text: str, color: str):
        """Aggiorna i testi e decide i colori delle due metà della pillola con palette Soft."""
        # Estraiamo la parte della data
        data_display = text.split("Data:")[-1].strip() if "Data:" in text else text
        self.date_part.setText(data_display)
        
        # Recuperiamo lo stato del TXT dal widget stesso
        has_txt = "TXT OK" in self.txt_part.text()
        
        # --- NUOVA LOGICA COLORI SOFT (v0.86) ---
        # (sfondo, testo): tinte tenui, il testo è il tono scuro della stessa famiglia
        COLOR_VERDE   = ("#E3F3E8", "#1B6B3A")
        COLOR_ROSSO   = ("#FBE4E2", "#A3271F")
        COLOR_ARANCIO = ("#FDEBCF", "#8A5200")
        COLOR_BLU     = ("#E1EDF8", "#134A7C")
        COLOR_ATTESA  = ("#E6EBF0", "#4A5D6E")   # ricerca o verifica online in corso
        
        # 1. Sinistra (TXT): Verde se OK, Arancio se ha righe ignorate, Rosso se manca
        da_controllare = self._txt_ignorate or self._txt_fuori_ordine
        txt_bg = (COLOR_ARANCIO if da_controllare else COLOR_VERDE) if has_txt else COLOR_ROSSO
        if "⏳" in self.txt_part.text():
            txt_bg = COLOR_ATTESA   # ricerca del txt su YouTube in corso
        
        # 2. Destra (DATA): Basata sulle icone
        if "⏳" in text:
            date_bg = COLOR_ATTESA   # verifica online in corso
        elif "✅" in text:
            date_bg = COLOR_VERDE
        elif "⚠️" in text:
            date_bg = COLOR_ARANCIO
        elif "⛔" in text or "MANCANTE" in text or "Invalida" in text:
            date_bg = COLOR_ROSSO
        else:
            # Gestione del fallback per il colore passato (se è blu o grigio, lo addolciamo)
            if color.lower() in ["blue", "#2196f3"]:
                date_bg = COLOR_BLU
            elif color.lower() in ["orange", "#ff9500"]:
                date_bg = COLOR_ARANCIO
            elif color.lower() in ["#4caf50", "#4cd964", "green"]:
                date_bg = COLOR_VERDE
            elif color.lower() in ["#ff3b30", "red"]:
                date_bg = COLOR_ROSSO
            else:
                date_bg = COLOR_ATTESA

        # Applichiamo lo stile CSS (Mantenendo i bordi per l'effetto "badge unico")
        common = "padding: 3px 10px; font-weight: 600; font-size: 11px;"

        self.txt_part.setStyleSheet(
            f"background-color: {txt_bg[0]}; color: {txt_bg[1]}; {common} "
            "border-top-left-radius: 6px; border-bottom-left-radius: 6px; "
            "border-top-right-radius: 0px; border-bottom-right-radius: 0px; "
            "border-right: 1px solid #FFFFFF;"
        )
        self.date_part.setStyleSheet(
            f"background-color: {date_bg[0]}; color: {date_bg[1]}; {common} "
            "border-top-left-radius: 0px; border-bottom-left-radius: 0px; "
            "border-top-right-radius: 6px; border-bottom-right-radius: 6px;"
        )

        # Tooltip pillola DATA
        if "⏳" in text:
            self.date_part.setToolTip("⏳ Verifica online della data in corso…\n"
                                      "Tra qualche secondo diventa verde, se il titolo YouTube la conferma.")
        elif "✅" in text and "Elaborato" in text:
            self.date_part.setToolTip("✅ Video già elaborato\nClicca per modificare la data.")
        elif "✅" in text and "manuale" in text.lower():
            self.date_part.setToolTip("✅ Data inserita manualmente\nClicca per modificarla.")
        elif "✅" in text:
            self.date_part.setToolTip("✅ Data rilevata automaticamente dal nome file\nClicca per modificarla.")
        elif "⚠️" in text and "MANCANTE" in text:
            self.date_part.setToolTip("⚠️ Data non trovata nel nome file\nClicca per inserirla manualmente.")
        elif "⚠️" in text:
            self.date_part.setToolTip("⚠️ Data ambigua — potrebbe non essere corretta\nClicca per verificarla.")
        elif "⛔" in text:
            self.date_part.setToolTip("⛔ Data non valida\nClicca per correggerla.")
        else:
            self.date_part.setToolTip("Clicca per modificare la data.")

# ══════════════════════════════════════════════════════════════════════════
# FINESTRA IMPOSTAZIONI
# ══════════════════════════════════════════════════════════════════════════
class SettingsDialog(QDialog):
    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Impostazioni Avanzate")
        self.setFixedSize(780, 430)
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

            # i titoli nel codice hanno un'emoji davanti e sono in maiuscolo: si mostrano puliti
            pulito = re.sub(r"^[^A-Za-zÀ-ÿ]+", "", title).capitalize()
            lbl_title = QLabel(pulito)
            lbl_title.setObjectName("settings_group_title")
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
             "Soglia di luminosità per considerare un frame nero (0-1). Default: 0.1\n"
             "Se in uno stacco non trova un nero, il programma riprova da solo\n"
             "con +0.05 e +0.10 (neri 'grigi' delle registrazioni VHS)."),
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
             "Distanza massima in secondi tra il timestamp TXT e la fine del nero. Default: 2.0"),
        ]))
        col_dx.addStretch()

        cols.addLayout(col_sx)
        cols.addLayout(col_dx)
        layout.addLayout(cols)

        # Checkbox comportamento
        self._auto_start = QCheckBox("Avvia elaborazione automaticamente dopo import da YouTube")
        self._auto_start.setChecked(settings.get("auto_start_after_yt", False))
        self._auto_start.setToolTip("Se attivo, avvia subito l'elaborazione dopo aver importato un video da YouTube")
        layout.addWidget(self._auto_start)

        self._use_master = QCheckBox("Usa il master (metodo classico, più lento)")
        self._use_master.setChecked(settings.get("use_master", False))
        self._use_master.setToolTip(
            "Spento (default): neri e tagli vengono fatti direttamente sul video originale.\n"
            "Stessa precisione al fotogramma, una ricodifica in meno: qualità più alta,\n"
            "file più leggeri e niente file temporaneo.\n\n"
            "Acceso: crea prima un master con un keyframe per ogni fotogramma e taglia da\n"
            "quello, come nelle versioni fino alla 1.3.")
        layout.addWidget(self._use_master)

        # Bottoni
        btn_row = QHBoxLayout()
        btn_save  = QPushButton("Salva")
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
                "parallel_cuts": "0"}
        for k, e in self._entries.items():
            e.setText(defs[k])
        self._use_master.setChecked(False)

    def get_values(self) -> dict:
        vals = {k: e.text() for k, e in self._entries.items()}
        vals["auto_start_after_yt"] = self._auto_start.isChecked()
        vals["use_master"] = self._use_master.isChecked()
        return vals


# ══════════════════════════════════════════════════════════════════════════
# FINESTRA EDITOR TXT
# ══════════════════════════════════════════════════════════════════════════
class TxtEditorDialog(QDialog):
    def __init__(self, title: str, content: str, parent=None, vid_name: str | None = None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(900, 680)
        self.setModal(True)
        self._vid_name = vid_name
        self._ricerca  = None   # (thread, worker) della ricerca su YouTube in corso
        self.data_trovata = None   # data dal titolo YouTube, applicata al salvataggio

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        self._editor = QTextEdit()
        self._editor.setObjectName("txt_editor")
        self._editor.setPlainText(content)
        layout.addWidget(self._editor)

        btn_row = QHBoxLayout()
        btn_save   = QPushButton("Salva modifiche")
        btn_cancel = QPushButton("Annulla")
        btn_save.setObjectName("btn_txt_save")
        btn_cancel.setObjectName("btn_dlg_cancel")
        btn_save.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_save)
        btn_row.addWidget(btn_cancel)
        if vid_name:
            # Recupera il txt dalla descrizione del video su YouTube, cercandolo per titolo
            self._btn_cerca = QPushButton("Cerca su YouTube")
            self._btn_cerca.setIcon(icona("cerca", "#52606D"))
            self._btn_cerca.setObjectName("btn_dlg_reset")
            self._btn_cerca.setToolTip("Cerca su YouTube il video con questo titolo e\n"
                                       "ricava il txt dai timestamp della descrizione.")
            self._btn_cerca.clicked.connect(self._cerca_youtube)
            btn_row.addWidget(self._btn_cerca)
            self._lbl_cerca = QLabel("")
            self._lbl_cerca.setWordWrap(True)
            btn_row.addWidget(self._lbl_cerca, stretch=1)
        else:
            btn_row.addStretch()
        layout.addLayout(btn_row)
        self.finished.connect(self._stacca_ricerca)

    def get_text(self) -> str:
        return self._editor.toPlainText()

    def _cerca_youtube(self):
        self._btn_cerca.setEnabled(False)
        self._lbl_cerca.setText("Ricerca su YouTube in corso...")
        thread, worker = QThread(), TxtSearchWorker([self._vid_name])
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.sig_uno.connect(self._on_trovato)
        worker.sig_fine.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        # Il thread deve sopravvivere anche se la finestra viene chiusa prima della risposta
        app = self.parent()
        app._ricerche_txt.append((thread, worker))
        thread.finished.connect(lambda: app._ricerche_txt.remove((thread, worker)))
        self._ricerca = (thread, worker)
        thread.start()

    @Slot(str, dict)
    def _on_trovato(self, vid: str, r: dict):
        self._btn_cerca.setEnabled(True)
        self._ricerca = None
        if r["esito"] != "ok":
            self._lbl_cerca.setText(f"⚠️ {r['messaggio'][:1].upper()}{r['messaggio'][1:]}.")
            return
        attuale = self.get_text().strip()
        if attuale and attuale != r["txt"].strip():
            risposta = QMessageBox.question(
                self, "Sostituire il testo?",
                "L'editor contiene già del testo.\nSostituirlo con quello trovato su YouTube?")
            if risposta != QMessageBox.StandardButton.Yes:
                self._lbl_cerca.setText("Testo trovato ma non inserito.")
                return
        self._editor.setPlainText(r["txt"])
        self.data_trovata = r.get("data")
        data = f" Data dal titolo: {self.data_trovata}." if self.data_trovata else ""
        self._lbl_cerca.setText(f"✅ {r['messaggio'][:1].upper()}{r['messaggio'][1:]}.{data} "
                                "Controlla e premi Salva.")

    def _stacca_ricerca(self):
        if self._ricerca:
            try:
                self._ricerca[1].sig_uno.disconnect(self._on_trovato)
            except (RuntimeError, TypeError):
                pass
            self._ricerca = None


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
        clean_date = current_date if current_date and "-" in current_date else "01-01-1980"
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
        btn_ok.setObjectName("btn_save_date")
        btn_ok.clicked.connect(self.validate_and_accept)
        btn_ok.setDefault(True)  # Invio → Salva

        btn_cancel = QPushButton("Annulla")
        btn_cancel.clicked.connect(self.reject)

        btn_layout.addWidget(btn_ok)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

        self.setModal(True)


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
        self.setWindowTitle("Storico elaborazioni")
        self.setMinimumSize(780, 480)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # Titolo
        lbl = QLabel("Storico dei video elaborati — clicca il cestino per rimuovere una voce")
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

        def _parse_date(entry):
            try:
                return datetime.strptime(entry.get("data_elaborazione", ""), "%d-%m-%Y %H:%M")
            except Exception:
                return datetime.min

        for vid, entry in sorted(storico.items(),
                                  key=lambda x: _parse_date(x[1]),
                                  reverse=True):
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setItem(row, 0, QTableWidgetItem(entry.get("data_elaborazione", "?")))
            self._table.setItem(row, 1, QTableWidgetItem(vid))
            self._table.setItem(row, 2, QTableWidgetItem(entry.get("canale", "")))
            self._table.setItem(row, 3, QTableWidgetItem(str(entry.get("n_spot", ""))))

            # Bottone elimina riga
            btn_del = QPushButton(glifo("cestino", "🗑"))
            btn_del.setObjectName("btn_icona_rossa")
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
        # Lista dei nomi dalla descrizione YouTube (video senza timestamp): ogni "+"
        # scrive l'orario col nome successivo
        self._nomi  = []
        self._salti = 0          # spostamenti col pulsante (nomi senza un nero proprio)
        self._ricerca = None     # (thread, worker) della ricerca su YouTube in corso
        self.data_trovata = None # data dal titolo YouTube, applicata al salvataggio
        self._neri = []          # (secondo, pulsante "+") dei neri trovati
        self._anteprima = None   # processo ffplay dell'anteprima in corso
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

        lbl_neri = QLabel("Neri trovati — clicca per inserire")
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

        lbl_editor = QLabel("Editor TXT — scrivi il nome dopo il timestamp")
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

        # Riga "prossimo nome" (i pulsanti compaiono solo con la lista dei nomi da YouTube)
        nomi_row = QHBoxLayout()
        self._lbl_nomi = QLabel("")
        self._lbl_nomi.setWordWrap(True)
        self._lbl_nomi.setStyleSheet("font-size: 11px;")
        self._btn_indietro = QPushButton(glifo("indietro", "⏮"))
        self._btn_indietro.setObjectName("btn_icona")
        self._btn_indietro.setToolTip("Torna al nome precedente della lista")
        self._btn_salta = QPushButton("Salta nome")
        self._btn_salta.setToolTip("Salta il prossimo nome della lista\n"
                                   "(es. uno spot attaccato al precedente, senza nero)")
        self._btn_indietro.clicked.connect(lambda: self._sposta_nome(-1))
        self._btn_salta.clicked.connect(lambda: self._sposta_nome(1))
        self._btn_indietro.hide()
        self._btn_salta.hide()
        nomi_row.addWidget(self._lbl_nomi, stretch=1)
        nomi_row.addWidget(self._btn_indietro)
        nomi_row.addWidget(self._btn_salta)
        right.addLayout(nomi_row)
        self._editor.textChanged.connect(self._aggiorna_nomi)
        self._editor.textChanged.connect(self._aggiorna_neri_usati)
        self.finished.connect(self._chiudi_anteprima)

        btn_row = QHBoxLayout()
        btn_save   = QPushButton("Salva txt")
        btn_open   = QPushButton("Apri video")
        btn_open.setIcon(icona("avvia", "#1D3B53"))
        btn_cancel = QPushButton("Annulla")
        btn_save.setObjectName("btn_txt_save")
        btn_cancel.setObjectName("btn_dlg_cancel")
        btn_save.clicked.connect(self._save)
        btn_cancel.clicked.connect(self.reject)
        btn_open.clicked.connect(self._open_video)
        btn_row.addWidget(btn_save)
        btn_row.addWidget(btn_open)
        btn_row.addWidget(btn_cancel)
        btn_row.addStretch()
        right.addLayout(btn_row)

        root.addLayout(right, stretch=1)

        # Collega il segnale thread-safe al metodo UI
        self._sig_blacks_ready.connect(self._on_blacks_ready)
        # Avvia il blackdetect in background dopo che il dialog è visibile
        QTimer.singleShot(100, self._run_blackdetect)

        # Senza txt: intanto cerca il video su YouTube (txt completo o lista dei nomi)
        if not os.path.exists(txt_path) and hasattr(parent, "_avvia_ricerca_youtube"):
            self._lbl_nomi.setText("🔎 Ricerca della lista dei nomi su YouTube...")
            self._ricerca = parent._avvia_ricerca_youtube([os.path.basename(vid_path)],
                                                          self._on_youtube)
            self.finished.connect(self._stacca_ricerca)

    # ── LISTA DEI NOMI DA YOUTUBE ─────────────────────────────────────────
    def _stacca_ricerca(self):
        if self._ricerca:
            try:
                self._ricerca[1].sig_uno.disconnect(self._on_youtube)
            except (RuntimeError, TypeError):
                pass
            self._ricerca = None

    def _solo_modello(self) -> bool:
        """L'editor contiene ancora solo la riga iniziale vuota ("00:00 - ")."""
        return self._editor.toPlainText().strip() in ("", "00:00 -")

    @Slot(str, dict)
    def _on_youtube(self, vid: str, r: dict):
        self._ricerca = None
        self.data_trovata = r.get("data")
        if r["esito"] == "ok":
            # La descrizione ha già i timestamp: txt completo, se non hai ancora scritto nulla
            if self._solo_modello():
                self._editor.setPlainText(r["txt"])
                self._lbl_nomi.setText("✅ Trovato su YouTube il txt completo con i timestamp: "
                                       "controllalo e premi Salva.")
            else:
                self._lbl_nomi.setText("ℹ️ Su YouTube c'è il txt completo con i timestamp "
                                       "(🔎 Cerca su YouTube nell'editor txt): qui non l'ho inserito.")
            return
        if not r.get("nomi"):
            self._lbl_nomi.setText(f"ℹ️ Nessuna lista di nomi su YouTube ({r['messaggio']}).")
            return
        self._nomi = r["nomi"]
        if self._solo_modello():
            # Il primo spot parte sempre da 00:00
            self._editor.setPlainText(f"00:00 - {self._nomi[0]}")
            cursor = self._editor.textCursor()
            cursor.movePosition(cursor.MoveOperation.End)
            self._editor.setTextCursor(cursor)
        self._btn_indietro.show()
        self._btn_salta.show()
        self._aggiorna_nomi()

    def _indice_nome(self) -> int:
        """
        Posizione del prossimo nome: si conta dalle righe con un orario già nell'editor,
        così cancellando una riga sbagliata il nome torna giusto da solo.
        """
        righe = re.findall(r"^\s*\d{1,2}:\d{2}", self._editor.toPlainText(), re.M)
        return len(righe) + self._salti

    def _prossimo_nome(self) -> str:
        i = self._indice_nome()
        return self._nomi[i] if 0 <= i < len(self._nomi) else ""

    def _sposta_nome(self, passo: int):
        # Mai prima dell'inizio della lista
        if self._indice_nome() + passo >= 0:
            self._salti += passo
        self._aggiorna_nomi()

    def _aggiorna_nomi(self):
        if not self._nomi:
            return
        i = self._indice_nome()
        if i < len(self._nomi):
            self._lbl_nomi.setText(f"📋 Prossimo nome: <b>{html.escape(self._nomi[i])}</b> "
                                   f"({i + 1}/{len(self._nomi)}) — clicca un nero a sinistra")
        else:
            self._lbl_nomi.setText(f"✅ Tutti i {len(self._nomi)} nomi della lista sono inseriti.")

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

        self._status_lbl.setText(f"{len(b_starts)} neri trovati — clicca per inserire, "
                                 f"▶ per vederlo")

        prec = None
        for ts in b_starts:
            # Converte secondi in HH:MM:SS
            h  = int(ts) // 3600
            m  = (int(ts) % 3600) // 60
            s  = int(ts) % 60
            ts_str = f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"
            # Distanza dal nero precedente: gli spot durano quasi sempre 15/20/30/60 s,
            # un nero a pochi secondi dal precedente è di solito dentro uno spot
            dist = f"  (+{ts - prec:.0f}s)" if prec is not None else ""
            prec = ts

            riga = QHBoxLayout()
            riga.setSpacing(4)
            btn = QPushButton(f"+ {ts_str}{dist}")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            # Cattura ts_str per valore nel lambda
            btn.clicked.connect(lambda checked, t=ts_str: self._insert_timestamp(t))
            btn_play = QPushButton(glifo("avvia", "▶"))
            btn_play.setObjectName("btn_icona")
            btn_play.setFixedWidth(30)
            btn_play.setToolTip("Guarda qualche secondo intorno a questo nero")
            btn_play.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_play.clicked.connect(lambda checked, t=ts, e=ts_str: self._anteprima_nero(t, e))
            riga.addWidget(btn, stretch=1)
            riga.addWidget(btn_play)
            self._btn_layout.addLayout(riga)
            self._neri.append((int(ts), btn))
        self._aggiorna_neri_usati()

    _STILE_NERO = ("text-align: left; padding: 4px 8px; border-radius: 6px; min-width: 0px; "
                   "font-weight: 400; font-family: 'Cascadia Mono', 'Consolas', monospace; ")

    def _aggiorna_neri_usati(self):
        """I neri già scritti nell'editor diventano grigi, così si vede a che punto si è."""
        usati = {int(get_seconds(t)) for t in
                 re.findall(r"^\s*(\d{1,2}:\d{2}(?::\d{2})?)", self._editor.toPlainText(), re.M)}
        for sec, btn in self._neri:
            if sec in usati:
                btn.setStyleSheet(self._STILE_NERO + "background: #F5F6F8; color: #B8C0C9; "
                                  "border: 1px solid #E4E7EB;")
            else:
                btn.setStyleSheet(self._STILE_NERO + "background: #EEF2F6; color: #1D3B53; "
                                  "border: 1px solid #DCE3EA;")

    def _anteprima_nero(self, ts: float, ts_str: str):
        """Mostra con ffplay 5 secondi intorno al nero (2 prima, 3 dopo), in una finestrella."""
        self._chiudi_anteprima()
        cmd = [get_tool_path("ffplay"), "-hide_banner", "-loglevel", "error", "-autoexit",
               "-ss", f"{max(0.0, ts - 2):.2f}", "-t", "5", "-x", "640", "-y", "480",
               "-window_title", f"Anteprima nero {ts_str}", self.vid_path]
        try:
            self._anteprima = subprocess.Popen(
                cmd, creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
        except OSError as e:
            QMessageBox.warning(self, "Anteprima non disponibile",
                                f"Non riesco ad avviare ffplay (di solito è installato insieme "
                                f"a ffmpeg):\n{e}")

    def _chiudi_anteprima(self):
        if self._anteprima and self._anteprima.poll() is None:
            self._anteprima.terminate()
        self._anteprima = None

    def _insert_timestamp(self, ts_str: str):
        """Inserisce il timestamp (col prossimo nome della lista, se c'è) nella riga corrente."""
        nome = self._prossimo_nome()
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
            cursor.insertText(f"\n{ts_str} - {nome}")
        else:
            # Riga vuota: inserisci qui
            cursor.insertText(f"{ts_str} - {nome}")
        self._editor.setTextCursor(cursor)
        self._editor.setFocus()

    def _open_video(self):
        """Apre il video con il player predefinito del sistema."""
        try:
            if sys.platform == "win32":
                os.startfile(self.vid_path)
            elif sys.platform == "darwin":
                subprocess.run(["open", self.vid_path])
            else:
                subprocess.run(["xdg-open", self.vid_path])
        except Exception as e:
            QMessageBox.warning(self, "Errore", f"Impossibile aprire il video:\n{e}")

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
    _sig_yt_video        = Signal(list)
    _sig_yt_info         = Signal(str, object)
    _sig_duration        = Signal(float, int)
    _sig_ytdlp_scaricato = Signal(str)   # "" = riuscito, altrimenti l'errore

    def __init__(self):
        super().__init__()
        self._ytdlp_in_scarico, self._ytdlp_dopo = False, None
        self.setWindowTitle("Spot Cutter - Organizzatore Spot TV")
        self.setWindowIcon(QIcon(resource_path("Spot_Cutter.ico")))
        self.resize(1200, 900)
        self.setMinimumSize(1000, 700)

        # 1. Inizializza lo STATO (Incluso il caricamento impostazioni)
        base_folder = os.path.dirname(os.path.abspath(__file__))
        # Usa la cartella Video di Windows come default, con fallback a Documenti
        # Usa le API Windows per trovare la cartella Video reale
        # anche se l'utente l'ha spostata in una partizione diversa
        try:
            import ctypes.wintypes
            buf = ctypes.create_unicode_buffer(ctypes.wintypes.MAX_PATH)
            ctypes.windll.shell32.SHGetFolderPathW(0, 0x000e, 0, 0, buf)
            _videos = buf.value  # 0x000e = CSIDL_MYVIDEO
            if not _videos or not os.path.exists(_videos):
                raise ValueError
        except Exception:
            _home   = os.path.expanduser("~")
            _videos = os.path.join(_home, "Videos")
            if not os.path.exists(_videos):
                _videos = os.path.join(_home, "Documents")
        default_path = os.path.join(_videos, "Libreria Spot")

        self.settings_storage = QSettings("SpotCutter", "SpotCutterUltra")
        self.work_dir = str(self.settings_storage.value("work_dir", default_path))
        self._ricerche_txt = []   # ricerche txt su YouTube in corso: (thread, worker)
        self._date_verificate = set()   # video già mandati alla verifica online della data
        self._txt_auto_cartelle = {}    # video in ricerca automatica del txt -> cartella del video
        self._txt_in_ricerca = set()    # ricerca automatica del txt in corso: pillola con la clessidra
        self._date_in_verifica = set()  # verifica in corso: pillola grigio-azzurra con la clessidra
        self._date_esiti = {}           # video -> perché la data non è stata confermata online
        self._date_youtube = {}         # video -> data presa dal titolo YouTube
        self._yt_playlist = False           # scelta "Intera playlist" per il prossimo download
        self._yt_playlist_attiva = False    # download di playlist in corso
        self._yt_playlist_aggiunti = 0      # video della playlist entrati in coda

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
        self._sig_yt_video.connect(self._on_yt_video)
        self._sig_yt_info.connect(self._yt_after_info) # Aggiunto qui
        self._sig_duration.connect(self._on_duration_ready)
        self._sig_ytdlp_scaricato.connect(self._on_ytdlp_scaricato)

        # 5. Threading
        self._worker_thread = None
        self._yt_thread     = None
        self._sort_key      = ""
        self._sort_asc      = True

        # 6. Check iniziali
        if not os.path.exists(self.work_dir):
            try: os.makedirs(self.work_dir)
            except: pass

        QTimer.singleShot(800, self._startup_checks) 
        QTimer.singleShot(1200, self._proponi_ripresa_sessione)

    def _update_duration_label(self):
        """Calcola in background la durata totale dei video in coda."""
        queue = self.state.get("queue_files", [])
        current_dir = self.state.get("current_dir", "")
        if not queue:
            self._lbl_duration.setText("—")
            return
        self._lbl_duration.setText("calcolo...")

        def _worker():
            total = 0.0
            for vid, _, _ in queue:
                path = os.path.join(current_dir, vid)
                total += get_video_duration(path)
            # Torna sul thread UI via segnale
            self._sig_duration.emit(total, len(queue))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_duration_ready(self, total: float, count: int):
        """Aggiorna il label durata sul thread UI."""
        def hm(sec):
            h, m = int(sec) // 3600, (int(sec) % 3600) // 60
            return f"{h}h {m:02d}m" if h > 0 else f"{m}m"
        testo = f"{count} video · {hm(total)} di video"
        # Tempo di lavoro: dalla velocità misurata su questo computer nelle elaborazioni
        # fatte finora, con o senza master secondo l'opzione attiva. Niente misura, niente stima.
        velocita = self.settings_storage.value(self._chiave_velocita(), 0.0, type=float)
        if velocita > 0 and total > 0:
            lavoro = total * velocita
            testo += " · lavoro: " + ("meno di 1m" if lavoro < 60 else f"circa {hm(lavoro + 30)}")
        self._lbl_duration.setText(testo)

    def _chiave_velocita(self, master: bool | None = None) -> str:
        master = bool(self._s.get("use_master", False)) if master is None else master
        return "velocita_master" if master else "velocita_diretto"

    def _impara_velocita(self):
        """
        Dai video appena finiti: secondi di lavoro per secondo di video, con e senza master.
        La media si aggiorna piano (60% il valore di prima, 40% questa sessione), così un
        video anomalo non la stravolge; resta nelle impostazioni di questo computer.
        """
        tempi = self.state.pop("tempi_video", [])
        for master in (False, True):
            durata = sum(d for d, _, m in tempi if m == master)
            lavoro = sum(t for _, t, m in tempi if m == master)
            if durata < 30:
                continue
            chiave = self._chiave_velocita(master)
            prima = self.settings_storage.value(chiave, 0.0, type=float)
            ora = lavoro / durata
            self.settings_storage.setValue(chiave, ora if prima <= 0 else 0.6 * prima + 0.4 * ora)

    def _on_expand_log(self, checked: bool):
        """Espande o riduce il log con animazione."""
        self._log.setMaximumHeight(16777215)  # rimuove il limite fisso durante l'animazione
        anim = QPropertyAnimation(self._log, b"maximumHeight")
        anim.setDuration(200)
        anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        if checked:
            anim.setStartValue(130)
            anim.setEndValue(400)
        else:
            anim.setStartValue(400)
            anim.setEndValue(130)
        anim.finished.connect(lambda: self._log.setFixedHeight(400 if checked else 130))
        anim.start()
        self._anim_log = anim  # mantieni riferimento per evitare garbage collection

    def _on_sort(self, key: str):
        """Ordina la coda per la chiave selezionata."""
        if self._sort_key == key:
            self._sort_asc = not self._sort_asc  # inverte direzione
        else:
            self._sort_key = key
            self._sort_asc = True

        # Aggiorna aspetto bottoni
        for k in ["nome", "data", "stato"]:
            btn = getattr(self, f"_btn_sort_{k}", None)
            if btn:
                btn.setChecked(k == self._sort_key)
                if k == self._sort_key:
                    arrow = " ↑" if self._sort_asc else " ↓"
                    btn.setText(k.capitalize() + arrow)
                else:
                    btn.setText(k.capitalize())

        # Ordina queue_files
        queue = self.state.get("queue_files", [])
        if not queue:
            return

        if key == "nome":
            queue.sort(key=lambda x: x[0].lower(), reverse=not self._sort_asc)
        elif key == "data":
            def _date_key(item):
                from utils import extract_date_info
                _, anno, _ = extract_date_info(item[0])
                # Usa data manuale se presente
                if item[2]:
                    return item[2]
                return anno
            queue.sort(key=_date_key, reverse=not self._sort_asc)
        elif key == "stato":
            # Ordine: NO TXT prima, poi data ambigua, poi ok
            def _stato_key(item):
                has_txt = item[1] is not None
                if not has_txt:
                    return 0
                return 1
            queue.sort(key=_stato_key, reverse=not self._sort_asc)

        self.state["queue_files"] = queue
        self.render_queue()

    def _on_save_session(self):
        """Salva la coda corrente in un file JSON."""
        if not self.state.get("queue_files"):
            self._on_log("⚠️ Coda vuota — nulla da salvare.", "orange")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Salva sessione", 
            os.path.join(self.state.get("current_dir", ""), "sessione.json"),
            "File sessione (*.json)"
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._dati_sessione(), f, indent=2, ensure_ascii=False)
            self._on_log(f"💾 Sessione salvata: {os.path.basename(path)}", "green")
        except Exception as e:
            self._on_log(f"⚠️ Errore salvataggio sessione: {e}", "red")

    def _on_load_session(self):
        """Carica una sessione salvata da file JSON."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Carica sessione", "", "File sessione (*.json)"
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                self._applica_sessione(json.load(f))
            self._on_log(f"📂 Sessione caricata: {len(self.state['queue_files'])} video", "green")
        except Exception as e:
            self._on_log(f"⚠️ Errore caricamento sessione: {e}", "red")

    # ── SESSIONE AUTOMATICA ───────────────────────────────────────────────
    # La coda viene salvata a ogni cambiamento in %APPDATA%\SpotCutter (sopravvive anche
    # al cambio di versione del programma); alla riapertura si può riprenderla.

    def _dati_sessione(self) -> dict:
        return {
            "current_dir": self.state.get("current_dir", ""),
            "work_dir":    self.state.get("work_dir", ""),
            "queue":       [{"vid": v, "txt": t, "manual_date": d}
                            for v, t, d in self.state["queue_files"]],
        }

    def _applica_sessione(self, session: dict):
        current_dir = session.get("current_dir", "")
        work_dir    = session.get("work_dir", "")
        if current_dir and os.path.exists(current_dir):
            self.state["current_dir"] = current_dir
        if work_dir and os.path.exists(work_dir):
            self.state["work_dir"] = work_dir
            self.work_dir = work_dir
        self.state["queue_files"] = [
            (item["vid"], item.get("txt"), item.get("manual_date"))
            for item in session.get("queue", [])
        ]
        self.render_queue()

    @staticmethod
    def _file_sessione_auto() -> str:
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(base, "SpotCutter", "sessione_auto.json")

    def _salva_sessione_auto(self):
        # Finché non si è risposto alla domanda di ripresa, il file dell'ultima volta non si tocca
        if not getattr(self, "_sessione_auto_pronta", False):
            return
        path = self._file_sessione_auto()
        try:
            if self.state.get("queue_files"):
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(self._dati_sessione(), f, indent=2, ensure_ascii=False)
            elif os.path.exists(path):
                os.remove(path)
        except OSError:
            pass

    def _proponi_ripresa_sessione(self):
        try:
            path = self._file_sessione_auto()
            if os.path.exists(path) and not self.state.get("queue_files"):
                with open(path, "r", encoding="utf-8") as f:
                    session = json.load(f)
                n = len(session.get("queue", []))
                if n:
                    cartella = session.get("current_dir", "")
                    dove = f" dalla cartella\n{cartella}" if cartella else ""
                    risposta = QMessageBox.question(
                        self, "Riprendere la coda?",
                        f"L'ultima volta erano in coda {n} video{dove}.\n\nVuoi riprendere da lì?")
                    if risposta == QMessageBox.StandardButton.Yes:
                        self._sessione_auto_pronta = True
                        self._applica_sessione(session)
                        self._on_log(f"📂 Coda dell'ultima volta ripresa: {n} video.", "green")
        except (OSError, ValueError):
            pass
        finally:
            self._sessione_auto_pronta = True

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
            self._btn_work_dir.setText(f"  {os.path.basename(d) if os.path.basename(d) else d}")
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
        yt_lbl = QLabel("YouTube")
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
            self._btn_paste.setText(glifo("incolla", "📋"))
            self._btn_paste.setFont(QFont("Segoe UI Emoji", 12))

        yt_input_layout.addWidget(self._yt_entry)
        yt_input_layout.addWidget(self._btn_paste)
        layout.addLayout(yt_input_layout)

        # --- PILLOLA YOUTUBE (IMPORTA + DOWNLOAD DIRETTO) ---
        pill_layout = QHBoxLayout()
        pill_layout.setSpacing(0)

        # Pulsante Importa (Sinistro)
        self._btn_yt = QPushButton("Importa da YouTube")
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
            self._btn_dl.setText(glifo("scarica", "⬇"))

        pill_layout.addWidget(self._btn_yt)
        pill_layout.addWidget(self._btn_dl)
        layout.addLayout(pill_layout)

        sep1 = QFrame()
        sep1.setObjectName("separator")
        sep1.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sep1)

        # Sezione FILE LOCALI
        lbl_local = QLabel("File locali")
        lbl_local.setObjectName("lbl_section")
        layout.addWidget(lbl_local)

        # Bottoni file
        btn_folder = self._make_btn("Sfoglia cartella", "btn_folder", ico="cartella", colore="#1D3B53")
        btn_folder.clicked.connect(self._on_browse_folder)
        layout.addWidget(btn_folder)

        btn_files = self._make_btn("Aggiungi video", "btn_files", ico="video", colore="#1D3B53")
        btn_files.clicked.connect(self._on_add_files)
        layout.addWidget(btn_files)

        self._btn_clear = self._make_btn("Svuota coda", "btn_clear", ico="cestino")
        self._btn_clear.setEnabled(False)
        self._btn_clear.clicked.connect(self._on_clear_queue)
        layout.addWidget(self._btn_clear)

        sep2 = QFrame()
        sep2.setObjectName("separator")
        sep2.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sep2)

        lbl_folder = QLabel("Libreria")
        lbl_folder.setObjectName("lbl_section")
        layout.addWidget(lbl_folder)

        self._btn_work_dir = self._make_btn("Libreria Spot", "btn_work_dir", h=36, ico="cartella_aperta")
        self._btn_work_dir.setToolTip("Cambia la cartella dove verranno salvati i tagli")
        self._btn_work_dir.clicked.connect(self._on_choose_work_dir)
        layout.addWidget(self._btn_work_dir)

        btn_storico = self._make_btn("Storico elaborazioni", "btn_storico", h=36, ico="storico")
        btn_storico.setToolTip("Visualizza e gestisci lo storico dei video elaborati")
        btn_storico.clicked.connect(self._on_open_storico)
        layout.addWidget(btn_storico)

        btn_settings = self._make_btn("Impostazioni", "btn_settings", h=36, ico="impostazioni")
        btn_settings.setToolTip("Impostazioni Avanzate")
        btn_settings.clicked.connect(self._open_settings)
        layout.addWidget(btn_settings)

        layout.addStretch()

        # AVVIA / STOP
        self._btn_run = self._make_btn("Avvia", "btn_run", h=55, ico="avvia", colore="#FFFFFF")
        self._btn_run.setEnabled(False)
        self._btn_run.clicked.connect(lambda: self._on_run())
        layout.addWidget(self._btn_run)

        self._btn_stop = self._make_btn("Stop", "btn_stop", h=45)
        self._btn_stop.clicked.connect(self._on_stop)
        self._btn_stop.hide()
        layout.addWidget(self._btn_stop)

        parent_layout.addWidget(sb)

    def _make_btn(self, text, obj_name, h=40, ico=None, colore="#52606D"):
        """Crea un bottone sidebar — lo stile è definito nel QSS tramite objectName."""
        btn = QPushButton(("  " + text) if ico else text)
        btn.setObjectName(obj_name)
        btn.setFixedHeight(h)
        if ico:
            btn.setIcon(icona(ico, colore))
            btn.setIconSize(QSize(16, 16))
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
        stats_layout.setContentsMargins(16, 8, 16, 8)
        stats_layout.setSpacing(20)
        
        self._main_stat_labels = {}
        # Definiamo le icone per ogni categoria
        tooltips = {
            "spot":        "Spot pubblicitari generici",
            "promo":       "Promo e trailer di programmi TV",
            "bumper":      "Bumper — brevi stacchetti tra gli spot",
            "annunci":     "Annunci di palinsesto e comunicati",
            "natale":      "Spot e contenuti festivi (Natale, Capodanno...)",
            "cartelli":    "Cartelli e schermate fisse",
            "videosigle":  "Sigle dei contenitori cinematografici TV\n(es. Lunedì Cinema, I Filmissimi, I Bellissimi...)",
            "telegiornali":"Frammenti di telegiornale",
        }

        for key, label_text in self._NOMI_CONTATORI.items():
            lbl = QLabel(self._testo_contatore(label_text, 0))
            lbl.setObjectName(f"lbl_stat_{key}")
            lbl.setToolTip(tooltips.get(key, ""))
            stats_layout.addWidget(lbl)
            self._main_stat_labels[key] = lbl
            
        stats_layout.addStretch()
        layout.addWidget(stats_bar)

# Barra unificata: sessione + ordinamento + durata
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        # Etichetta SESSIONE
        lbl_sessione = QLabel("Sessione")
        lbl_sessione.setObjectName("lbl_section")
        toolbar.addWidget(lbl_sessione)

        # Pillola doppia salva/carica
        btn_save_session = QPushButton(glifo("salva", "💾"))
        btn_load_session = QPushButton(glifo("apri", "📂"))
        btn_save_session.setObjectName("btn_pill_left")
        btn_load_session.setObjectName("btn_pill_right")
        btn_save_session.setFixedSize(32, 28)
        btn_load_session.setFixedSize(32, 28)
        btn_save_session.setToolTip("Salva sessione")
        btn_load_session.setToolTip("Carica sessione")
        btn_save_session.clicked.connect(self._on_save_session)
        btn_load_session.clicked.connect(self._on_load_session)
        pill = QHBoxLayout()
        pill.setSpacing(0)
        pill.setContentsMargins(0, 0, 0, 0)
        pill.addWidget(btn_save_session)
        pill.addWidget(btn_load_session)
        toolbar.addLayout(pill)

        # Separatore verticale
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setObjectName("separator")
        toolbar.addWidget(sep)

        # Ordinamento
        lbl_sort = QLabel("Ordina:")
        lbl_sort.setObjectName("lbl_duration")
        toolbar.addWidget(lbl_sort)
        for key, label in [("nome", "Nome"), ("data", "Data"), ("stato", "Stato")]:
            btn = QPushButton(label)
            btn.setObjectName("btn_sort")
            btn.setFixedHeight(28)
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, k=key: self._on_sort(k))
            setattr(self, f"_btn_sort_{key}", btn)
            toolbar.addWidget(btn)

        sep_txt = QFrame()
        sep_txt.setFrameShape(QFrame.Shape.VLine)
        sep_txt.setObjectName("separator")
        toolbar.addWidget(sep_txt)

        self._btn_cerca_txt = QPushButton(" Cerca txt mancanti")
        self._btn_cerca_txt.setIcon(icona("cerca"))
        self._btn_cerca_txt.setObjectName("btn_sort")
        self._btn_cerca_txt.setFixedHeight(28)
        self._btn_cerca_txt.setToolTip("Per ogni video in coda senza txt cerca su YouTube il video\n"
                                       "con lo stesso titolo e crea il txt dai timestamp della descrizione.\n"
                                       "I txt già presenti non vengono mai toccati.")
        self._btn_cerca_txt.clicked.connect(self._on_cerca_txt_mancanti)
        toolbar.addWidget(self._btn_cerca_txt)

        toolbar.addStretch()

        # Durata totale a destra
        lbl_duration_title = QLabel("In coda:")
        lbl_duration_title.setObjectName("lbl_duration")
        self._lbl_duration = QLabel("—")
        self._lbl_duration.setObjectName("lbl_duration")
        self._lbl_duration.setToolTip("Durata totale dei video in coda e tempo di lavoro stimato.\n"
                                      "La stima usa la velocità misurata su questo computer nelle\n"
                                      "elaborazioni già fatte: compare dopo la prima.")
        toolbar.addWidget(lbl_duration_title)
        toolbar.addWidget(self._lbl_duration)

        layout.addLayout(toolbar)

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

        # Log console con bottone espandi
        log_header = QHBoxLayout()
        lbl_log = QLabel("Log")
        lbl_log.setObjectName("lbl_progress")
        btn_expand_log = QPushButton(glifo("espandi", "⛶"))
        btn_expand_log.setObjectName("btn_expand_log")
        btn_expand_log.setFixedSize(22, 22)
        btn_expand_log.setToolTip("Espandi/riduci log")
        btn_expand_log.setCheckable(True)
        btn_expand_log.clicked.connect(self._on_expand_log)
        log_header.addWidget(lbl_log)
        log_header.addStretch()
        log_header.addWidget(btn_expand_log)
        layout.addLayout(log_header)

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
        self._salva_sessione_auto()
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
            self._lbl_duration.setText("—")
            self._sync_buttons()
            return

        for i, (vid, txt, manual_date) in enumerate(queue):
            has_txt = False
            if txt is not None:
                txt_path = os.path.join(self.state.get("current_dir", ""), txt)
                if os.path.exists(txt_path) and os.path.getsize(txt_path) > 0:
                    has_txt = True
            
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
                st = f"⛔ Invalida: {date_to_check}" if date_to_check else "⛔ Nessuna data"
                sc = "#FF3B30"
            elif not date_to_check or date_to_check == "00-00-0000":
                st, sc = "⚠️ Data: MANCANTE", "#FF9500"
            elif manual_date:
                st, sc = f"✅ Data: {manual_date}", "#4CD964"
            elif auto_color == "green":
                st, sc = f"✅ Data: {ext_date}", "#4CD964"
            else:
                st, sc = f"⚠️ Data: {ext_date}", "#FF9500"

            # Verifica online: in corso (clessidra) o non riuscita (il motivo nel tooltip)
            manuale = manual_date and manual_date.strip() not in ("", "--")
            tip_data = None
            if not manuale and vid in self._date_in_verifica:
                st, sc = (f"Data: {ext_date} ⏳" if ext_date else "Data: verifica… ⏳"), "#78909C"
            elif not manuale and vid in self._date_esiti:
                tip_data = (f"⚠️ Data non confermata online: {self._date_esiti[vid]}.\n"
                            "Clicca per inserirla o correggerla.")
            elif manuale and is_valid:
                tip_data = ("✅ Data confermata dal titolo YouTube\nClicca per modificarla."
                            if self._date_youtube.get(vid) == manual_date
                            else "✅ Data inserita a mano\nClicca per modificarla.")

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
                is_running=running,
                current_dir=self.state.get("current_dir", ""),
                date_tooltip=None if is_done else tip_data,
                txt_in_ricerca=vid in self._txt_in_ricerca)

            card.sig_move_up.connect(self._move_item_up)
            card.sig_move_down.connect(self._move_item_down)
            card.sig_delete.connect(self._remove_item)
            card.sig_edit_txt.connect(self._open_txt_editor)
            card.sig_edit_date.connect(self._open_date_editor)
            card.sig_cut.connect(self._on_cut_manual)

            self._queue_layout.insertWidget(i, card)
            self.state["status_labels"][i] = card

        self._sync_buttons()
        self._update_duration_label()
        # I video appena entrati senza txt o con una data da confermare si cercano online
        QTimer.singleShot(0, self._verifica_date_online)

    def _non_pronti(self) -> list:
        """[(video, motivo)] dei video in coda che non si possono ancora elaborare."""
        cartella = self.state.get("current_dir", "")
        return [(v, m) for v, t, d in self.state.get("queue_files", [])
                if (m := motivo_non_pronto(v, t, d, cartella))]

    def _sync_buttons(self):
        """AVVIA è attivo se almeno un video è pronto: quelli non pronti si saltano."""
        queue = self.state.get("queue_files", [])
        running = self.state.get("running", False)

        non_pronti = self._non_pronti()
        pronti = len(queue) - len(non_pronti)
        can_start = pronti > 0 and not running
        if not running:
            if non_pronti and pronti:
                self._btn_run.setText(f"  Avvia ({pronti} di {len(queue)})")
            else:
                self._btn_run.setText("  Avvia")
            if non_pronti:
                elenco = "\n".join(f"  · {v[:60]} — {m}" for v, m in non_pronti[:8])
                if len(non_pronti) > 8:
                    elenco += f"\n  · ... e altri {len(non_pronti) - 8}"
                self._btn_run.setToolTip(("Verranno saltati e resteranno in coda:\n" if pronti
                                          else "Nessun video pronto:\n") + elenco)
            else:
                self._btn_run.setToolTip("")

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
            "white": "#DCE3EA", "grey": "#8FA1B3", "gray": "#8FA1B3",
            "cyan": "#5CC8D6", "blue": "#7DB7F0", "green": "#7BCB8E",
            "orange": "#F2B25C", "red": "#F0807A", "yellow": "#EDD97A",
            "magenta": "#C9A0DC",
        }
        hex_color = color_map.get(color.lower(), color
                                   if color.startswith("#") else "#DCE3EA")
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

    _NOMI_CONTATORI = {"spot": "Spot", "promo": "Promo", "bumper": "Bumper", "annunci": "Annunci",
                       "natale": "Natale", "cartelli": "Cartelli", "videosigle": "Sigle",
                       "telegiornali": "TG"}

    @staticmethod
    def _testo_contatore(nome: str, n: int) -> str:
        """Nome in grigio e numero nel colore della categoria (quello dell'etichetta, dallo stile)."""
        return f'<span style="color:#52606D; font-weight:400">{nome}</span>&nbsp;&nbsp;<b>{n}</b>'

    @Slot()
    def _on_stats_update(self):
        """Aggiorna i contatori delle statistiche nell'interfaccia"""
        # Definiamo i nomi visualizzati con le icone (coerenti con _build_main_area)
        display_names = self._NOMI_CONTATORI

        # Aggiorna solo le etichette dell'area principale
        for key, lbl in self._main_stat_labels.items():
            n = self.state["stats_counts"].get(key, 0)
            label_text = display_names.get(key, key.capitalize())
            lbl.setText(self._testo_contatore(label_text, n))

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

        self._impara_velocita()

        # Rimuove dalla coda i video completati (presenti nello storico), anche dopo uno
        # Stop: così premendo di nuovo Avvia si riparte da quelli che mancano
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
        saltati = list(self.state.get("saltati", []))
        if saltati:
            self._on_log("⏭️ 1 video saltato perché non pronto: resta in coda." if len(saltati) == 1 else
                         f"⏭️ {len(saltati)} video saltati perché non pronti: restano in coda.", "orange")
        if elapsed > 1 or saltati:
            QTimer.singleShot(50, lambda: self._show_finished_dialog(successo, m, s_, riepilogo, saltati))

    def _show_finished_dialog(self, successo: bool, m: int, s_: int, riepilogo: str, saltati=()):
        stato = "Completato! ✅" if successo else "Interrotto 🛑"
        
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Elaborazione terminata")
        msg_box.setIcon(QMessageBox.Icon.Information if successo else QMessageBox.Icon.Warning)
        
        testo_box = f"Lavoro {stato}\nTempo totale: {m}m {s_}s"
        if riepilogo:
            testo_box += f"\n\nCategorie elaborate:\n{riepilogo}"
        if saltati:
            elenco = "\n".join(f"  · {v[:60]} — {mot}" for v, mot in saltati[:8])
            if len(saltati) > 8:
                elenco += f"\n  · ... e altri {len(saltati) - 8}"
            testo_box += (f"\n\nSaltati perché non pronti ({len(saltati)}), restano in coda:\n{elenco}")
        
        msg_box.setText(testo_box)
        
        btn_open = msg_box.addButton("Apri cartella", QMessageBox.ButtonRole.ActionRole)
        btn_ok = msg_box.addButton("OK", QMessageBox.ButtonRole.AcceptRole)
        
        msg_box.exec()
        
        if msg_box.clickedButton() == btn_open:
            self._open_output_folder()


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
            
        self._btn_yt.setText("Importa da YouTube")
        self._on_progress(0, "Pronto.")
        
        playlist = self._yt_playlist_attiva
        self._yt_playlist_attiva = False

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

            btn_open = msg.addButton("Apri cartella", QMessageBox.ButtonRole.AcceptRole)
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
        if playlist:
            # Playlist: i video sono già entrati in coda uno alla volta (_on_yt_video)
            added_count = self._yt_playlist_aggiunti
        else:
            added_count = self._aggiungi_scaricati(result)
            if not result:
                self._on_log("ℹ️ Nessun nuovo video aggiunto (già scaricato o file non trovato).", "gray")

        self._sync_buttons()
        self.render_queue()

        # Avvio automatico dopo import YouTube se abilitato nelle impostazioni
        if self._s.get("auto_start_after_yt", False) and added_count > 0:
            self._on_run(conferma=False)

    def _aggiungi_scaricati(self, result: list) -> int:
        """Mette in coda i video scaricati (vid, txt); ritorna quanti sono stati aggiunti."""
        added_count = 0
        for vid, txt in result or []:
            if any(item[0] == vid for item in self.state["queue_files"]):
                self._on_log(f"⚠️ {vid} è già presente nella lista attuale.", "orange")
                continue
            self.state["queue_files"].append((vid, txt, None))
            added_count += 1
        if added_count > 0:
            s = "o" if added_count == 1 else "i"
            self._on_log(f"✅ {added_count} vide{s} aggiunt{s} alla coda con successo.", "green")
        return added_count

    @Slot(list)
    def _on_yt_video(self, result: list):
        """Playlist: un video appena scaricato entra subito in coda (solo in modalità import)."""
        if getattr(self, "_is_direct_download", False):
            return
        self._yt_playlist_aggiunti += self._aggiungi_scaricati(result)
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

    def _on_run(self, conferma: bool = True):
        """conferma=False per l'avvio automatico dopo un download: nessuna domanda."""
        if self.state["running"]:
            return

        # 1. FIX SICUREZZA: Controllo coda vuota per evitare crash nel worker
        if not self.state.get("queue_files"):
            self._on_log("⚠️ Coda vuota. Nulla da elaborare.", "orange")
            return

        # Video non pronti: non bloccano gli altri, ma prima di partire lo si dice
        non_pronti = self._non_pronti()
        pronti = len(self.state["queue_files"]) - len(non_pronti)
        if pronti == 0:
            self._on_log("⚠️ Nessun video pronto: mancano txt o date.", "orange")
            return
        if non_pronti and conferma:
            uno = len(non_pronti) == 1
            elenco = "\n".join(f"  · {v[:70]} — {m}" for v, m in non_pronti[:8])
            if len(non_pronti) > 8:
                elenco += f"\n  · ... e altri {len(non_pronti) - 8}"
            box = QMessageBox(self)
            box.setWindowTitle("Video non pronti")
            box.setIcon(QMessageBox.Icon.Question)
            box.setText(f"{'1 video non è pronto e verrà saltato' if uno else f'{len(non_pronti)} video non sono pronti e verranno saltati'}:"
                        f"\n\n{elenco}\n\n"
                        f"{'Resta' if uno else 'Restano'} in coda: se nel frattempo "
                        f"{'lo sistemi' if uno else 'li sistemi'}, "
                        f"{'viene elaborato' if uno else 'vengono elaborati'} quando arriva il "
                        f"{'suo' if uno else 'loro'} turno.\n\n"
                        f"Avviare {'il video pronto' if pronti == 1 else f'i {pronti} video pronti'}?")
            btn_si = box.addButton("Avvia", QMessageBox.ButtonRole.YesRole)
            box.addButton("Annulla", QMessageBox.ButtonRole.NoRole)
            box.setDefaultButton(btn_si)
            box.exec()
            if box.clickedButton() != btn_si:
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
        self.state["use_master"] = bool(self._s.get("use_master", False))
        self.state["tempi_video"] = []
        self.state["saltati"] = []
        # Il motore aspetta qualche secondo i video la cui data è ancora in verifica online
        self.state["date_in_verifica"] = self._date_in_verifica
        self.state["txt_in_ricerca"] = self._txt_in_ricerca
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
            self._applica_data_youtube(vid, dlg.data_trovata)
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

        dlg = TxtEditorDialog(f"Editor — {base}.txt", contenuto, self, vid_name=vid_name)
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
        self._applica_data_youtube(vid_name, dlg.data_trovata)
        self.render_queue()

    # ══════════════════════════════════════════════════════════════════════
    # TXT MANCANTI DA YOUTUBE
    # ══════════════════════════════════════════════════════════════════════

    def _applica_data_youtube(self, vid: str, data: str | None):
        """
        Usa la data del titolo YouTube solo dove la pillola non è già verde: mai sopra una
        data inserita a mano né sopra una data riconosciuta dal nome del file (se quest'ultima
        è diversa, lo segnala nel log).
        """
        if not data:
            return
        base = os.path.splitext(vid)[0]
        for i, (v, t, manuale) in enumerate(self.state["queue_files"]):
            if v != vid:
                continue
            if manuale and manuale.strip() not in ("", "--"):
                return
            data_file, _, colore = extract_date_info(v)
            if colore == "green":
                if data_file != data:
                    self._on_log(f"⚠️ {base}: la data nel nome ({data_file}) è diversa da quella "
                                 f"del titolo YouTube ({data}), controlla.", "orange")
                return
            self.state["queue_files"][i] = (v, t, data)
            self._date_youtube[v] = data
            self._on_log(f"📅 {base}: data dal titolo YouTube {data}.", "green")
            return

    def _txt_presente(self, vid_name: str, cartella: str | None = None) -> bool:
        cartella = self.state.get("current_dir", "") if cartella is None else cartella
        path = os.path.join(cartella, os.path.splitext(vid_name)[0] + ".txt")
        return os.path.exists(path) and os.path.getsize(path) > 0

    def _on_cerca_txt_mancanti(self):
        mancanti = [item[0] for item in self.state["queue_files"] if not self._txt_presente(item[0])]
        if not mancanti:
            self._on_log("ℹ️ Nessun txt mancante nella coda.", "cyan")
            return
        if not strumento_presente("yt-dlp"):
            self._proponi_ytdlp(dopo=self._on_cerca_txt_mancanti)
            return
        self._on_log(f"🔎 Ricerca su YouTube dei txt mancanti: {len(mancanti)} video...", "cyan")
        self._btn_cerca_txt.setEnabled(False)
        self._btn_cerca_txt.setText(f" Ricerca 0/{len(mancanti)}...")
        # La cartella si fissa ora: i txt vanno accanto a questi video anche se nel frattempo
        # ne viene caricata un'altra
        self._cerca_txt_stato = {"totale": len(mancanti), "fatti": 0, "trovati": 0,
                                 "cartella": self.state["current_dir"]}

        self._avvia_ricerca_youtube(mancanti, self._on_txt_trovato, self._on_cerca_txt_finita)

    def _avvia_ricerca_youtube(self, video: list, on_uno, on_fine=None, solo_data=False):
        """Ricerca su YouTube in un thread a parte, un video alla volta. Ritorna (thread, worker)."""
        thread, worker = QThread(), TxtSearchWorker(video, solo_data)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.sig_uno.connect(on_uno)
        worker.sig_fine.connect(thread.quit)
        if on_fine:
            worker.sig_fine.connect(on_fine)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        self._ricerche_txt.append((thread, worker))
        thread.finished.connect(lambda: self._ricerche_txt.remove((thread, worker)))
        thread.start()
        return thread, worker

    def _verifica_date_online(self):
        """
        Controllo di sicurezza: le date non certe del nome (ricostruite da "1331983", solo
        l'anno, ...) si confrontano col titolo YouTube. Se il video si trova, vale la data
        del titolo e la pillola diventa verde; se no resta arancione, da confermare a mano.
        Ogni video si controlla una volta per sessione; le date inserite a mano non si toccano.
        Con la stessa ricerca i video entrati in coda senza txt ricevono anche il txt, dalla
        descrizione del video.
        """
        if not strumento_presente("yt-dlp"):
            return   # si rifà appena yt-dlp viene scaricato
        da_fare, senza_txt = [], []
        for vid, _, manuale in self.state.get("queue_files", []):
            if vid in self._date_verificate:
                continue
            data_incerta = (not (manuale and manuale.strip() not in ("", "--"))
                            and extract_date_info(vid)[2] != "green")
            manca_txt = not self._txt_presente(vid)
            if not data_incerta and not manca_txt:
                continue
            self._date_verificate.add(vid)
            if data_incerta:
                self._date_in_verifica.add(vid)
            if manca_txt:
                self._txt_in_ricerca.add(vid)
                senza_txt.append(vid)
            else:
                da_fare.append(vid)
        if senza_txt:
            self._on_log(f"🔎 Ricerca automatica del txt su YouTube: {len(senza_txt)} video...", "cyan")
            for vid in senza_txt:   # i txt vanno accanto a questi video
                self._txt_auto_cartelle[vid] = self.state["current_dir"]
            # Gli esiti arrivano da un altro thread: vanno ricevuti da metodi della finestra
            # (non da funzioni locali), così Qt li esegue nel thread dell'interfaccia
            self._avvia_ricerca_youtube(senza_txt, self._on_txt_auto, self._on_txt_auto_fine)
            if not da_fare:
                self.render_queue()   # mostra subito la clessidra
        if da_fare:
            self._on_log(f"📅 Verifica online della data: {len(da_fare)} video...", "cyan")
            self._avvia_ricerca_youtube(da_fare, self._on_data_verificata, solo_data=True)
            self.render_queue()   # mostra subito la clessidra

    @Slot(str, dict)
    def _on_txt_auto(self, vid: str, r: dict):
        """Esito della ricerca automatica del txt per un video entrato in coda senza."""
        cartella = self._txt_auto_cartelle.pop(vid, None)
        if cartella is None:
            return
        self._txt_in_ricerca.discard(vid)
        detto = vid in self._date_in_verifica and not r.get("data")
        if vid in self._date_in_verifica:
            self._on_data_verificata(vid, r)
        if not (detto and r["esito"] != "ok"):   # il motivo è già nel log della data
            self._salva_txt_trovato(vid, r, cartella)
        self.render_queue()

    @Slot()
    def _on_txt_auto_fine(self):
        """Ricerca automatica finita (o interrotta da un errore): niente clessidre rimaste accese."""
        cercati = getattr(self.sender(), "video", None)
        rimasti = [v for v in (cercati if cercati is not None else list(self._txt_auto_cartelle))
                   if v in self._txt_auto_cartelle]
        if not rimasti:
            return
        for vid in rimasti:
            self._txt_auto_cartelle.pop(vid, None)
        self._txt_in_ricerca.difference_update(rimasti)
        self._date_in_verifica.difference_update(rimasti)
        self.render_queue()

    @Slot(str, dict)
    def _on_data_verificata(self, vid: str, r: dict):
        base = os.path.splitext(vid)[0]
        data = r.get("data")
        self._date_in_verifica.discard(vid)
        if not data:
            motivo = (r["messaggio"] if r["esito"] != "ok"
                      else "il titolo YouTube non ha una data certa (solo l'anno, o una data recente)")
            self._date_esiti[vid] = motivo
            self._on_log(f"⚠️ {base}: data non confermata online ({motivo}), controllala a mano.",
                         "orange")
            self.render_queue()
            return
        self._date_esiti.pop(vid, None)
        stimata = extract_date_info(vid)[0]
        if stimata and not stimata.startswith("01-01-") and stimata != data:
            self._on_log(f"⚠️ {base}: dal nome sembrava {stimata}, ma il titolo YouTube dice {data}.",
                         "orange")
        self._applica_data_youtube(vid, data)
        self.render_queue()

    @Slot(str, dict)
    def _on_txt_trovato(self, vid: str, r: dict):
        st = self._cerca_txt_stato
        st["fatti"] += 1
        self._btn_cerca_txt.setText(f" Ricerca {st['fatti']}/{st['totale']}...")
        if self._salva_txt_trovato(vid, r, st["cartella"]):
            st["trovati"] += 1

    def _salva_txt_trovato(self, vid: str, r: dict, cartella: str) -> bool:
        """Esito di una ricerca su YouTube: scrive il txt accanto al video. True se l'ha scritto."""
        base = os.path.splitext(vid)[0]
        if r["esito"] != "ok":
            self._on_log(f"⚠️ {base}: {r['messaggio']}.", "orange")
            if r.get("data") and self.state["current_dir"] == cartella:
                self._applica_data_youtube(vid, r["data"])   # trovato, ma senza timestamp
                self.render_queue()
            return False
        # Mai sovrascrivere un txt comparso nel frattempo (es. scritto a mano nell'editor)
        if self._txt_presente(vid, cartella):
            self._on_log(f"ℹ️ {base}: txt già presente, non modificato.", "cyan")
            return False
        path = os.path.join(cartella, f"{base}.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(r["txt"])
        self._on_log(f"✅ {base}: {r['messaggio']}.", "green")
        if self.state["current_dir"] == cartella:
            for i, item in enumerate(self.state["queue_files"]):
                if item[0] == vid:
                    self.state["queue_files"][i] = (item[0], f"{base}.txt", item[2])
            self._applica_data_youtube(vid, r.get("data"))
            self.render_queue()
        return True

    @Slot()
    def _on_cerca_txt_finita(self):
        st = self._cerca_txt_stato
        self._btn_cerca_txt.setEnabled(True)
        self._btn_cerca_txt.setText(" Cerca txt mancanti")
        self._on_log(f"🔎 Ricerca txt finita: {st['trovati']} trovati su {st['totale']}.",
                     "green" if st["trovati"] == st["totale"] else "orange")
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
                      vals.get("auto_start_after_yt", False),
                      vals.get("use_master", False))
        self._s = load_settings()
        self._on_log("✅ Impostazioni salvate.", "cyan")
        self._update_duration_label()   # la stima del lavoro dipende dall'opzione master

    # ══════════════════════════════════════════════════════════════════════
    # YOUTUBE DOWNLOAD
    # ══════════════════════════════════════════════════════════════════════

    def _on_yt_download(self):
        url = self._yt_entry.text().strip()
        if not url:
            return
            
        if not strumento_presente("yt-dlp"):
            self._proponi_ytdlp(dopo=self._on_yt_download)
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
            self._btn_yt.setText("Importa da YouTube")
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
                self._yt_playlist = True
                self._on_log("🔗 Scelta: Intera playlist.", "cyan")
            else:
                # Annullato: ripristina entrambi i bottoni
                self._btn_yt.setEnabled(True)
                if hasattr(self, "_btn_dl"): self._btn_dl.setEnabled(True)
                self._btn_yt.setText("Importa da YouTube")
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
                self._btn_yt.setText("Importa da YouTube")
                self._on_progress(0, "Download annullato.")
                self._is_direct_download = False
                return
            self._yt_playlist = True

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
        playlist = self._yt_playlist
        self._yt_playlist = False
        self._yt_playlist_attiva = playlist
        self._yt_playlist_aggiunti = 0
        self._yt_worker = YTWorker(url, output_dir, self.state, direct_download=is_direct,
                                   playlist=playlist)
        self._yt_thread = QThread()
        self._yt_worker.moveToThread(self._yt_thread)

        # ─── FIX BUG 3: RELAY THREAD-SAFE ────────────────────────────────────
        # Invece di connettere il segnale del worker direttamente al segnale della UI,
        # lo connettiamo alla funzione .emit del segnale della UI.
        self._yt_worker.sig_log.connect(self._sig_log.emit)
        self._yt_worker.sig_progress.connect(self._sig_progress.emit)
        self._yt_worker.sig_finished.connect(self._sig_yt_finished.emit)
        self._yt_worker.sig_video.connect(self._sig_yt_video.emit)
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

        if strumento_presente("yt-dlp"):
            threading.Thread(target=self._update_ytdlp, daemon=True).start()
        elif self.settings_storage.value("ytdlp_rifiutato", False, type=bool):
            # Già detto di no una volta: all'avvio non si richiede più, solo quando serve
            self._on_log("⚠️ yt-dlp non trovato: download da YouTube, ricerca dei txt e verifica "
                         "delle date non funzionano. Il programma lo propone quando serve.", "orange")
        else:
            self._proponi_ytdlp()

    def _proponi_ytdlp(self, dopo=None) -> None:
        """yt-dlp manca: si propone di scaricarlo. dopo() viene chiamata a scaricamento riuscito."""
        if self._ytdlp_in_scarico:
            self._on_log("⏳ Scaricamento di yt-dlp già in corso...", "orange")
            return
        box = QMessageBox(self)
        box.setWindowTitle("yt-dlp mancante")
        box.setIcon(QMessageBox.Icon.Question)
        box.setText("yt-dlp non è installato.\n\n"
                    "Serve per scaricare i video da YouTube, cercare i txt mancanti e verificare "
                    "le date.\n\n"
                    "Spot Cutter può scaricarlo adesso dalla pagina ufficiale di yt-dlp "
                    "(circa 18 MB, una volta sola) e metterlo nella cartella bin.\n\n"
                    "Scaricarlo?")
        btn_si = box.addButton("Scarica", QMessageBox.ButtonRole.YesRole)
        box.addButton("Non ora", QMessageBox.ButtonRole.NoRole)
        box.setDefaultButton(btn_si)
        box.exec()
        if box.clickedButton() is not btn_si:
            self.settings_storage.setValue("ytdlp_rifiutato", True)
            self._on_log("⚠️ yt-dlp non scaricato: le funzioni di YouTube restano spente. "
                         "Il programma lo ripropone quando serve.", "orange")
            return
        self.settings_storage.setValue("ytdlp_rifiutato", False)
        self._ytdlp_in_scarico, self._ytdlp_dopo = True, dopo
        self._on_log("⬇️ Scaricamento di yt-dlp dalla pagina ufficiale...", "cyan")

        def lavoro():
            try:
                scarica_ytdlp(lambda f: self._sig_progress.emit(f, f"Scaricamento yt-dlp... {int(f * 100)}%"))
                self._sig_ytdlp_scaricato.emit("")
            except Exception as e:
                self._sig_ytdlp_scaricato.emit(str(e) or type(e).__name__)
        threading.Thread(target=lavoro, daemon=True).start()

    @Slot(str)
    def _on_ytdlp_scaricato(self, errore: str):
        self._ytdlp_in_scarico = False
        dopo, self._ytdlp_dopo = self._ytdlp_dopo, None
        if errore:
            self._on_progress(0, "Pronto")
            self._on_log(f"❌ Scaricamento di yt-dlp non riuscito: {errore}", "red")
            QMessageBox.warning(self, "yt-dlp non scaricato",
                                f"Non sono riuscito a scaricare yt-dlp:\n{errore}\n\n"
                                "Controlla la connessione e riprova, oppure scaricalo a mano da\n"
                                "https://github.com/yt-dlp/yt-dlp/releases\n"
                                "e metti yt-dlp.exe nella cartella bin del programma.")
            return
        self._on_progress(1.0, "yt-dlp scaricato")
        self._on_log("✅ yt-dlp scaricato nella cartella bin: le funzioni di YouTube sono attive.", "green")
        self._verifica_date_online()
        if dopo:
            dopo()

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
        
        # 1. Il messaggio dice cosa si interrompe davvero (niente, se il programma è fermo)
        def attivo(nome):
            th = getattr(self, nome, None)
            try:
                return bool(th) and th.isRunning()
            except RuntimeError:   # thread già distrutto da Qt
                return False

        in_corso = []
        if self.state.get("running") or attivo("_worker_thread"):
            in_corso.append("il taglio dei video: alla riapertura potrai riprendere, i video già "
                            "finiti vengono saltati e quello a metà viene rifatto senza doppioni")
        if attivo("_yt_thread"):
            in_corso.append("un download da YouTube: rimettendo lo stesso link riparte da dove "
                            "era arrivato")
        if self._ricerche_txt:
            in_corso.append("una ricerca su YouTube (txt o date): non si perde niente")

        msg_box = QMessageBox(self)
        msg_box.setWindowTitle('Esci')
        if in_corso:
            msg_box.setIcon(QMessageBox.Icon.Warning)
            msg_box.setText("Se esci, si interrompe:\n\n" + "\n\n".join(f"• {x}." for x in in_corso))
            si_button = msg_box.addButton("Esci", QMessageBox.ButtonRole.YesRole)
            no_button = msg_box.addButton("Resta", QMessageBox.ButtonRole.NoRole)
        else:
            msg_box.setIcon(QMessageBox.Icon.Question)
            testo = "Vuoi chiudere Spot Cutter?"
            if self.state.get("queue_files"):
                testo += "\n\nLa coda è salvata: te la riproporrò alla prossima apertura."
            msg_box.setText(testo)
            si_button = msg_box.addButton("Esci", QMessageBox.ButtonRole.YesRole)
            no_button = msg_box.addButton("Annulla", QMessageBox.ButtonRole.NoRole)
        # Con un lavoro in corso Invio non deve interromperlo; da fermo non c'è niente da perdere
        msg_box.setDefaultButton(no_button if in_corso else si_button)

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
