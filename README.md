# 🎬 Spot Cutter

> 🇮🇹 Estrae automaticamente spot pubblicitari, promo e bumper da registrazioni TV digitalizzate, organizzandoli in una libreria personale per l'uso con piattaforme IPTV come DizqueTV e Tunarr. Sviluppato con l'assistenza dell'IA.

> 🇬🇧 Automatically extracts TV commercials, promos and bumpers from digitized recordings, organizing them into a personal ad library for use with IPTV platforms like DizqueTV and Tunarr. Developed with AI assistance.

![Version](https://img.shields.io/badge/version-1.0-blue)
![Python](https://img.shields.io/badge/python-3.11+-green)
![License](https://img.shields.io/badge/license-MIT-orange)
![Platform](https://img.shields.io/badge/platform-Windows-lightgrey)

---

## 📌 Cos'è / What is it

🇮🇹 Spot Cutter è un'applicazione desktop per Windows che permette di estrarre automaticamente spot pubblicitari, promo, bumper e sigle da video di registrazioni televisive o cassette digitalizzate. Il programma analizza i fotogrammi neri tra i contenuti per individuare i punti di stacco e, guidato da un semplice file di testo con i timestamp, taglia e organizza automaticamente i clip nella tua libreria.

🇬🇧 Spot Cutter is a Windows desktop application that automatically extracts TV commercials, promos, bumpers and jingles from television recordings or digitized tapes. The program analyzes black frames between content to identify cut points and, guided by a simple text file with timestamps, automatically cuts and organizes clips into your library.

---

## ✨ Funzionalità / Features

🇮🇹
- **Taglio automatico** — rileva i fotogrammi neri e taglia con precisione al frame
- **File di testo guidato** — indica gli spot con semplici timestamp, il programma fa il resto
- **Importazione da YouTube** — scarica video direttamente nell'app e aggiungili alla coda
- **Editor tagli manuali** — correggi o crea manualmente i timestamp con l'assistenza del rilevamento automatico
- **Categorizzazione automatica** — ogni clip viene salvato nella categoria giusta (Spot, Promo, Bumper, Sigle, TG, Natale...)
- **Libreria organizzata** — i file vengono salvati automaticamente per anno e categoria
- **Storico elaborazioni** — tieni traccia di tutto quello che hai già elaborato
- **Tagli paralleli** — sfrutta i core del processore per velocizzare l'elaborazione

🇬🇧
- **Automatic cutting** — detects black frames and cuts with frame-level precision
- **Text file guided** — mark spots with simple timestamps, the program does the rest
- **YouTube import** — download videos directly into the app and add them to the queue
- **Manual cut editor** — manually correct or create timestamps with automatic detection assistance
- **Auto categorization** — each clip is saved in the right category (Spot, Promo, Bumper, Jingles, News, Christmas...)
- **Organized library** — files are automatically saved by year and category
- **Processing history** — keep track of everything you have already processed
- **Parallel cutting** — uses processor cores to speed up processing

---

## 🖥️ Requisiti / Requirements

- Windows 10 / 11
- [ffmpeg](https://ffmpeg.org/download.html) — per il taglio video / for video cutting
- [yt-dlp](https://github.com/yt-dlp/yt-dlp/releases) — per il download da YouTube / for YouTube downloads

---

## 🚀 Installazione / Installation

### Versione compilata / Compiled version (EXE)
1. 🇮🇹 Scarica l'ultima release dalla pagina [Releases](https://github.com/Vipp0/Spot-Cutter/releases) / 🇬🇧 Download the latest release from [Releases](https://github.com/Vipp0/Spot-Cutter/releases)
2. Estrai la cartella `SpotCutter` / Extract the `SpotCutter` folder
3. Metti `ffmpeg.exe`, `ffprobe.exe` e `yt-dlp.exe` nella cartella `bin/` / Place `ffmpeg.exe`, `ffprobe.exe` and `yt-dlp.exe` in the `bin/` folder
4. Avvia `SpotCutter.exe` / Launch `SpotCutter.exe`

### Da sorgente / From source
```bash
pip install PySide6
python main.py
```

---

## 📁 Struttura della libreria / Library structure

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

## ⚠️ Disclaimer

This software is intended for personal archival use only. Users are responsible for ensuring their use complies with applicable laws and the terms of service of any platforms accessed. The author does not condone copyright infringement.

---

## 📄 Licenza / License

Distribuito sotto licenza MIT / Distributed under MIT License. Vedi / See [LICENSE](LICENSE) for details.

---

## 🙏 Crediti / Credits

- [FFmpeg](https://ffmpeg.org/) — elaborazione video / video processing
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) — download YouTube
- [PySide6](https://doc.qt.io/qtforpython/) — interfaccia grafica / GUI framework
