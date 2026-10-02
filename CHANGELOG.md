# Changelog

Modifiche successive alla release 1.2. Le versioni 1.3, 1.3.1 e 1.3.2 sono uscite insieme nella release 1.3.2; la 1.3.3 insieme alla 1.3.4; la 1.3.5 insieme alla 1.3.6.
Changes after release 1.2. Versions 1.3, 1.3.1 and 1.3.2 were released together as 1.3.2; version 1.3.3 together with 1.3.4; version 1.3.5 together with 1.3.6.

---

## 🎬 Spot Cutter 1.3.8

### 🐛 Correzioni / Fixes

- 🇮🇹 **Niente falso errore sui video in bianco e nero** — nei video senza colori (o con colori molto sbiaditi) il log mostrava in rosso "Ricerca neri terminata con errore", anche se l'analisi era completa e i tagli giusti. Ora l'avviso compare solo per gli errori veri
- 🇬🇧 **No false error on black-and-white videos** — in videos without colours (or with very faded colours) the log showed "Black search ended with an error" in red, even though the analysis was complete and the cuts correct. The warning now appears only for real errors

---

## 🎬 Spot Cutter 1.3.7

### ✨ Miglioramenti del motore / Engine improvements

- 🇮🇹 **Stacchi netti senza nero al punto giusto** — dove tra uno spot e l'altro non c'è il nero (es. Canale 5 del 1984, bumper di 2 secondi) il taglio si cercava un secondo troppo avanti e finiva sullo stacco successivo: lo spot precedente si prendeva il bumper e lo spot dopo perdeva i primi secondi ("Suona con Ricordi"). Ora il punto atteso di uno stacco netto parte da dove inizierebbe il nero e, tra i cambi di scena abbastanza netti, vince il più vicino invece del più forte (negli spot molto montati uno stacco interno può essere più netto di quello vero). Su 71 video di prova: 23 tagli migliorano, 2 punti già stimati si spostano di mezzo secondo, i tagli sul nero non cambiano
- 🇬🇧 **Sharp cuts without black in the right place** — where there is no black between spots (e.g. Canale 5 in 1984, 2-second bumpers) the cut was searched one second too late and landed on the next scene change: the previous spot took the bumper and the next spot lost its first seconds ("Suona con Ricordi"). Now the expected point of a sharp cut starts where the black would begin and, among sufficiently sharp scene changes, the nearest wins instead of the strongest (in heavily edited spots an inner cut can be sharper than the real one). On 71 test videos: 23 cuts improve, 2 already estimated points move by half a second, cuts on black do not change

- 🇮🇹 **Spot che iniziano al buio** — alcuni spot si aprono con qualche secondo di immagine quasi nera col sonoro (Super Faust, la sagoma di "Chiamalo amore", le scritte su nero di "Disco d'oro", il comunicato Fininvest battuto a macchina): il programma li scambiava per il nero tra due spot e il clip perdeva da 2 a 7 secondi di inizio. Ora nei neri lunghi (almeno 2 secondi) si ascolta l'audio: se dopo un silenzio il suono riparte ben prima che torni l'immagine, il clip parte dal suono. Le pause vere restano mute fino alla fine del nero e non cambiano (132 su 138 neri lunghi nei video di prova)
- 🇬🇧 **Spots that start in the dark** — some spots open with a few seconds of almost black picture with sound (Super Faust, the silhouette in "Chiamalo amore", the text on black of "Disco d'oro", the typed Fininvest announcement): the program took them for the black between two spots and the clip lost 2 to 7 seconds of its start. Now the audio of long blacks (at least 2 seconds) is checked: if after a silence the sound starts well before the picture returns, the clip starts from the sound. Real pauses stay silent until the end of the black and do not change (132 of 138 long blacks in the test videos)

### 🔧 Miglioramenti / Improvements

- 🇮🇹 **Verifica della data visibile** — mentre la data viene controllata online la pillola è grigio-azzurra con la clessidra ("📅 13-03-1983 ⏳"), così si distingue da una data che resta da confermare a mano; se la verifica non riesce, il tooltip spiega perché (es. "nessun video su YouTube con questo titolo"). Il tooltip dice anche se una data viene dal titolo YouTube o è stata inserita a mano, e un nome senza data mostra "⛔ Nessuna data"
- 🇬🇧 **Visible date check** — while the date is checked online the pill is grey-blue with an hourglass ("📅 13-03-1983 ⏳"), so it can be told apart from a date that still has to be confirmed by hand; if the check fails, the tooltip explains why (e.g. "no video on YouTube with this title"). The tooltip also tells whether a date comes from the YouTube title or was entered by hand, and a name without a date shows "⛔ No date"

