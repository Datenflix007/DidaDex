# DidaDex

Didaktisch-methodische Suchmaschine für Unterrichtsmaterialien – lokaler Crawler, SQLite-Resume und optionaler Desktop-Materialviewer.

<img width="1795" height="1187" alt="image" src="https://github.com/user-attachments/assets/3742d009-70bf-45d2-b6ef-8da8ba933909" />


## Start (Windows, Python 3.10+)

**Empfohlen – integrierte Python-Oberfläche mit DFS-Einstellungen und Viewer:**

```powershell
python engine_desktop.py
```

`engine.py` vereint Start, Stop, Export, Worker, Fachauswahl, die beiden Round-Robin-DFS-Parameter, den nativen Materialviewer und das Live-Dashboard. `engine_desktop.py` ist ein kompatibler Starter und öffnet dieselbe Oberfläche.

Auch `python engine.py` startet die vollständige Desktop-Oberfläche. Der bisherige Streamlit-Viewer bleibt als Rückfalloption vorhanden. Die Engine legt bei Bedarf eine `.venv` an und installiert Crawler-Abhängigkeiten aus `crawler/requirements_crawler.txt`.

**Crawler direkt:** `python crawler/crawler.py` startet den kanonischen Python-Crawler mit dem TEST-Standardprofil. Das Desktop-Fenster übergibt seine Laufkonfiguration als kleine temporäre JSON-Datei an dieselbe Datei. `crawler/crawler.ipynb` bleibt nur als historische Referenz erhalten und wird nicht mehr vom Desktop gestartet.

## Neu: Live-Dashboard während des Crawls

Nach **Crawler starten** tauscht `engine_desktop.py` die große Einstellungsmaske gegen ein **zweispaltiges Live-Dashboard** aus: links die Treffer-/Crawlerzahlen mit nativer Tiefen-Heatmap, rechts die fortlaufende Konsole mit Status und Fortschrittsanzeige. Mit **Sauber stoppen & exportieren** wird der bestehende Stoppprozess verwendet. Erst nach Beendigung lässt sich zu **Einstellungen** zurückkehren. Die Materialansicht bleibt als separater Tkinter-Tab erreichbar.

Die Dashboard-Daten stammen aus der bestehenden SQLite-Datenbank und einer kleinen zusätzlich erzeugten Statusdatei. Neben der bisherigen `depth_heatmap.html` wird `depth_heatmap_live.html` alle etwa drei Sekunden neu erzeugt. Die HTML-Datei lässt sich optional über den Button öffnen; **für die Heatmap im Python-Fenster wird kein Browser benötigt**.

Technische Details und die genaue Bedeutung der Kennzahlen: [`docs/live_dashboard.md`](docs/live_dashboard.md). Die Implementierung liegt in `engine.py`; `engine_desktop.py` bleibt als kompatibler Startweg erhalten.

## Neu: Round-Robin-DFS pro Seed

Der Crawler verarbeitet nicht mehr alle Seeds zuerst nach Tiefe 0. Stattdessen wählt er für jeden Seed ein kleines **Arbeitspaket**, besucht darin bevorzugt tiefere Links (DFS-ähnlich), wechselt zum nächsten Seed und setzt in der nächsten Runde mit größerer zulässiger Tiefe fort. Die Arbeitspakete, Tiefe und Anzahl paralleler Worker sind konfigurierbar.

| Modus | Maximale Seiten pro Seed-Runde | Tiefenschritt je Runde |
|---|---:|---:|
| TEST | 15 | 5 |
| STANDARD | 50 | 5 |
| NACHT | 100 | 5 |

**Im Desktop-Fenster** die Felder `DFS: Seiten pro Seed-Runde` und `Tiefenschritt pro Runde` verwenden. Die direkte Ausführung kann dieselben Werte über eine Laufkonfigurations-JSON an `crawler.py` übergeben. Ein Tiefenschritt von 5 bedeutet zunächst Tiefen 0–5, danach 0–10 usw.; erledigte URLs werden nicht wiederholt.

