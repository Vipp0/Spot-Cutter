"""
post_build.py — Crea la struttura della cartella bin dopo la compilazione
Eseguire dopo pyinstaller: python post_build.py
"""
import os
import shutil

DIST_DIR = os.path.join("dist", "SpotCutter")
BIN_DIR  = os.path.join(DIST_DIR, "bin")

# Crea cartella bin
os.makedirs(BIN_DIR, exist_ok=True)
print(f"✅ Cartella bin creata in {BIN_DIR}")

# Crea file README dentro bin
readme = """SPOT CUTTER — bin folder
================================
IT: Inserire in questa cartella i seguenti eseguibili:
EN: Place the following executables in this folder:

  ffmpeg.exe   — https://ffmpeg.org/download.html
  ffprobe.exe  — https://ffmpeg.org/download.html (included with ffmpeg)
  yt-dlp.exe   — https://github.com/yt-dlp/yt-dlp/releases

IT: Il programma cerca automaticamente gli eseguibili prima
    in questa cartella bin/, poi nella cartella principale,
    poi nel PATH di sistema.

EN: The program automatically searches for executables first
    in this bin/ folder, then in the main folder,
    then in the system PATH.
"""
with open(os.path.join(BIN_DIR, "README.txt"), "w", encoding="utf-8") as f:
    f.write(readme)
print("✅ File README.txt creato")

# Copia automatica exe se presenti nella cartella del progetto
EXE_LIST = ["ffmpeg.exe", "ffprobe.exe", "yt-dlp.exe"]
found_any = False
for exe in EXE_LIST:
    # Cerca prima nella cartella corrente, poi in bin/ del progetto
    for search_path in [exe, os.path.join("bin", exe)]:
        if os.path.isfile(search_path):
            dest = os.path.join(BIN_DIR, exe)
            shutil.copy2(search_path, dest)
            print(f"✅ Copiato: {exe} → bin/")
            found_any = True
            break
    else:
        print(f"⚠️  {exe} non trovato — scaricalo e mettilo in dist/SpotCutter/bin/")

print()
if found_any:
    print("🎉 Build completata! Controlla dist/SpotCutter/")
else:
    print("🎉 Build completata! Aggiungi gli exe in dist/SpotCutter/bin/")