- 🇮🇹 **Messaggio di uscita su misura** — chiudendo il programma il messaggio dice cosa si interrompe davvero (taglio, download da YouTube, ricerche) e come riprendere; se non c'è niente in corso chiede solo "Vuoi chiudere Spot Cutter?" e ricorda che la coda è salvata. Con un lavoro in corso il pulsante preselezionato è "Resta", così un Invio per sbaglio non lo interrompe
- 🇬🇧 **Tailored exit message** — when closing the program the message says what would actually be interrupted (cutting, YouTube download, searches) and how to resume; if nothing is running it just asks "Close Spot Cutter?" and reminds that the queue is saved. With work in progress the preselected button is "Stay", so an accidental Enter does not interrupt it

### 🛠️ Sviluppo / Development

- 🇮🇹 **Prova anti-regressione** (`tools/regressione.py`, solo per lo sviluppo, non fa parte del programma) — dopo ogni modifica al motore ricalcola in pochi secondi i tagli di tutti i video di prova e dice quali cambiano, con i fogli di fotogrammi prima/dopo; può anche confrontare con il motore di una versione precedente
- 🇬🇧 **Regression check** (`tools/regressione.py`, development only, not part of the program) — after each engine change it recalculates the cuts of all test videos in a few seconds and lists which ones change, with before/after frame sheets; it can also compare with the engine of an earlier version

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

- 🇮🇹 **Tagli manuali: nomi già pronti** — per un video senza txt, l'editor dei tagli manuali (✂️) cerca il video su YouTube. Se la descrizione ha solo la lista dei nomi senza orari, la prima riga parte già con il primo nome a 00:00 e ogni clic su un nero (+) aggiunge l'orario con il nome successivo; "⏭ Salta nome" e "⏮" servono per i nomi senza un nero proprio. Il nome proposto si ricalcola dalle righe presenti, quindi cancellando una riga sbagliata non si sfasa nulla. Se invece la descrizione ha già i timestamp, l'editor si riempie con il txt completo. La data del titolo viene applicata al salvataggio
- 🇬🇧 **Manual cuts: names ready** — for a video without a txt, the manual cuts editor (✂️) looks the video up on YouTube. If the description only has the list of names without times, the first line already starts with the first name at 00:00 and each click on a black (+) adds the time with the next name; "⏭ Skip name" and "⏮" handle names without a black of their own. The proposed name is recalculated from the lines present, so deleting a wrong line never shifts the names. If the description already has timestamps, the editor is filled with the complete txt. The date from the title is applied on save

- 🇮🇹 **Tagli manuali: anteprima dei neri** — accanto a ogni nero trovato un pulsante ▶ mostra 5 secondi di video intorno a quel punto in una piccola finestra, per capire subito se è uno stacco o un nero dentro uno spot, senza aprire tutto il video
- 🇬🇧 **Manual cuts: black preview** — next to each black found, a ▶ button shows 5 seconds of video around that point in a small window, to see at once whether it is a break or a black inside a spot, without opening the whole video

- 🇮🇹 **Tagli manuali: distanza tra i neri e neri già usati** — ogni nero mostra la distanza dal precedente ("+ 01:31 (+31s)"; gli spot durano quasi sempre 15, 20, 30 o 60 secondi) e quelli già inseriti nel txt diventano grigi
- 🇬🇧 **Manual cuts: gap between blacks and used blacks** — each black shows the distance from the previous one ("+ 01:31 (+31s)"; spots almost always last 15, 20, 30 or 60 seconds) and those already in the txt turn grey

### 🔧 Miglioramenti / Improvements

- 🇮🇹 **Ricerca txt per i file doppioni** — i nomi con un segno di doppione in fondo ("... e prom[2]", "(2)", "- Copia") non impediscono più di trovare il video: se il nome intero non trova nulla, la ricerca riprova senza quel segno
- 🇬🇧 **Txt search for duplicate files** — names ending with a duplicate mark ("... e prom[2]", "(2)", "- Copy") no longer prevent finding the video: if the full name finds nothing, the search retries without that mark

