# Changelog

Modifiche successive alla release 1.2. Le versioni 1.3, 1.3.1 e 1.3.2 sono uscite insieme nella release 1.3.2; la 1.3.3 insieme alla 1.3.4.
Changes after release 1.2. Versions 1.3, 1.3.1 and 1.3.2 were released together as 1.3.2; version 1.3.3 together with 1.3.4.

---

## 🎬 Spot Cutter 1.3.6

### ✨ Nuove funzionalità / New features

- 🇮🇹 **Ripresa dopo uno Stop** — premendo di nuovo Avvia i video già elaborati vengono saltati, e dopo uno Stop escono dalla coda come a fine elaborazione
- 🇬🇧 **Resume after a Stop** — pressing Start again skips videos already processed, and after a Stop they leave the queue as they do when processing ends

- 🇮🇹 **Nessun doppione per il video interrotto a metà** — il programma ricorda i clip già creati (anche se chiudi il programma o va via la corrente) e alla ripresa li rimuove prima di rifare il video, con gli stessi nomi
- 🇬🇧 **No duplicates for a video stopped halfway** — the program remembers the clips already created (even if the program is closed or the power goes off) and on resume removes them before redoing the video, with the same names

- 🇮🇹 **Playlist intere** — una playlist (o un video di una playlist, scegliendo "Intera playlist") viene scaricata un video alla volta, ognuno con il suo txt e la sua data, ed entra in coda appena pronto; la barra mostra "Playlist 12/100"
- 🇬🇧 **Whole playlists** — a playlist (or a video of a playlist, choosing "Whole playlist") is downloaded one video at a time, each with its txt and date, and joins the queue as soon as it is ready; the bar shows "Playlist 12/100"

- 🇮🇹 **Playlist interrotta? Si riprende** — dopo uno Stop basta rimettere lo stesso link: i video già scaricati vengono saltati e quello interrotto riparte da dove era arrivato
- 🇬🇧 **Playlist stopped? Just resume** — after a Stop, paste the same link again: videos already downloaded are skipped and the interrupted one continues where it left off

- 🇮🇹 **Coda salvata in automatico** — la coda viene salvata a ogni cambiamento; alla riapertura il programma chiede se riprendere quella dell'ultima volta (vale anche dopo aver installato una versione nuova)
- 🇬🇧 **Queue saved automatically** — the queue is saved on every change; on reopening the program asks whether to resume the last one (also after installing a new version)

---

## 🎬 Spot Cutter 1.3.5

### ✨ Nuove funzionalità / New features

- 🇮🇹 **Cerca su YouTube** — nell'editor del txt (clic sulla pillola "NO TXT") un pulsante cerca su YouTube il video con lo stesso titolo e riempie l'editor con i timestamp della descrizione, da controllare e salvare
- 🇬🇧 **Search on YouTube** — in the txt editor (click the "NO TXT" pill) a button searches YouTube for the video with the same title and fills the editor with the timestamps from its description, ready to check and save

- 🇮🇹 **Cerca txt mancanti** — un pulsante nella barra della coda recupera in un colpo i txt di tutti i video che non ce l'hanno; i txt già presenti non vengono mai toccati
- 🇬🇧 **Search missing txt** — a button in the queue toolbar fetches the txt for every video that has none in one go; existing txt files are never touched

- 🇮🇹 Riconosce anche i nomi scaricati con altri programmi, con la data senza barre e il titolo troncato ("2541985 RaiDue ... TG2 Staser" → "25/4/1985 - RaiDue - ... TG2 Stasera", "341985 RaiTre ... e prom" → "3/4/1985 - RaiTre - ... e promo"); le date ambigue ("1111985") vengono provate in entrambe le letture. Se non trova un titolo compatibile, se ne trova più di uno o se il video non ha timestamp lo dice, senza mai scegliere a caso
- 🇬🇧 Also recognises names downloaded with other programs, with the date without slashes and a truncated title ("2541985 RaiDue ... TG2 Staser" → "25/4/1985 - RaiDue - ... TG2 Stasera", "341985 RaiTre ... e prom" → "3/4/1985 - RaiTre - ... e promo"); ambiguous dates ("1111985") are tried with both readings. If no matching title is found, more than one matches, or the video has no timestamps, it says so, never picking at random

