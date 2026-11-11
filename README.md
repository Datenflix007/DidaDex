# DidaDex

Didaktisch-methodische Suchmaschine für Unterrichtsmaterialien – lokaler Crawler, SQLite-Resume und optionaler Desktop-Materialviewer.

## Start (Windows, Python 3.10+)

**Empfohlen – integrierte Python-Oberfläche mit DFS-Einstellungen und Viewer:**

```powershell
python engine_desktop.py
```

Die Desktop-Variante verwendet die vorhandene `engine.py` für Start, Stop, Export, Worker und Fachauswahl, ergänzt zwei Round-Robin-DFS-Parameter und zeigt den Materialviewer **direkt im Tkinter-Tab** ohne Browser oder Streamlit.

Alternativ lässt sich die **bisherige** `engine.py` weiterhin mit `python engine.py` starten; die neuen DFS-Standardwerte bleiben auch dort aktiv. Der bisherige Streamlit-Viewer bleibt als Rückfalloption vorhanden. Die Engine legt bei Bedarf eine `.venv` an und installiert Crawler-Abhängigkeiten aus `crawler/requirements_crawler.txt`.

**Notebook direkt:** `crawler/crawler.ipynb` in Jupyter öffnen, erste Einstellungszelle konfigurieren und „Run All“ ausführen. Im Notebook benötigte Pakete werden im aktiven Kernel installiert.

## Neu: Live-Dashboard während des Crawls

Nach **Crawler starten** tauscht `engine_desktop.py` die große Einstellungsmaske gegen ein **zweispaltiges Live-Dashboard** aus: links die Treffer-/Crawlerzahlen mit nativer Tiefen-Heatmap, rechts die fortlaufende Konsole mit Status und Fortschrittsanzeige. Mit **Sauber stoppen & exportieren** wird der bestehende Stoppprozess verwendet. Erst nach Beendigung lässt sich zu **Einstellungen** zurückkehren. Die Materialansicht bleibt als separater Tkinter-Tab erreichbar.

Die Dashboard-Daten stammen aus der bestehenden SQLite-Datenbank und einer kleinen zusätzlich erzeugten Statusdatei. Neben der bisherigen `depth_heatmap.html` wird `depth_heatmap_live.html` alle etwa drei Sekunden neu erzeugt. Die HTML-Datei lässt sich optional über den Button öffnen; **für die Heatmap im Python-Fenster wird kein Browser benötigt**.

Technische Details und die genaue Bedeutung der Kennzahlen: [`docs/live_dashboard.md`](docs/live_dashboard.md). `engine.py` weiterhin behalten, denn `engine_desktop.py` importiert diese Datei.

## Neu: Round-Robin-DFS pro Seed

Der Crawler verarbeitet nicht mehr alle Seeds zuerst nach Tiefe 0. Stattdessen wählt er für jeden Seed ein kleines **Arbeitspaket**, besucht darin bevorzugt tiefere Links (DFS-ähnlich), wechselt zum nächsten Seed und setzt in der nächsten Runde mit größerer zulässiger Tiefe fort. Die Arbeitspakete, Tiefe und Anzahl paralleler Worker sind konfigurierbar.

| Modus | Maximale Seiten pro Seed-Runde | Tiefenschritt je Runde |
|---|---:|---:|
| TEST | 15 | 5 |
| STANDARD | 50 | 5 |
| NACHT | 100 | 5 |

**Im Desktop-Fenster** die Felder `DFS: Seiten pro Seed-Runde` und `Tiefenschritt pro Runde` verwenden. **Im Notebook**: `DFS_DEPTH_STEP` und `PROFILE[MODUS]['pages_per_seed_turn']` in der ersten Codezelle ändern. Ein Tiefenschritt von 5 bedeutet zunächst Tiefen 0–5, danach 0–10 usw.; erledigte URLs werden nicht wiederholt.

