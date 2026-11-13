# DidaDex – aktueller Crawling-Workflow und Datenpipeline

Stand: 13.11.2026

Diese Datei beschreibt den durchgängigen Laufweg vom Desktop bis zum
exportierten Suchkorpus. Sie ergänzt, statt wiederholt, die vorhandenen
Detaildokumentationen:

- [Round-Robin-DFS und Scheduler](crawling_strategy.md)
- [Live-Dashboard und Kennzahlen](live_dashboard.md)
- [Desktop-Viewer](desktop_viewer.md)

## Kurzfassung der Umstellung

`crawler/crawler.py` ist die kanonische ausführbare Crawler-Laufzeit. Die
Desktop-Anwendung startet keine Notebook-Zellen und erstellt keinen temporären
Python-Runner mehr. `crawler/crawler.ipynb` bleibt ausschließlich als
historische Referenz im Repository.

Die großen, versionskontrollierten Datenlisten liegen getrennt vom Code unter
`crawler/config/`. Dadurch ist der Laufweg nachvollziehbar und der
Quellkatalog kann geprüft oder erweitert werden, ohne den Crawler-Code selbst
zu verändern.

```text
Desktop-UI (engine.py / engine_desktop.py)
  │
  ├─ erzeugt Laufkonfiguration und Stop-Markierung
  │
  ▼
crawler/crawler.py --config <JSON> --stop-file <Marker>
  │
  ├─ lädt Kataloge aus crawler/config/
  ├─ führt Offline-Selbsttests aus
  ├─ crawlt und schreibt den wiederaufnehmbaren SQLite-Zustand
  ├─ aktualisiert Status und Tiefen-Heatmap
  └─ exportiert den gefilterten Suchkorpus als crawl.jsonl
```

## Zuständigkeiten der Dateien

| Pfad | Aufgabe |
|---|---|
| `engine.py` | Einheitliche Tkinter-Oberfläche, Konfiguration, Prozessstart, geordneter Stopp, Live-Dashboard und Viewer-Integration. |
| `engine_desktop.py` | Kompatibler Startweg für dieselbe Oberfläche. |
| `crawler/crawler.py` | Ausführbare Runtime mit CLI, Validierung, Scheduler, Abruf, Extraktion, Persistenz und Export. |
| `crawler/crawler.ipynb` | Historische Referenz; kein durch die Desktop-App ausgeführter Laufweg. |
| `crawler/config/sources.json` | Basisquellen, erweiterte Quellen und bekannte Lizenzzuordnungen pro Site. |
| `crawler/config/seed_extensions.json` | Zusätzliche Seeds zu bestehenden Quellengruppen. |
| `crawler/config/subject_aliases.json` | Fachnamen und ihre Aliasbegriffe für die Fachfilterung. |

Der derzeitige, im Repository getestete Katalogstand umfasst 150
Quellengruppen, 406 Seeds, 228 freigegebene Hostnamen sowie 17 Fächer mit 99
Aliasbegriffen. Das sind Katalogzahlen, kein Nachweis für die aktuelle
Erreichbarkeit der Server.

## Start und Übergabe der Laufkonfiguration

### Desktop-Start

```powershell
python engine.py
```

Alternativ startet `python engine_desktop.py` dieselbe Oberfläche. Vor dem
Crawl validiert die UI den Laufnamen und die Einstellungen. Anschließend
serialisiert `crawl_config_payload()` unter anderem Profil, Seiten- und
Zeitlimits, Workerzahl, Fachfilter, DFS-Werte sowie Crawl-Optionen in:

```text
crawler/.didadex_config_<RUN_NAME>.json
```

Die Engine entfernt eine eventuell vorhandene Stop-Markierung und startet dann
genau diesen Prozess:

```text
crawler.py --config <Laufkonfiguration> --stop-file <Stop-Markierung>
```

