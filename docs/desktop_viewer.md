# 11.11.2026 – Native Materialanzeige und Seed-Round-Robin-DFS

## Motivation

Die ersten kurzen Testläufe lieferten wenige, aber inhaltlich brauchbare Dokumente. Nach einem zweiminütigen Crawl ist eine geringe Zahl indexierter Dokumente **noch kein Nachweis** für eine unzureichende Navigationstiefe. Im Zuge der neuen Scheduler-Änderung wurde zusätzlich eine Seed-weise, schrittweise vertiefte Round-Robin-DFS eingebaut; die Klassifikationslogik bleibt erhalten. Details: [`crawling_strategy.md`](crawling_strategy.md).

## Geänderte oder ergänzte Dateien

| Pfad | Änderung |
|---|---|
| `crawler/crawler.ipynb` | Parallele `robots.txt`-Abfrage (je Host geschützt), Round-Robin-DFS mit progressiver Tiefengrenze, persistenter Seed-Zuordnung. Qualitätsfilter und Seed-Liste unverändert. |
| `crawledDataViewer/viewer_tk.py` | Neuer Tkinter-Viewer, der ohne Webserver oder Streamlit im Python-Fenster läuft. |
| `engine.py` | Vereint Launcher, native Viewer-Registerkarte, Live-Dashboard und zwei DFS-Eingabefelder. `engine_desktop.py` ist ein kompatibler Starter. |
| `README.md` | Start- und Funktionsbeschreibung aktualisiert. |
| `docs/desktop_viewer.md` | Diese technische Dokumentation. |

**Bewusst nicht ersetzt:** `crawledDataViewer/viewer.py` und die Requirements-Dateien. Der bestehende Crawler-Funktionsumfang und die Inhaltsklassifikation bleiben erhalten, sein Scheduling ist jedoch bewusst geändert. `python engine.py` startet nun die vereinheitlichte Oberfläche; der neue Notebook-Crawler verwendet dort Round-Robin-DFS mit Standardwerten.

## Installation / Übernahme der ZIP

1. Bestehenden Repository-Ordner sichern oder Änderungen committen.
2. ZIP **im Stammordner des Repositories entpacken**, dabei `crawler/crawler.ipynb` und `README.md` überschreiben.
3. Die neuen Unterordnerpfade unverändert beibehalten. `engine.py` muss nach wie vor im Projektstamm liegen.
4. Start über `python engine.py` (Windows mit Tkinter, Python 3.10+); `python engine_desktop.py` bleibt kompatibel.
5. Im Tab **Crawled Data Viewer** Lauf auswählen oder auf **JSONL öffnen** klicken. Du kannst auch unabhängig davon `python crawledDataViewer/viewer_tk.py` starten.

### Bestehende Laufdaten

Der Viewer erwartet vorzugsweise `crawler/outputs/runs/<RUN_NAME>/crawl.jsonl`. Alte und neuere `.jsonl`-Dateien können auch manuell geöffnet werden, sofern jede Zeile ein JSON-Objekt mit wenigstens `title` / `url` / `text` enthält. Zusätzliche Metadaten werden, falls vorhanden, angezeigt. Die Ausgabeformate des Crawlers sind nicht geändert worden.

### Suche, Bewertung, Skalierung

- Die Eingabe durchsucht Titel, URL, Quelle, Fachhinweise und **die ersten 6.000 Zeichen** des Texts. Eine komplette Volltextsuche ist nicht Bestandteil dieses Datenviewers.
- Die vollständigen Texte werden für Details per Byte-Offset aus der Originaldatei gelesen.
- Die Anzeige blättert 250 Treffer pro Seite; gefilterte Treffer können als CSV exportiert werden.
- Eine manuelle Bewertung schreibt `manual_labels.json` neben die JSONL. `crawl.jsonl` bleibt unverändert.
- Qualitätsschwellen im Viewer: `score >= 10` = Unterrichtsmaterial, `6–9` = Prüfen, sonst Unbrauchbar. Das sind vorläufige Labels zur manuellen Sichtung – keine Ground-Truth-Werte.
- Bei einem sehr großen Korpus erfordert auch das Einlesen der Kurzmetadaten Zeit. Die Verarbeitung läuft deshalb in einem Hintergrund-Thread und blockiert nicht die Tkinter-Oberfläche.

## Warum der Crawl mit wenigen Treffern enden kann

Die Laufzeit enthält DNS-/TLS-Verbindungen, initiale `robots.txt`-Abrufe, Download von HTML, HTML-Analyse und gegebenenfalls Materialdateien. Jede von der Klassifizierung abgelehnte Seite erzeugt **keinen** Korpuseintrag, kann aber weiterführende Links erschließen. Daher ist *„vier Dokumente nach zwei Minuten“* nicht mit *„vier Seiten besucht“* gleichzusetzen. Stattdessen `progress.log`, `crawler_state.sqlite` und `depth_heatmap.html` eines längeren Laufs prüfen.

## Nächste sinnvolle Evaluation

- Zunächst 10 Minuten im TEST-Profil, möglichst mit neuem Laufnamen.
- Anzahl erledigter URLs, Fehler, Warteschlangenwachstum, Tiefe > 0 und Zahl der wirklich indexierten Dokumente in `progress.log` / Heatmap kontrollieren.
- Qualitätsstichprobe von 20–50 Treffern anhand *konkreter Unterrichtsaufträge*, fachlicher Eignung, Materialverweise und Nutzbarkeit bilden.
- Erst dann entscheiden, ob Navigation, Materialerkennung oder Klassifikationsschwellen angepasst werden müssen.

## Hinweis zu robots.txt und Lizenz

Die Änderung betrifft **nur** die Parallelität verschiedener Hosts. Pro Host bleibt der bestehende Lock erhalten und `DOWNLOAD_DELAY_SECONDS` sowie `robots.txt`-Crawl-Delays werden berücksichtigt. Auch die erlaubte Hostliste und die Materiallizenzprüfung wurden nicht gelockert. Ein Lizenzhinweis im Viewer ist lediglich aus den Metadaten übernommen.
