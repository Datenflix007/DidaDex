# DidaDex – Round-Robin-DFS pro Seed (11.11.2026)

## Ziel und Ausgangspunkt

Der vorherige Scheduler wählte aus der globalen Frontier mit `ORDER BY depth ASC` zunächst Seiten geringerer Tiefe. Bei einer langen Seed-Liste dominierten deshalb Tiefe-0-Seiten. Die neue Implementierung führt einen **begrenzten Tiefendurchlauf pro Seed und Runde** aus. Klassifikations- und Fachheuristiken, die extrahierten Felder, die kuratierte Seed-Liste sowie URL-Normalisierung und Hash-basierte Dokument-IDs sind unverändert.

## Genaues Verhalten

1. Jeder Seed bekommt eine persistente `root_seed`-Zuordnung in SQLite. Wenn mehrere Seeds dieselbe kanonische URL referenzieren, entscheidet die erste Einfügung – die URL wird **nicht zweimal** abgerufen.
2. Die Worker wählen Seeds nach der geringsten Zahl bereits vergebener Runden (`seed_schedule.turns`); bei Gleichstand gilt die Reihenfolge der Seed-Liste. Bei aktivierter fairer Host-Verteilung werden gleichzeitig genutzte Seed-Hosts nach Möglichkeit vermieden. Innerhalb eines Seeds arbeitet **maximal ein Worker**.
3. Pro Seed-Runde werden maximal `pages_per_seed_turn` URLs abgearbeitet. **Innerhalb der Runde** wird die tiefste aktuell wartende URL gewählt (`ORDER BY depth DESC, priority DESC, rowid DESC`). Dies ist eine priorisierte DFS-ähnliche *LIFO*-Frontier; keine rekursive Funktionsaufruf-DFS.
4. Die Tiefengrenze steigt von `DFS_DEPTH_STEP` über `2 × DFS_DEPTH_STEP` usw. bis `min(PROFILE['max_depth'], DEPTH_HARD_LIMIT)`. Bereits besuchte URLs werden **nicht** erneut besucht – daher handelt es sich nicht um klassisches Iterative Deepening DFS mit redundanten Wiederholungen.
5. Nach der Runde wird der Seed freigegeben; der nächste Seed erhält sein Budget. Sobald alle Seeds einmal an der Reihe waren, beginnt die nächste Runde. Neue untergeordnete Seiten behalten ihre `root_seed`-Zuordnung. Auch Sitemaps werden einem kuratierten Seed zugeordnet, erzeugen also nicht tausende zusätzliche Seed-Warteschlangen.
6. SQLite behält seine bisherigen Frontier-Zustände `queued`, `running`, `done`, `blocked`, `error`. Beim Neustart wird `running` wieder zu `queued`, um unterbrochene Anfragen nachzuholen; erledigte URLs werden nicht neu eingeplant. Die Anzahl begonnener Seed-Runden bleibt erhalten.

**Das ist ein Scheduling-Ansatz**, kein Garantieverfahren für relevante Ergebnisse. Tiefe 50 ist nur eine obere Grenze, nicht das Ziel jeder URL. Der existierende adaptive Tiefenfilter kann irrelevante Zweige weiterhin vorher abschneiden.

## Einstellbare Parameter

| Modus | Standardlaufzeit | Seiten pro Seed-Runde (`pages_per_seed_turn`) | Tiefenschritt (`DFS_DEPTH_STEP`) | Worker aus bestehendem Profil |
|---|---:|---:|---:|---:|
| `TEST` | 10 min | 15 | 5 | 5 |
| `STANDARD` | 3 h | 50 | 5 | 6 |
| `NACHT` | 12 h | 100 | 5 | 8 |

**Crawler-Laufzeit:** `crawler/crawler.py` ist die kanonische Ausführungsdatei. Der Desktop übergibt Profil und DFS-Werte als kleine Laufkonfigurations-JSON; `crawler/crawler.ipynb` wird dafür nicht mehr verwendet.

**Python-Desktop:** `python engine.py` starten (oder `python engine_desktop.py` als Kompatibilitätsstarter). Im Tab „Crawler“ gibt es zusätzlich die Felder **DFS: Seiten pro Seed-Runde** und **Tiefenschritt pro Runde**. Die vereinheitlichte Engine übergibt diese Werte direkt an `crawler.py`.

**Laufzeit-Auswahl:** Neben den kurzen Testwerten 5, 10 und 30 Minuten bietet die Oberfläche ganze Stunden von 1 bis **60 h**. `NACHT` startet weiterhin mit 12 h, ist aber kein 720-Minuten-Hardlimit. Die Runtime akzeptiert auch direkte Laufkonfigurationen bis 3.600 Minuten und weist höhere Werte zurück.

Empfehlung: Mit `TEST`, 15 Seiten/Seed und Tiefenschritt 5 beginnen. Mehr Worker sind nicht automatisch schneller: `robots.txt`, Host-Pausen, langsame Server und heruntergeladene Materialien können begrenzen.