Der Crawler liest die JSON-Datei ein, prüft Werte wie Modus, Tiefen- und
Seed-Runden-Grenzen und übernimmt nur bekannte Fächer aus dem Alias-Katalog.
Nach Ende des Prozesses entfernt die Engine sowohl die temporäre
Laufkonfiguration als auch die Stop-Markierung. Beide Dateimuster stehen in
`.gitignore` und gehören nicht in Commits.

Die Laufzeit wird im Desktop als Auswahl angeboten: 5, 10 oder 30 Minuten für
Kurztests sowie ganze Stunden von 1 bis **60 h**. Die Engine serialisiert den
gewählten Wert aus Kompatibilitätsgründen weiterhin als `runtime_minutes`.
Die Profile setzen beim Wechsel nur ihre Standardwerte (TEST: 10 min,
STANDARD: 3 h, NACHT: 12 h); `NACHT` ist kein festes 720-Minuten-Limit.
Auch direkte Konfigurationen dürfen höchstens 3.600 Minuten enthalten.

### Direkter Start

```powershell
python crawler/crawler.py
```

Ohne `--config` verwendet der Crawler das TEST-Standardprofil. Für
automatisierte oder reproduzierbare Läufe kann eine eigene JSON-Datei mit
`--config` angegeben werden; `--stop-file` ist der Schnittstellenweg für einen
geordneten externen Stopp. Für `profile.runtime_minutes` gilt ebenfalls die
Obergrenze von 3.600 Minuten (60 Stunden).

## Ablauf der Pipeline

1. **Laufkonfiguration und Kataloge laden.** Die Runtime lädt die drei
   JSON-Kataloge, leitet daraus die Seed-Liste, Host-Allowlist und
   Quellenzuordnung ab und prüft die Laufparameter.
2. **Offline-Selbsttests.** Vor dem Netzlauf prüfen kleine lokale Tests
   Klassifikation, Materiallink-Erkennung, URL-Normalisierung,
   Tiefenbegrenzung und Metadatenextraktion. Diese Phase stellt keine
   Erreichbarkeit eines Bildungsservers fest.
3. **Laufordner und Resume-Zustand öffnen.** Die Ausgabe liegt unter
   `crawler/outputs/runs/<RUN_NAME>/`. `crawler_state.sqlite` wird mit WAL
   geöffnet; vorhandene Frontier-, Dokument- und Scheduler-Zustände bleiben
   erhalten. Beim Neustart werden zuvor als `running` markierte URLs wieder
   als `queued` behandelt.
4. **Seeds und Frontier verarbeiten.** Der Scheduler arbeitet die kuratierten
   Seeds in Round-Robin-Runden ab und bevorzugt innerhalb einer Runde tiefere
   Links. Die genaue DFS-Logik und ihre Parameter sind in
   [crawling_strategy.md](crawling_strategy.md) beschrieben.
5. **Abruf begrenzen und navigieren.** Der Crawler beachtet Host-Allowlist,
   `robots.txt`, Crawl-Delays, Host- und Queue-Grenzen, Redirect-Prüfungen,
   Tiefengrenzen und – sofern aktiv – begrenzte Sitemap-Hinweise. Er folgt
   standardmäßig nicht quellenübergreifend zu einem anderen Host.
6. **Extrahieren und indexieren.** HTML und unterstützte Materialtypen werden
   analysiert. URL- und Inhalts-Deduplizierung, Fachfilter,
   Relevanz-/Qualitätsregeln und Lizenzoptionen entscheiden, ob ein Text als
   Dokument in die SQLite-Datenbank aufgenommen wird. Materiallinks allein
   bedeuten nicht, dass eine Binärdatei gespeichert wurde.
7. **Laufdaten aktualisieren.** Während des Crawls entstehen
   `progress.log`, die technische Statusdatei `crawler_live.json` und die
   Tiefen-Heatmap. Das Dashboard liest diese Daten lesend; es greift nicht in
   den Crawlerzustand ein.
