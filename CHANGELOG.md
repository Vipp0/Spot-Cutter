# Changelog

Modifiche successive alla release 1.2. Le versioni 1.3, 1.3.1 e 1.3.2 sono uscite insieme nella release 1.3.2; la 1.3.3 insieme alla 1.3.4; la 1.3.5 insieme alla 1.3.6.
Changes after release 1.2. Versions 1.3, 1.3.1 and 1.3.2 were released together as 1.3.2; version 1.3.3 together with 1.3.4; version 1.3.5 together with 1.3.6.

---

## 🎬 Spot Cutter 1.4.2

### 🔧 Miglioramenti / Improvements

- 🇮🇹 **La stima del lavoro conta solo i video pronti** — il riepilogo sopra la coda stimava il lavoro su tutti i video, anche quelli senza txt o senza data che vengono saltati. Ora la durata resta quella di tutta la coda, ma la stima riguarda solo i video pronti e lo dice ("lavoro: circa 22m per i 6 pronti"). Le durate non vengono più rilette a ogni ridisegno della coda: si usano quelle già lette per le card
- 🇬🇧 **The work estimate counts only the ready videos** — the summary above the queue estimated the work on all videos, including those without a txt or a date, which are skipped. Now the length is still that of the whole queue, but the estimate covers only the ready videos and says so ("work: about 22m for the 6 ready"). Lengths are no longer read again at every queue redraw: those already read for the cards are used

- 🇮🇹 **Il motivo di un taglio fallito** — se ffmpeg non riesce a creare un clip, il log della finestra ora aggiunge al codice anche il motivo ("…: nome.mkv — No space left on device") e il log tecnico riporta il messaggio completo di ffmpeg. Il comando di taglio è lo stesso di prima
- 🇬🇧 **The reason for a failed cut** — if ffmpeg cannot create a clip, the window log now adds the reason to the code ("…: name.mkv — No space left on device") and the technical log holds the full ffmpeg message. The cut command is the same as before

### 🐛 Correzioni / Fixes

- 🇮🇹 **Avvio da un terminale non UTF-8** — lanciando il programma da alcuni terminali di Windows, una scritta di servizio con un'emoji poteva farlo chiudere subito. Quelle scritte ora vanno nel log tecnico, e una console che non sa scrivere un carattere non ferma più il programma
- 🇬🇧 **Starting from a non-UTF-8 terminal** — when launching the program from some Windows terminals, a service message with an emoji could make it close at once. Those messages now go to the technical log, and a console that cannot write a character no longer stops the program

---

## 🎬 Spot Cutter 1.4.1

### ✨ Nuove funzionalità / New features

- 🇮🇹 **Il download riprova da solo** — ogni tanto YouTube interrompe un download a metà (errore 403) e il programma si limitava a dire "yt-dlp terminato con codice 1": bastava riprovare a mano, ma in un download di tanti video restavano dei buchi. Ora, se il download fallisce, il programma aspetta 5 secondi e riprova da solo fino a 3 tentativi, riprendendo dal pezzo già scaricato. Se fallisce ancora, il log dice il motivo vero (YouTube ha rifiutato, troppe richieste, connessione, video non disponibile) invece del solo codice; per un video rimosso o privato non riprova
- 🇬🇧 **Downloads retry by themselves** — every now and then YouTube interrupts a download halfway (error 403) and the program only said "yt-dlp ended with code 1": retrying by hand was enough, but when downloading many videos some were left missing. Now, if the download fails, the program waits 5 seconds and retries by itself up to 3 attempts, resuming from the part already downloaded. If it still fails, the log gives the real reason (YouTube refused, too many requests, connection, video unavailable) instead of just the code; for a removed or private video it does not retry

