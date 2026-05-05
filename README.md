# 🎬 Spot Cutter

> Taglia automaticamente spot pubblicitari, promo, bumper e sigle da registrazioni TV e videocassette digitalizzate.

![Version](https://img.shields.io/badge/version-1.0-blue)
![Python](https://img.shields.io/badge/python-3.11+-green)
![License](https://img.shields.io/badge/license-MIT-orange)
![Platform](https://img.shields.io/badge/platform-Windows-lightgrey)

---

## 📌 Cos'è

Spot Cutter è un'applicazione desktop per Windows che permette di estrarre automaticamente spot pubblicitari, promo, bumper e sigle da video di registrazioni televisive o cassette digitalizzate.

Il programma analizza i fotogrammi neri tra i contenuti per individuare i punti di stacco e, guidato da un semplice file di testo con i timestamp, taglia e organizza automaticamente i clip nella tua libreria.

---

## ✨ Funzionalità principali

- **Taglio automatico** — rileva i fotogrammi neri e taglia con precisione al frame
- **File di testo guidato** — indica gli spot con semplici timestamp, il programma fa il resto
- **Importazione da YouTube** — scarica video direttamente nell'app e aggiungili alla coda
- **Editor tagli manuali** — correggi o crea manualmente i timestamp con l'assistenza del rilevamento automatico
- **Categorizzazione automatica** — ogni clip viene salvato nella categoria giusta (Spot, Promo, Bumper, Sigle, TG, Natale...)
- **Libreria organizzata** — i file vengono salvati automaticamente per anno e categoria
- **Storico elaborazioni** — tieni traccia di tutto quello che hai già elaborato
- **Tagli paralleli** — sfrutta i core del processore per velocizzare l'elaborazione

---

## 🖥️ Requisiti

- Windows 10 / 11
- [ffmpeg](https://ffmpeg.org/download.html) — per il taglio video
- [yt-dlp](https://github.com/yt-dlp/yt-dlp/releases) — per il download da YouTube

---

## 🚀 Installazione

### Versione compilata (EXE)
1. Scarica l'ultima release dalla pagina [Releases](https://github.com/Vipp0/Spot-Cutter-Pro/releases)
2. Estrai la cartella `SpotCutter`
3. Metti `ffmpeg.exe`, `ffprobe.exe` e `yt-dlp.exe` nella cartella `bin/`
4. Avvia `SpotCutter.exe`

### Da sorgente
```bash
pip install PySide6
python main.py
```

---

## 📁 Struttura della libreria

I clip vengono salvati automaticamente in `Video\Libreria Spot` con questa struttura:

```
Libreria Spot/
├── 1981/
│   ├── Spot/
│   ├── Promo-Trailer/
│   ├── Bumper/
│   └── ...
├── 1990/
└── Download YT/
```

---

## 📄 Licenza

Distribuito sotto licenza MIT. Vedi [LICENSE](LICENSE) per i dettagli.

---

## 🙏 Crediti

- [FFmpeg](https://ffmpeg.org/) — elaborazione video
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) — download YouTube
- [PySide6](https://doc.qt.io/qtforpython/) — interfaccia grafica