- 🇮🇹 **Data dal titolo** — quando il video viene trovato, anche la data viene presa dal titolo YouTube ("2541985" → 25-04-1985) e la pillola diventa tutta verde; viene inserita solo se la data manca o è incerta, mai sopra una data inserita a mano o già riconosciuta dal nome (se è diversa compare un avviso nel log)
- 🇬🇧 **Date from the title** — when the video is found, the date is also taken from the YouTube title ("2541985" → 25-04-1985) and the pill turns fully green; it is filled in only when the date is missing or uncertain, never over a date entered by hand or already recognised from the name (if they differ, a warning appears in the log)

---

## 🎬 Spot Cutter 1.3.4

### 🐛 Bug fix

- 🇮🇹 Canale ripetuto nel nome dei clip ("Promo X - Retequattro - Rete 4"): il canale già presente in coda al nome viene riconosciuto in ogni forma e scritto una volta sola nella forma standard ("Promo X - Rete 4")
- 🇬🇧 Channel repeated in clip names ("Promo X - Retequattro - Rete 4"): the channel already present at the end of the name is recognised in any form and written once in the standard form ("Promo X - Rete 4")

- 🇮🇹 Nomi troncati all'ultimo punto: "Brainmost - G.W. Electronics - Milano" diventava "Brainmost - G.W", "166 1.2.3.4.5.6" perdeva il ".6". Ora il nome resta completo
- 🇬🇧 Names cut at the last dot: "Brainmost - G.W. Electronics - Milano" became "Brainmost - G.W", "166 1.2.3.4.5.6" lost the ".6". The full name is now kept

- 🇮🇹 La "/" nei nomi diventa un trattino ("Promo/teaser" → "Promo-teaser") invece di attaccare le parole ("Promoteaser")
- 🇬🇧 A "/" in names becomes a hyphen ("Promo/teaser" → "Promo-teaser") instead of joining the words ("Promoteaser")

- 🇮🇹 Il canale di Tele+ si scrive "Tele+": "Sky/Tele+" avrebbe creato una sottocartella al posto del nome del file
- 🇬🇧 The Tele+ channel is written "Tele+": "Sky/Tele+" would have created a subfolder instead of the file name

---

## 🎬 Spot Cutter 1.3.3

### 🐛 Bug fix

- 🇮🇹 Con un nero di soli 3 fotogrammi il clip precedente finiva con il primo fotogramma dello spot successivo: ora la fine del clip resta sempre dentro il nero
- 🇬🇧 With a black only 3 frames long, the previous clip ended with the first frame of the next spot: the clip end now always stays inside the black

---

## 🎬 Spot Cutter 1.3.2

### ✨ Miglioramenti del motore / Engine improvements

- 🇮🇹 **Neri VHS rovinati** — sui nastri rovinati il nero "schiarisce" verso il grigio o viene spezzato da righe di traking: ora il clip parte dalla fine vera del nero e non più con fino a 1 secondo di nero sporco all'inizio
- 🇬🇧 **Damaged VHS blacks** — on worn tapes the black fades towards grey or is broken by tracking lines: clips now start at the real end of the black instead of with up to 1 second of dirty black

- 🇮🇹 **Sfondi colorati scuri protetti** — un fondo blu o verde scuro all'inizio di uno spot non viene più scambiato per nero (controllo della saturazione): nessun fotogramma dello spot viene tagliato via
- 🇬🇧 **Dark coloured backgrounds protected** — a dark blue or green background at the start of a spot is no longer mistaken for black (saturation check): no spot frames are cut off

- 🇮🇹 **Stacchi netti su sfondo scuro** — quando uno spot comincia direttamente con uno sfondo scuro colorato, senza nero, il taglio cade esattamente sul primo fotogramma e lo stacco viene segnalato "da verificare"
- 🇬🇧 **Hard cuts on dark backgrounds** — when a spot starts directly on a dark coloured background with no black, the cut lands exactly on its first frame and is flagged "to be checked"

- 🇮🇹 Il log indica quando la fine di un nero è stata corretta ("fine corretta da ...")
- 🇬🇧 The log shows when the end of a black has been corrected ("fine corretta da ...")

- 🇮🇹 Sui neri netti non cambia nulla (al massimo 1 fotogramma di nero in meno); la ricerca neri richiede circa 12 secondi in più ogni 20 minuti di video
- 🇬🇧 Nothing changes on clean blacks (at most 1 black frame less); black detection takes about 12 extra seconds per 20 minutes of video

---

## 🎬 Spot Cutter 1.3.1

### ⚡ Prestazioni e qualità / Performance and quality