- 🇮🇹 **Log tecnico su file** — tutto ciò che passa nel log della finestra viene scritto anche in un file, con data e ora, insieme a ciò che nella finestra non entra: i messaggi d'errore completi di yt-dlp, i comandi lanciati, gli errori imprevisti del programma e gli avvisi interni, la versione e gli strumenti trovati all'avvio. Serve a capire cosa è successo quando qualcosa va storto. Il file è `spotcutter.log` nella cartella `%APPDATA%\SpotCutter`, non supera i 5 MB (se ne conserva uno solo precedente) e si apre dal menu "⋯" sopra la coda, voce "Apri il log tecnico". Il titolo della finestra ora mostra anche la versione
- 🇬🇧 **Technical log file** — everything that goes through the window log is also written to a file, with date and time, together with what does not fit in the window: the full yt-dlp error messages, the commands launched, the program's unexpected errors and internal warnings, the version and the tools found at startup. It helps to understand what happened when something goes wrong. The file is `spotcutter.log` in the `%APPDATA%\SpotCutter` folder, never exceeds 5 MB (only one previous file is kept) and opens from the "⋯" menu above the queue, entry "Open the technical log". The window title now also shows the version

### 🔧 Miglioramenti / Improvements

- 🇮🇹 **I video "solo nomi" si riconoscono subito** — alcune descrizioni più vecchie su YouTube hanno la lista dei nomi degli spot ma non gli orari: il txt non si può creare da solo, ma con i tagli manuali i nomi si inseriscono da soli a ogni nero scelto. Finora niente lo diceva: la card mostrava solo "NO TXT". Ora la pillola è azzurra e dice quanti nomi sono pronti ("NO TXT · 18 nomi"), il log lo segnala e un clic sulla pillola apre direttamente i tagli manuali, che usano i nomi già trovati senza rifare la ricerca
- 🇬🇧 **"Names only" videos are recognised at a glance** — some older descriptions on YouTube have the list of spot names but no times: the txt cannot be created automatically, but with manual cuts the names are inserted by themselves at each black chosen. Until now nothing said so: the card only showed "NO TXT". Now the pill is light blue and says how many names are ready ("NO TXT · 18 names"), the log reports it and a click on the pill opens manual cuts directly, which use the names already found without searching again

---

## 🎬 Spot Cutter 1.4.0

### ✨ Nuove funzionalità / New features

- 🇮🇹 **Elenco finale dei clip da controllare** — gli stacchi senza nero vengono segnalati mentre il video si elabora, ma lì scorrono via. A fine lavoro il log li ripete tutti insieme, raggruppati per video e scritti per clip: orario, nome e punto da guardare ("03:05 Spot Ford Escort — inizio e fine"). I punti solo stimati sono in rosso; i bumper non vengono elencati, a meno che un loro estremo sia stimato. La finestra di fine lavoro dice quanti clip sono da controllare, e il log ora conserva 800 righe invece di 150, così l'elenco ci sta tutto. Lo stesso elenco viene aggiunto al file `Da controllare.txt` nella cartella della libreria, con la data dell'elaborazione, una casella da spuntare per ogni clip e il percorso del file del clip
- 🇬🇧 **Final list of clips to check** — cuts without black are reported while the video is processed, but there they scroll away. At the end the log repeats them all together, grouped by video and written per clip: time, name and the point to look at ("03:05 Spot Ford Escort — start and end"). Points that are only estimated are in red; bumpers are not listed, unless one of their ends is estimated. The end-of-work window says how many clips need checking, and the log now keeps 800 lines instead of 150, so the whole list fits. The same list is appended to the file `Da controllare.txt` in the library folder, with the date of the run, a box to tick for each clip and the path of the clip file

- 🇮🇹 **Filtri per stato sulla coda** — sopra la coda ci sono tre pastiglie con il conteggio: Tutti, Pronti, Da sistemare. Con un clic su "Da sistemare" restano visibili solo i video senza txt o con la data da confermare, senza dover scorrere una coda lunga; i numeri d'ordine restano quelli della coda intera
- 🇬🇧 **Status filters on the queue** — above the queue there are three chips with a count: All, Ready, To fix. Clicking "To fix" leaves only the videos without a txt or with a date to confirm, without scrolling a long queue; the order numbers stay those of the whole queue