## Reichweite und Durchsatz ab dem nächsten Lauf

- Die URL-Deduplizierung bleibt slashlos, aber ein Redirect-Ziel mit bedeutungsvollem abschließendem Slash wird korrekt abgerufen. Echte Redirect-Zyklen werden nach der ersten Wiederholung beendet.
- Beim Fortsetzen eines alten Laufs werden ausschließlich frühere Fehler `too_many_redirects` einmal wieder in die Warteschlange gestellt. Das betrifft die frühere Slash-Fehlbehandlung; neue echte Zyklen erhalten einen anderen Fehlergrund. Vorher die SQLite-Datei samt WAL/SHM sichern.
- Quellübergreifende Navigation ist jetzt standardmäßig aus. Alle kuratierten Seeds werden weiterhin gecrawlt; die Desktop-Option **Freigegebene Hosts verbinden (optional)** kann sie gezielt wieder aktivieren. Das schützt die Warteschlange vor einem einzelnen sehr großen Host.
- Der Crawler folgt zusätzlich höchstens vier `Sitemap:`-Angaben aus einer erlaubten `robots.txt` desselben Hosts. `robots.txt`, Host-Allowlist und die vorhandenen Sitemap-Limits bleiben dabei verbindlich.
- Die Tiefen-Heatmap wird höchstens im eingestellten Intervall erzeugt und am Ende erzwungen geschrieben. `STORE_CRAWL_EDGES = False` vermeidet standardmäßig die große reine Diagnose-Tabelle; für eine gezielte Graphanalyse kann sie in einer Laufkonfigurations-JSON aktiviert werden.

## Neue SQLite-Felder

Die bestehende Datei `crawler/outputs/runs/<RUN_NAME>/crawler_state.sqlite` wird **automatisch erweitert**:

- `frontier.root_seed`: ursprünglicher Seed, dem diese URL gehört.
- `seed_schedule.root_seed`: eindeutiger Seed-Schlüssel.
- `seed_schedule.ordinal`: Reihenfolge der Seed-Liste.
- `seed_schedule.turns`: bisher vergebene Seed-Runden (beinhaltet eine eventuell unterbrochene Runde).
- `seed_schedule.claimed_pages`: bisher für diesen Seed abgerufene bzw. zum Abruf reservierte Seiten.

Altbestände ohne `root_seed` werden aus Seed-URLs, Parent-Verweisen und – bei fehlenden Redirect-Eltern – dem kuratierten Host zugeordnet. Bei sehr großen älteren Datenbanken kann die einmalige Migration Zeit beanspruchen. **Vor dem Update die komplette Laufdatenbank einschließlich WAL/SHM-Dateien sichern und kein zweites Crawler-Fenster gleichzeitig mit demselben Laufnamen starten.** Ein automatischer Rückbau des Datenbankschemas ist nicht vorgesehen.

## Erfolg kontrollieren

1. Für den ersten Test besser einen **neuen Laufnamen** verwenden, damit Altbestände nicht die Auswertung verfälschen.
2. In `progress.log` erscheinen Zeilen `Seed-Runde N: <URL> | DFS bis Tiefe X, Budget Y Abrufe`.
3. `depth_heatmap.html` zeigt tatsächlich besuchte und indexierte Tiefen getrennt. `crawl.jsonl` enthält **nur akzeptierte Dokumente**, nicht jede besuchte URL.
4. Optional die SQLite-Datenbank mit Python abfragen:

```python
import sqlite3
from pathlib import Path
state = Path('crawler/outputs/runs/MEIN_LAUF/crawler_state.sqlite')
with sqlite3.connect(state) as db:
    print('Besuche je Tiefe:')
    for row in db.execute('SELECT depth, status, count(*) FROM frontier GROUP BY depth,status ORDER BY depth,status'):
        print(row)
    print('Erste Seed-Runden:')
    for row in db.execute('SELECT root_seed, turns, claimed_pages FROM seed_schedule ORDER BY ordinal LIMIT 15'):
        print(row)
```

Das Anwachsen der Zahl an indexierten Dokumenten und der `crawl.jsonl`-Größe ist **nicht** proportional zur Tiefe, denn die bestehenden Qualitäts- und Lizenzfilter entscheiden weiter über die Aufnahme in den Korpus.

## Tests

```powershell
python -m unittest discover -s tests -v
```

Die neuen Tests verwenden synthetische HTML-Seiten ohne Netzwerk: Besuchsreihenfolge, progressive Tiefengrenzen, Host-Fairness, Deduplizierung, Resume sowie automatische Migration einer älteren SQLite-Frontier. Im automatisierten Test ist keine Validierung der Erreichbarkeit realer Bildungsserver enthalten. `robots.txt` und Nutzungsbedingungen müssen bei echten Läufen weiterhin beachtet werden.