- 🇮🇹 **Taglio diretto dall'originale** — il master intermedio non serve più: stessa precisione al fotogramma, una ricodifica in meno, qualità più alta (VMAF da +0,9 a +1,6), file dal 4% all'8% più leggeri, elaborazione circa un terzo più veloce e nessun file temporaneo
- 🇬🇧 **Direct cutting from the original** — the intermediate master is no longer needed: same frame accuracy, one less re-encode, higher quality (VMAF +0.9 to +1.6), files 4–8% smaller, processing about a third faster and no temporary file

- 🇮🇹 **Coda continua per i tagli paralleli** — appena un taglio finisce ne parte un altro, con i clip più lunghi per primi: nessun core resta fermo ad aspettare
- 🇬🇧 **Continuous queue for parallel cuts** — as soon as a cut ends another one starts, longest clips first: no core sits idle waiting

- 🇮🇹 Tempo stimato (ETA) calcolato sui secondi di video già tagliati
- 🇬🇧 Estimated time (ETA) based on the seconds of video already cut

### ✨ Nuove funzionalità / New features

- 🇮🇹 **Opzione "Usa il master (metodo classico)"** nelle impostazioni, spenta di default, per tornare al metodo della 1.3
- 🇬🇧 **"Use the master (classic method)" option** in settings, off by default, to go back to the 1.3 method

### 🐛 Bug fix

- 🇮🇹 Dopo uno Stop (o un errore di FFmpeg) non restano più clip tagliati a metà nella libreria
- 🇬🇧 After a Stop (or an FFmpeg error) no half-cut clips are left in the library

---

## 🎬 Spot Cutter 1.3

### ✨ Nuovo motore di taglio / New cutting engine

- 🇮🇹 **Nero dinamico per ogni stacco** — il nero viene cercato a tre sensibilità nello stesso passaggio (0.1, 0.15, 0.20): i neri "grigi" delle registrazioni VHS vengono trovati stacco per stacco
- 🇬🇧 **Dynamic black for each cut** — blacks are searched at three sensitivities in a single pass (0.1, 0.15, 0.20): the "grey" blacks of VHS recordings are found cut by cut

- 🇮🇹 **Taratura dei timestamp per video** — il programma misura di quanto i timestamp del txt anticipano i neri e ne tiene conto
- 🇬🇧 **Per-video timestamp calibration** — the program measures how early the txt timestamps are compared to the blacks and compensates

- 🇮🇹 **Scelta dei neri in ordine** — ogni nero viene usato per un solo stacco: gestiti bumper brevi, neri lunghi, neri spezzati da disturbi e timestamp ripetuti
- 🇬🇧 **Ordered black assignment** — each black is used for one cut only: short bumpers, long blacks, blacks broken by noise and repeated timestamps are handled

- 🇮🇹 **Stacchi netti senza nero** — riconosciuti dal cambio di scena, tagliati senza fotogrammi dello spot vicino e segnalati "da verificare" nel log e nella card
- 🇬🇧 **Hard cuts with no black** — detected from the scene change, cut with no frames from the adjacent spot and flagged "to be checked" in the log and the card

- 🇮🇹 Rilevamento del silenzio rimosso: spostava il taglio dentro gli spot (causa dei "decimi dello spot precedente")
- 🇬🇧 Silence detection removed: it moved the cut inside the spots (cause of the "tenths of the previous spot")

- 🇮🇹 Il log mostra per ogni stacco il nero scelto e la sensibilità usata
- 🇬🇧 The log shows the chosen black and the sensitivity used for each cut

### ⚡ Prestazioni / Performance

- 🇮🇹 **Taglio circa 4 volte più veloce** per ogni clip (seek ibrido), con risultato identico al fotogramma
- 🇬🇧 **About 4× faster cutting** per clip (hybrid seek), with frame-identical output

### 🐛 Bug fix

- 🇮🇹 File txt mancante o vuoto non riconosciuto correttamente nella coda
- 🇬🇧 Missing or empty txt file not correctly detected in the queue

- 🇮🇹 Spot con lo stesso nome (es. bumper ripetuti) potevano ancora sovrascriversi durante i tagli paralleli
- 🇬🇧 Spots with the same name (e.g. repeated bumpers) could still overwrite each other during parallel cuts

- 🇮🇹 Timestamp a una cifra nel txt (es. 0:27, 1:05:20) ora accettati
- 🇬🇧 Single-digit timestamps in the txt (e.g. 0:27, 1:05:20) are now accepted

- 🇮🇹 Stop durante il download da YouTube ora chiude davvero yt-dlp
- 🇬🇧 Stop during a YouTube download now really closes yt-dlp

---

> ⚠️ **Windows only.** Mac/Linux compatibility not tested.
>
> ℹ️ This software is intended for personal archival use only.