- 🇮🇹 **Ripresa della coda: si può anche scartarla** — all'avvio, alla domanda "Riprendere la coda?" le risposte ora sono tre: "Riprendi", "Non ora" (la coda resta da parte e la domanda torna al prossimo avvio) e "Scarta la coda" (viene dimenticata e non viene più proposta; i video restano dove sono)
- 🇬🇧 **Queue restore: it can also be discarded** — at startup, the question "Restore the queue?" now has three answers: "Restore", "Not now" (the queue is kept aside and the question comes back at the next start) and "Discard the queue" (it is forgotten and no longer offered; the videos stay where they are)

### 🎨 Nuova grafica / New look

- 🇮🇹 **Intestazione della coda al posto della barra dei pulsanti** — sopra la coda ora c'è il titolo "Coda" con sotto il riepilogo (quanti video, quanto durano, quanto lavoro), che prima stava in piccolo a destra. L'ordinamento è un solo menu ("Ordina"; scegliendo di nuovo la stessa voce si inverte), salvataggio e caricamento della sessione sono nel menu "⋯", e "Cerca su YouTube" compare solo quando in coda ci sono video senza txt, dicendo quanti sono. I contatori dei clip creati (Spot, Promo, Bumper…) si sono spostati nel pannello in basso, accanto all'avanzamento, e compaiono solo quando c'è qualcosa da contare
- 🇬🇧 **Queue header instead of the button bar** — above the queue there is now the title "Queue" with the summary below it (how many videos, how long they are, how much work), which used to sit small on the right. Sorting is a single menu ("Sort"; choosing the same entry again reverses it), saving and loading a session are in the "⋯" menu, and "Search on YouTube" appears only when the queue has videos without a txt, saying how many. The counters of the clips created (Spot, Promo, Bumper…) moved to the bottom panel, next to the progress, and appear only when there is something to count