**Wichtig:** Auch ein zweiminütiger Testlauf kann wenige *indexierte* Dokumente enthalten, obwohl deutlich mehr Webseiten besucht wurden. Die Qualitätsfilterung, die URL-Deduplizierung, die kuratierte Seed-Liste, `robots.txt`, Host-Pausen und die bisherige Lizenzbehandlung wurden nicht bewusst gelockert. Die Suchqualität muss anhand einer Stichprobe beurteilt werden.

## Ausgabe und Fortsetzung

- Suchkorpus: `crawler/outputs/runs/<RUN_NAME>/crawl.jsonl`
- Wiederaufnehmbarer Crawl-Zustand: `crawler/outputs/runs/<RUN_NAME>/crawler_state.sqlite`
- Durchsuchte Tiefen: `depth_heatmap.html`, `depth_heatmap.tsv`, `depth_heatmap.json`
- Laufprotokoll: `progress.log`

Dieselbe `RUN_NAME`-Kennung setzt die Datenbank fort; eine neue Kennung ergibt einen separaten Versuch. Laufdaten werden nicht mit dieser ZIP geliefert. Die SQLite-Tabellen `frontier` und `seed_schedule` erhalten neue Zuordnungen und Rundeninformationen. **Vor dem Überschreiben eine Sicherheitskopie des Projekts und bestehender Laufdaten anlegen.** Eine ältere `engine.py` kennt das neue Datenbankschema nicht; alte Notebook-Versionen sollten mit derselben Laufdatenbank nicht erneut gestartet werden.

## Materialviewer

`python engine_desktop.py` → Tab **Crawled Data Viewer**, oder separat:

```powershell
python crawledDataViewer/viewer_tk.py
```

Der Viewer zeigt Laufordner, Volltexte, Quellen, Materiallinks und Metadaten, ermöglicht Filter und manuelle Qualitätsbewertungen (`manual_labels.json`). `crawl.jsonl` bleibt dabei unverändert. Die neue Oberfläche benötigt Tkinter (bei normalen Windows-Python-Installationen enthalten).

## Installation und Tests

Die ZIP-Datei **im Hauptordner des GitHub-Repositories** entpacken; die darin enthaltene Struktur (`crawler/`, `crawledDataViewer/`, `docs/`, `tests/`) beim Kopieren erhalten. Nur gleichnamige Code-Dateien überschreiben. `engine.py`, `crawledDataViewer/viewer.py` und vorhandene Daten nicht löschen.

```powershell
python -m unittest discover -s tests -v
```

Ausführliche Erläuterung: [`docs/crawling_strategy.md`](docs/crawling_strategy.md). Desktop-Viewer: [`docs/desktop_viewer.md`](docs/desktop_viewer.md).

## Hinweise

Fachzuordnung und Qualitätsbewertung sind heuristisch, keine validierten Klassifikatoren. 500 MiB Korpusdaten werden nicht garantiert. Die bisherige Lizenzprüfung für Materialdateien ist **kein** vollständiger Rechtsnachweis für die Speicherung und Weitergabe von HTML-Seitentexten. Vor einer Veröffentlichung müssen Nutzungsrechte und Datenschutz geprüft werden.

## Live-Dashboard im Breitbild

`python engine_desktop.py` öffnet DidaDex standardmäßig maximiert. Nach Crawl-Start erscheint **links** (60 %) die vergrößerte Live-Statistik mit Tiefen-Heatmap, **rechts** (40 %) die fortlaufende Terminalausgabe mit Fortschrittsanzeige. Die Trennlinie ist verschiebbar; die Konsole kann automatisch ans Ende scrollen oder zum Kopieren angehalten werden. Die Einstellungen bleiben vor dem Start und nach dem Lauf erreichbar.

Für dieses Layout-Update nur `engine_desktop.py` und `crawledDataViewer/live_dashboard.py` ersetzen. `engine.py`, `crawler/crawler.ipynb` und bisherige Crawl-Daten **nicht** löschen oder überschreiben. Einzelheiten: `docs/live_dashboard.md`.