8. **Beenden und exportieren.** Bei normalem Ende, einem gesetzten
   Stop-Marker, Zeit-/Seitenlimits oder einer internen Zielkorpusgrenze endet
   der Workerpool geordnet. Anschließend exportiert die Runtime die bis dahin
   akzeptierten Dokumente.

## Fortschritt bei zuvor zurückgestellten Seiten

Offene, zulässige und einem Seed zugeordnete URLs bleiben in der persistenten
Frontier. Sie werden in späteren Round-Robin-Runden mit wachsender
Tiefengrenze erneut berücksichtigt, statt nach einer ersten flachen Runde
liegen zu bleiben. Vollständig abgearbeitet werden sie, sofern keine
Laufzeit-, Seiten-, Queue-, Host-, `robots.txt`-, Relevanz- oder Tiefengrenze
greift. Das ist ausdrücklich kein Anspruch, das offene Web oder jede Seite
eines Hosts vollständig zu crawlen.

**Beobachteter Testlauf:** Mit 10 Workern wurden in fünf Minuten rund
**2,5 MiB** Korpusdaten gesammelt. Dieser Wert beschreibt die konkrete
Testkonfiguration und ihre zu diesem Zeitpunkt erreichbaren Quellen; er ist
kein garantierter Durchsatz und keine Zusage für andere Host-Mischungen.

## Geordneter Stopp und Fortsetzung

Die Schaltfläche **Sauber stoppen und exportieren** legt
`crawler/.didadex_stop_<RUN_NAME>` an. Ein Watcher der Runtime prüft diese
Markierung ungefähr alle 0,3 Sekunden, lässt laufende Arbeit kontrolliert
abschließen und führt anschließend den Export aus.

Ein erneuter Lauf mit derselben `RUN_NAME` setzt auf der vorhandenen
`crawler_state.sqlite` auf. Eine neue Kennung erzeugt einen getrennten
Laufordner. Vor Änderungen an einem bestehenden Lauf oder einem Wechsel auf
eine ältere Crawler-Version sollten die Datenbank und zugehörige WAL-Dateien
gesichert werden. Zwei parallele Crawler dürfen nicht denselben Laufnamen
verwenden.

## Ausgabe eines Laufs

| Artefakt | Bedeutung |
|---|---|
| `crawler_state.sqlite` | Wiederaufnehmbarer technischer Zustand: Frontier, Scheduler, Dokumente und weitere Laufdaten. |
| `crawl.jsonl` | Finaler Suchkorpus mit akzeptierten, deduplizierten Dokumenten. Er enthält nicht jede abgerufene URL. |
| `progress.log` | Fortlaufendes Crawler-Protokoll. |
| `crawler_live.json` | Kleine Statusdatei für das Live-Dashboard, ohne Volltexte. |
| `depth_heatmap.html`, `.json`, `.tsv` | Persistierte Auswertung nach Host und Crawling-Tiefe. |
| `materials/` | Optional gespeicherte Materialdateien, falls die Laufoptionen und Prüfungen dies zulassen. |

Der Export schreibt `crawl.jsonl` atomar über eine temporäre Datei und
begrenzt die Abgabedatei auf das eingestellte Zielvolumen. Das Ziel von 500 MiB
ist eine Obergrenze für den Export, keine Garantie, dass genügend akzeptierte
Dokumente erreicht werden. Alte redundante Exportformate desselben Laufordners
werden beim aktuellen Export entfernt; der SQLite-Resume-Zustand bleibt
erhalten.

## Validierungsgrenze dieser Umstellung

Die Umstellung wurde lokal mit Syntax-/Importprüfungen, Katalogvergleich und
den Offline-Tests unter `tests/` geprüft. Dabei wurden weder ein echter
Netzcrawl noch Durchsatz oder die Erreichbarkeit einzelner Bildungsserver
validiert. Ein produktiver Lauf muss weiterhin `robots.txt`,
Nutzungsbedingungen, Lizenz- und Datenschutzanforderungen beachten.