- 🇮🇹 **Interfaccia ridisegnata** — stessi comandi negli stessi posti, aspetto nuovo. I colori vengono dal logo: blu notte per gli elementi importanti (pannello dell'avanzamento e del log, pulsanti principali delle finestre); i pulsanti di YouTube restano rossi e arancione per l'avanzamento totale. I pulsanti secondari sono tenui e le voci di servizio (Svuota coda, Libreria, Storico, Impostazioni) sono righe leggere; le scritte non sono più in maiuscolo
- 🇬🇧 **Redesigned interface** — same controls in the same places, new look. The colours come from the logo: night blue for the important elements (progress and log panel, main buttons of the windows); the YouTube buttons stay red and orange for the total progress. Secondary buttons are soft and service entries (Clear queue, Library, History, Settings) are light rows; labels are no longer in capitals

- 🇮🇹 **Icone uniformi al posto delle emoji** — pulsanti, card e barra della coda usano le icone di sistema di Windows, tutte dello stesso disegno; i pulsanti delle card si colorano solo al passaggio del mouse. Le pillole di txt e data hanno un fondo chiaro con il testo scuro dello stesso colore (verde, arancione, rosso e grigio-azzurro mantengono il loro significato) e i contatori in alto mostrano il nome in grigio e il numero nel colore della categoria, leggibile su bianco
- 🇬🇧 **Consistent icons instead of emoji** — buttons, cards and the queue bar use the Windows system icons, all in the same style; card buttons take colour only on hover. The txt and date pills have a light background with dark text of the same colour (green, orange, red and grey-blue keep their meaning) and the counters at the top show the name in grey and the number in the category colour, readable on white

- 🇮🇹 **Card con anteprima e informazioni** — ogni video in coda mostra un fotogramma del video e, sotto il titolo, canale, durata e quanti clip prevede il txt ("Canale 5 · 14 min 01 s · 36 clip nel txt"). Anteprima e durata si leggono in sottofondo dopo che il video è entrato in coda, senza rallentare il programma, e l'anteprima viene conservata per le volte successive. Un titolo troppo lungo si accorcia invece di allargare la card
- 🇬🇧 **Cards with preview and information** — every queued video shows a frame of the video and, under the title, channel, length and how many clips the txt expects ("Canale 5 · 14 min 01 s · 36 clips in the txt"). Preview and length are read in the background after the video enters the queue, without slowing the program down, and the preview is kept for the next times. A title that is too long is shortened instead of widening the card

- 🇮🇹 **Avvia verde, Stop rosso** — sono i due soli pulsanti pieni e colorati della finestra
- 🇬🇧 **Green Start, red Stop** — they are the only two filled, coloured buttons in the window

- 🇮🇹 **Avanzamento e log in un pannello unico** — in basso c'è un solo pannello blu notte: in alto l'operazione in corso con la percentuale e la sua barra, sotto il totale dei video con la barra arancione, e poi il log. Occupa meno spazio di prima, quindi la coda ne ha di più; a programma fermo dice "Pronto"
- 🇬🇧 **Progress and log in a single panel** — at the bottom there is one night-blue panel: at the top the current operation with its percentage and bar, below it the total of the videos with the orange bar, then the log. It takes less room than before, so the queue has more; when idle it says "Ready"

- 🇮🇹 **Log che si apre senza scatti** — il pulsante che ingrandisce il log da sempre andava a scatti: il riquadro cresceva fino a metà e poi saltava all'altezza finale, e in chiusura non si animava affatto. Ora si anima l'altezza vera del riquadro, in apertura e in chiusura, anche se si clicca di nuovo a metà movimento
- 🇬🇧 **Log that opens without jerks** — the button that enlarges the log had always been jerky: the box grew halfway and then jumped to its final height, and on closing it was not animated at all. Now the real height of the box is animated, both opening and closing, even when clicking again halfway through

- 🇮🇹 **Finestre secondarie** — impostazioni, editor del txt, data, storico, tagli manuali e finestre di messaggio seguono lo stesso stile: un pulsante principale blu notte per finestra, gli altri tenui
- 🇬🇧 **Secondary windows** — settings, txt editor, date, history, manual cuts and message boxes follow the same style: one night-blue main button per window, the others soft

---

## 🎬 Spot Cutter 1.3.11

### ✨ Nuove funzionalità / New features

- 🇮🇹 **Stima del tempo di lavoro della coda** — l'etichetta in alto a destra mostrava solo la durata totale dei video ("20 video · 3h 12m"), che si poteva scambiare per il tempo mancante. Ora si chiama "In coda:" e dice entrambe le cose: "20 video · 3h 12m di video · lavoro: circa 25m". La stima usa la velocità reale del computer: a ogni elaborazione il programma misura quanto ci ha messo rispetto alla durata dei video e ne tiene una media, separata per il taglio diretto e per il master, usando quella dell'opzione attiva. Compare dopo la prima elaborazione e si adatta da sola a computer diversi
- 🇬🇧 **Estimated working time for the queue** — the label at the top right only showed the total length of the videos ("20 videos · 3h 12m"), which could be mistaken for the time left. It is now called "In queue:" and says both: "20 videos · 3h 12m of video · work: about 25m". The estimate uses the real speed of the computer: at each run the program measures how long it took compared with the length of the videos and keeps an average, separate for direct cutting and for the master, using the one for the active option. It appears after the first run and adapts by itself to different computers

---

## 🎬 Spot Cutter 1.3.10

### 🐛 Correzioni / Fixes

- 🇮🇹 **Chiusura improvvisa durante la ricerca automatica del txt** — nella 1.3.9, aggiungendo alla coda dei video senza txt, i video in coda potevano sparire e subito dopo il programma si chiudeva da solo. Gli esiti della ricerca automatica aggiornavano la coda da un thread diverso da quello dell'interfaccia; ora arrivano nel modo giusto, come per il pulsante "Cerca txt mancanti". I video già forniti di txt non erano interessati
- 🇬🇧 **Sudden exit during the automatic txt search** — in 1.3.9, adding videos without a txt to the queue could make the queued videos disappear and the program close by itself right after. The results of the automatic search updated the queue from a thread other than the interface one; they now arrive the right way, as with the "Search missing txt" button. Videos that already had a txt were not affected

---

## 🎬 Spot Cutter 1.3.9

### ✨ Nuove funzionalità / New features

- 🇮🇹 **Il txt si cerca da solo** — quando un video entra in coda senza txt (trascinato, caricato da una cartella o ripreso da una sessione) il programma lo cerca subito su YouTube, senza dover premere "Cerca txt mancanti". Durante la ricerca la pillola del txt è grigio-azzurra con la clessidra ("📄 TXT ⏳"); se il video si trova, il txt arriva dalla descrizione e con la stessa ricerca si conferma anche la data. Ogni video si cerca una volta per sessione, un txt già presente non viene mai sovrascritto e il pulsante resta per riprovare a mano. Se il txt arriva mentre si stanno già tagliando gli altri video, quello viene elaborato quando arriva il suo turno
- 🇬🇧 **The txt is searched automatically** — when a video enters the queue without a txt (dragged, loaded from a folder or restored from a session) the program searches for it on YouTube straight away, without pressing "Search missing txt". During the search the txt pill is grey-blue with an hourglass ("📄 TXT ⏳"); if the video is found, the txt comes from the description and the same search also confirms the date. Each video is searched once per session, an existing txt is never overwritten and the button stays for a manual retry. If the txt arrives while the other videos are already being cut, that video is processed when its turn comes

### ✨ Miglioramenti del motore / Engine improvements

- 🇮🇹 **L'ultima nota del bumper non viene più troncata** — nelle registrazioni del 1983-84 senza nero tra i pezzi, il suono dura spesso qualche fotogramma più dell'immagine: l'ultima nota del jingle del bumper finiva nei primi fotogrammi dello spot successivo, quindi il bumper usciva troncato e lo spot iniziava con un residuo di jingle. Ora, sugli stacchi netti, se il suono del pezzo prima continua dopo lo stacco e poi tace (entro mezzo secondo), l'audio si taglia nel punto del silenzio: il pezzo prima tiene il suo suono intero, con l'ultimo fotogramma fermo per quei pochi fotogrammi, e quello dopo parte pulito. L'immagine resta tagliata esattamente dove prima e l'audio non viene ricodificato. Dove lo spot successivo parte subito col sonoro non c'è un silenzio a cui agganciarsi e il taglio resta com'era. Nei video di prova: 20 stacchi su 141 senza nero, code da 0,06 a 0,40 secondi; nessun punto di taglio si sposta
- 🇬🇧 **The last note of the bumper is no longer cut off** — in 1983-84 recordings without black between items, the sound often lasts a few frames longer than the picture: the last note of the bumper jingle ended in the first frames of the next spot, so the bumper came out cut off and the spot started with a leftover of the jingle. Now, on sharp cuts, if the sound of the previous item continues after the cut and then goes silent (within half a second), the audio is cut at the silence: the previous item keeps its whole sound, with its last frame held for those few frames, and the next one starts clean. The picture is still cut exactly where it was and the audio is not re-encoded. Where the next spot starts with sound straight away there is no silence to hook onto and the cut stays as it was. On the test videos: 20 of 141 cuts without black, tails from 0.06 to 0.40 seconds; no cut point moves

### 🔧 Miglioramenti / Improvements

- 🇮🇹 **Via un avviso inutile dal log** — all'inizio di ogni video con la data scritta in modo insolito nel nome il log diceva "la data potrebbe essere ambigua, verificare", anche se la data era già stata confermata online o inserita a mano. Un video con la data non confermata oggi viene saltato, quindi l'avviso non serviva più
- 🇬🇧 **A useless warning removed from the log** — at the start of every video with an unusual date in its name the log said "the date may be ambiguous, please check", even though the date had already been confirmed online or entered by hand. A video with an unconfirmed date is now skipped, so the warning was no longer needed

---

## 🎬 Spot Cutter 1.3.8

### ✨ Nuove funzionalità / New features

- 🇮🇹 **Un video non pronto non blocca più la coda** — prima bastava un video senza txt o con la data da confermare per lasciare grigio il tasto Avvia. Ora Avvia si accende se almeno un video è pronto e dice quanti ne partono ("▶ AVVIA (19 di 20)"); il tooltip elenca quelli lasciati fuori con il motivo. Al clic una finestra chiede conferma, poi i video non pronti vengono saltati e restano in coda, mentre quelli elaborati escono: alla fine restano solo quelli da sistemare. Il controllo si fa quando arriva il turno di ogni video, quindi se nel frattempo ne sistemi uno (o la verifica online della data finisce) viene elaborato normalmente. Il riepilogo finale elenca i saltati
- 🇬🇧 **A video that is not ready no longer blocks the queue** — before, a single video without a txt or with a date to confirm kept the Start button grey. Now Start lights up if at least one video is ready and says how many will run ("▶ START (19 of 20)"); the tooltip lists the ones left out with the reason. On click a window asks for confirmation, then videos that are not ready are skipped and stay in the queue, while processed ones leave it: at the end only the ones to fix remain. The check is made when each video's turn comes, so if you fix one in the meantime (or the online date check finishes) it is processed normally. The final summary lists the skipped ones

- 🇮🇹 **yt-dlp si scarica da solo** — se yt-dlp manca, all'avvio (e quando premi un pulsante che lo usa) il programma propone di scaricarlo dalla pagina ufficiale di yt-dlp e lo mette nella cartella `bin`: circa 18 MB, una volta sola, con controllo dell'impronta SHA-256 del file. Se rispondi "Non ora" all'avvio non lo richiede più, ma lo ripropone quando serve. Come prima, a ogni avvio yt-dlp viene poi aggiornato da solo
- 🇬🇧 **yt-dlp downloads itself** — if yt-dlp is missing, at startup (and when you press a button that needs it) the program offers to download it from the official yt-dlp page and puts it in the `bin` folder: about 18 MB, only once, with a SHA-256 check of the file. If you answer "Not now" at startup it does not ask again, but offers it when needed. As before, yt-dlp is then updated automatically at every startup

### ✨ Miglioramenti del motore / Engine improvements

- 🇮🇹 **Il programma impara la durata dei bumper** — i bumper di un video sono sempre gli stessi, ripetuti: se lo stesso bumper compare almeno 3 volte e quasi sempre dura uguale (es. 1,7 secondi), quando uno esce molto più lungo o più corto vuol dire che un suo estremo è sbagliato (di solito un bumper scuro seguito da uno spot che inizia scuro, dove lo stacco quasi non si vede). Il programma sposta allora l'estremo meno sicuro alla distanza giusta, agganciandolo allo stacco più vicino a quel punto. Per prudenza un estremo su un nero non si tocca mai, uno stacco vero si sposta solo su un altro stacco vero, e se il txt stesso dice che quel bumper è più lungo (es. doppia sigla) resta com'è. Nei video di prova: 9 tagli migliorano, nessuno peggiora; in un video Retequattro del 1984 i 17 bumper passano da durate tra 0,5 e 3 secondi a 1,6–1,8
- 🇬🇧 **The program learns the bumper length** — the bumpers of a video are always the same, repeated: if the same bumper appears at least 3 times and almost always lasts the same (e.g. 1.7 seconds), when one comes out much longer or shorter one of its ends is wrong (usually a dark bumper followed by a spot that starts dark, where the cut is barely visible). The program then moves the less reliable end to the right distance, snapping it to the nearest cut around that point. To be safe, an end on a black is never touched, a real cut is only moved onto another real cut, and if the txt itself says that bumper is longer (e.g. double ident) it stays as it is. On the test videos: 9 cuts improve, none gets worse; in a 1984 Retequattro video the 17 bumpers go from lengths between 0.5 and 3 seconds to 1.6–1.8

- 🇮🇹 **Orari del txt di una registrazione più lunga** — alcune descrizioni hanno gli orari che partono, ad esempio, da 03:57 per un video di 4 minuti: prima tutti gli stacchi finivano fuori dal video. Ora, se gli orari superano la durata del video ma facendoli partire da zero combaciano con i neri, il programma li usa spostati e lo scrive nel log; se non combaciano avvisa di controllare il txt
- 🇬🇧 **Txt times from a longer recording** — some descriptions have times starting, for example, at 03:57 for a 4-minute video: before, all the cuts ended up outside the video. Now, if the times exceed the video length but match the blacks when shifted to start from zero, the program uses them shifted and says so in the log; if they do not match it warns to check the txt

### 🐛 Correzioni / Fixes

- 🇮🇹 **Orario doppio nel txt: niente più spot schiacciati** — se due righe del txt avevano lo stesso orario per errore, la seconda poteva prendersi un nero di minuti prima e tutti gli spot in mezzo finivano schiacciati in un punto solo (clip da mezzo secondo e uno lunghissimo). Ora una riga con l'orario doppio prende un nero solo se è vicino al suo orario. Nei video di prova: 17 tagli tornano al loro posto, nessuno peggiora
- 🇬🇧 **Duplicate time in the txt: no more squashed spots** — if two txt lines had the same time by mistake, the second could grab a black from minutes earlier and all the spots in between were squashed into a single point (half-second clips and one very long one). Now a line with a duplicate time takes a black only if it is near its time. In the test videos: 17 cuts go back to their place, none gets worse

- 🇮🇹 **Avviso per gli orari doppi o fuori ordine** — quando una riga del txt ha l'orario uguale o precedente alla riga prima, la pillola TXT diventa arancione, il tooltip elenca le righe e il log lo segnala: va bene se i due pezzi iniziano davvero nello stesso secondo, altrimenti basta correggere l'orario nel txt
- 🇬🇧 **Warning for duplicate or out-of-order times** — when a txt line has a time equal to or earlier than the previous line, the TXT pill turns orange, the tooltip lists the lines and the log reports it: fine if the two items really start in the same second, otherwise just correct the time in the txt

- 🇮🇹 **Niente falso errore sui video in bianco e nero** — nei video senza colori (o con colori molto sbiaditi) il log mostrava in rosso "Ricerca neri terminata con errore", anche se l'analisi era completa e i tagli giusti. Ora l'avviso compare solo per gli errori veri
- 🇬🇧 **No false error on black-and-white videos** — in videos without colours (or with very faded colours) the log showed "Black search ended with an error" in red, even though the analysis was complete and the cuts correct. The warning now appears only for real errors

- 🇮🇹 **yt-dlp trova sempre ffmpeg** — per unire video e audio yt-dlp ha bisogno di ffmpeg, ma lo vedeva solo se stavano nella stessa cartella o se ffmpeg era nel PATH di sistema: con yt-dlp nella cartella del programma e ffmpeg in `bin` (o viceversa) il download usciva male. Ora il programma rende visibili la sua cartella e `bin` a tutto ciò che lancia, compresa l'anteprima ▶ dei tagli manuali
- 🇬🇧 **yt-dlp always finds ffmpeg** — to merge video and audio yt-dlp needs ffmpeg, but it only saw it when they were in the same folder or ffmpeg was in the system PATH: with yt-dlp in the program folder and ffmpeg in `bin` (or the other way round) the download came out wrong. Now the program makes its folder and `bin` visible to everything it launches, including the ▶ preview of manual cuts

- 🇮🇹 **Niente falso avviso con yt-dlp nel PATH di sistema** — se yt-dlp era installato solo nel PATH di sistema, all'avvio il log diceva che non c'era e l'aggiornamento automatico non partiva, anche se il download funzionava. Ora viene riconosciuto e aggiornato
- 🇬🇧 **No false warning with yt-dlp in the system PATH** — if yt-dlp was installed only in the system PATH, at startup the log said it was missing and the automatic update did not start, even though downloading worked. It is now recognised and updated

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