- 🇮🇹 **Pillola TXT arancione per le righe ignorate** — se il txt ha righe non nel formato "mm:ss - Nome" (es. "1.05 Spot…", "01:30 Spot…" senza trattino), la pillola diventa arancione e il tooltip le elenca; lo stesso elenco compare nel log quando il video parte. Prima venivano saltate in silenzio e quello spot restava attaccato al precedente. Righe vuote e separatori come "****" non contano
- 🇬🇧 **Orange TXT pill for ignored lines** — if the txt has lines not in the "mm:ss - Name" format (e.g. "1.05 Spot…", "01:30 Spot…" without the dash), the pill turns orange and the tooltip lists them; the same list appears in the log when the video starts. Before, they were silently skipped and that spot stayed attached to the previous one. Empty lines and separators like "****" don't count

- 🇮🇹 **Date senza barre riconosciute dal nome** — nomi come "1331983 Canale 5 ..." o "2071984 RaiUno ..." (data compatta senza zeri) prima avevano la data rossa "Sconosciuto": ora la data viene ricostruita (13/3/1983, 20/7/1984; nei titoli originali giorno e mese non hanno lo zero, quindi "2071984" non può essere il 2 luglio). Se le letture possibili sono due ("1121985" = 1/12 o 11/2) si sa almeno l'anno
- 🇬🇧 **Dates without slashes recognised from the name** — names like "1331983 Canale 5 ..." or "2071984 RaiUno ..." (compact date without zeros) used to have a red "Unknown" date: now the date is rebuilt (13/3/1983, 20/7/1984; in the original titles day and month have no leading zero, so "2071984" cannot be 2 July). When two readings are possible ("1121985" = 1/12 or 11/2) at least the year is known

- 🇮🇹 **Verifica online della data** — le date non certe (ricostruite dal nome o con solo l'anno) restano arancioni finché non vengono confrontate col titolo YouTube, in automatico appena il video entra in coda: se il video viene trovato vale la data del titolo e la pillola diventa verde, altrimenti resta da confermare a mano. Le date già certe e quelle inserite a mano non vengono toccate
- 🇬🇧 **Online date check** — uncertain dates (rebuilt from the name or year only) stay orange until they are compared with the YouTube title, automatically as soon as the video joins the queue: if the video is found the title date is used and the pill turns green, otherwise it must be confirmed by hand. Dates that are already certain or entered by hand are never touched

- 🇮🇹 **Cartella giusta per ogni clip** — il tipo si prende dalla prima parola del nome (Spot, Promo, Bumper, Annuncio, Cartello, Videosigla, Trailer): "Spot promozioni Fiat" non finisce più nei Promo, "Spot giornale annunci ..." negli Annunci, "Spot bambola Camilla TG Sebino" nei Telegiornali. Le sigle ("Sigla inizio ...", "Sigla fine trasmissioni") vanno in Videosigle
- 🇬🇧 **Right folder for every clip** — the type comes from the first word of the name (Spot, Promo, Bumper, Annuncio, Cartello, Videosigla, Trailer): "Spot promozioni Fiat" no longer ends up in Promo, "Spot giornale annunci ..." in Annunci, "Spot bambola Camilla TG Sebino" in Telegiornali. Theme tunes ("Sigla inizio ...", "Sigla fine trasmissioni") go to Videosigle

- 🇮🇹 **Marchi natalizi solo sotto le feste** — Alemagna, Motta (Tartufone), Bauli, Melegatti, Maina e Paluani mandano il clip in Natale solo nei video di novembre, dicembre e gennaio ("Spot caramelle Sanagola Alemagna" di febbraio resta tra gli spot); parole come natale, panettone, pandoro e buone feste valgono tutto l'anno
- 🇬🇧 **Christmas brands only during the holidays** — Alemagna, Motta (Tartufone), Bauli, Melegatti, Maina and Paluani send the clip to Natale only in November, December and January videos ("Spot caramelle Sanagola Alemagna" from February stays among the spots); words like natale, panettone, pandoro and buone feste count all year round

- 🇮🇹 **Nomi lunghi tagliati bene** — i nomi oltre 100 caratteri si tagliano all'ultima parola intera, senza lasciare parentesi aperte ("... Juventus-Argentinos Junior (sponsorizzato da Mo" → "... Juventus-Argentinos Junior")
- 🇬🇧 **Long names cut cleanly** — names over 100 characters are cut at the last whole word, without leaving open brackets ("... Juventus-Argentinos Junior (sponsorizzato da Mo" → "... Juventus-Argentinos Junior")

### 🐛 Correzioni / Fixes

- 🇮🇹 **"Interrotto" sulla card giusta** — con uno Stop durante i tagli, "Interrotto" compariva sul video successivo (mai partito) e quello fermato restava su "In lavorazione"
- 🇬🇧 **"Stopped" on the right card** — with a Stop during cutting, "Stopped" appeared on the next video (never started) while the stopped one stayed on "Processing"

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