Offene, zulässige und einem Seed zugeordnete URLs bleiben in der persistenten Frontier. Sie werden in späteren Round-Robin-Runden mit wachsender Tiefengrenze weiter berücksichtigt, statt nach einer ersten flachen Runde liegen zu bleiben. Vollständig abgearbeitet werden sie, sofern keine Laufzeit-, Seiten-, Queue-, Host-, `robots.txt`-, Relevanz- oder Tiefengrenze greift.

**Beobachteter Testlauf:** Mit 10 Workern wurden in fünf Minuten etwa **2,5 MiB** Korpusdaten gesammelt. Das ist ein Ergebnis dieser konkreten Konfiguration, kein garantierter Durchsatz oder eine Zusage für jede Quelle.

**Wichtig:** Auch ein zweiminütiger Testlauf kann wenige *indexierte* Dokumente enthalten, obwohl deutlich mehr Webseiten besucht wurden. Die Qualitätsfilterung, die URL-Deduplizierung, die kuratierte Seed-Liste, `robots.txt`, Host-Pausen und die bisherige Lizenzbehandlung wurden nicht bewusst gelockert. Die Suchqualität muss anhand einer Stichprobe beurteilt werden.

## Ausgabe und Fortsetzung

- Suchkorpus: `crawler/outputs/runs/<RUN_NAME>/crawl.jsonl`
- Wiederaufnehmbarer Crawl-Zustand: `crawler/outputs/runs/<RUN_NAME>/crawler_state.sqlite`
- Durchsuchte Tiefen: `depth_heatmap.html`, `depth_heatmap.tsv`, `depth_heatmap.json`
- Laufprotokoll: `progress.log`

Dieselbe `RUN_NAME`-Kennung setzt die Datenbank fort; eine neue Kennung ergibt einen separaten Versuch. Laufdaten werden nicht mit dieser ZIP geliefert. Die SQLite-Tabellen `frontier` und `seed_schedule` erhalten neue Zuordnungen und Rundeninformationen. **Vor dem Überschreiben eine Sicherheitskopie des Projekts und bestehender Laufdaten anlegen.** Ältere `engine.py`- oder `crawler.py`-Versionen sollten mit derselben Laufdatenbank nicht erneut gestartet werden.

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

Ausführliche Erläuterung: [Workflow und Pipeline](docs/crawling_workflow_pipeline.md), [Round-Robin-DFS](docs/crawling_strategy.md), [Live-Dashboard](docs/live_dashboard.md) und [Desktop-Viewer](docs/desktop_viewer.md).

## Hinweise

Fachzuordnung und Qualitätsbewertung sind heuristisch, keine validierten Klassifikatoren. 500 MiB Korpusdaten werden nicht garantiert. Die bisherige Lizenzprüfung für Materialdateien ist **kein** vollständiger Rechtsnachweis für die Speicherung und Weitergabe von HTML-Seitentexten. Vor einer Veröffentlichung müssen Nutzungsrechte und Datenschutz geprüft werden.

## Live-Dashboard im Breitbild

`python engine_desktop.py` öffnet DidaDex standardmäßig maximiert. Nach Crawl-Start erscheint **links** (60 %) die vergrößerte Live-Statistik mit Tiefen-Heatmap, **rechts** (40 %) die fortlaufende Terminalausgabe mit Fortschrittsanzeige. Die Trennlinie ist verschiebbar; die Konsole kann automatisch ans Ende scrollen oder zum Kopieren angehalten werden. Die Einstellungen bleiben vor dem Start und nach dem Lauf erreichbar.

Für dieses Layout-Update nur die genannten Dateien ersetzen. `engine.py`, `crawler/crawler.py`, `crawler/config/` und bisherige Crawl-Daten **nicht** löschen oder überschreiben. Einzelheiten: `docs/live_dashboard.md`.
