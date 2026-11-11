# Zielgröße, Messung, Interpretation

## Hochrechnung des bisherigen Programms

Live-Screenshot der ursprünglichen DidaDex-GUI, 11.11.2026 ca. 16:27:

- 11.156 abgearbeitet
- 618 indexiert
- 9,55 MiB Korpus
- 65.111 offen
- 2.495 Fehler
- 227 Hosts

Rechnerische Ausbeute: `9,55 / 11.156 = 0,000856 MiB` je abgearbeiteter URL, entsprechend ca. **65 MiB** nach insgesamt 76.267 URLs bei stabiler Rate. 300 MiB benötigen ca. **350.500 Abrufe** insgesamt, 500 MiB ca. **584.100 Abrufe** insgesamt, wenn nichts optimiert wird. Das sind Extrapolationen, keine Laufgarantien.

## Wesentliche Qualitätsfragen

1. Wie viele Antworten haben HTTP 200, wie viele 403, 404, 429?
2. Erzeugt eine fertige Unterrichtsmaterialseite Text oder fast nur Navigation?
3. Werden DOCX, PPTX, ODT und PDFs wirklich im **Textindex** gespeichert?
4. Werden Sitemap-Folgeseiten gefunden und Filter-Parameter nicht entfernt?
5. Werden irrelevante Inhalte als `education_content` akzeptiert? Nicht gleichwertig mit `teaching_activity`.
6. Wie viele pro Host entdeckt, geladen, indexiert und wie viel extrahierter Text?
7. Stammt der Größenzuwachs von echten Inhalten oder von repetitivem Boilerplate? Stichproben manuell prüfen.

## Was das neue Programm berichtet

Mit `python crawler.py status` oder in `data/report.json`:

- `text_corpus_mib`: nur die UTF-8-Bytes im Feld `text`
- `queue_states`: pending, blocked, skipped, error, done
- `top_reasons`: hostbezogene Gründe, z.B. HTTP 403, 404, 429, robots, too short
- `by_source`: Anzahl und MiB der extrahierten Texte je Quellengruppe

Die ursprüngliche DidaDex-GUI und die separate Erweiterung besitzen **andere** Zähler. Daher Zahlen nicht ohne genaue Definition unmittelbar vergleichen. Für das IR-Seminar zählt am Ende der JSONL-Korpus im geforderten Schema.

## Mögliche Risiken im Langzeitlauf

- Sehr dynamische Seiten / JavaScript: bei reinem `requests`/BeautifulSoup ist deren Text unter Umständen nicht vorhanden.
- Login/geschützte Inhalte werden nicht extrahiert.
- `robots.txt` oder Websiteschutz kann URLs ausschließen: dies ist zu respektieren.
- Ein langes HTML-Verzeichnis kann sehr viele Navigationseinträge erzeugen: `--max-links-page 90` und Pfadfilter begrenzen das.
- Bei großen PDFs werden bis zu 100 Seiten extrahiert, je Dokument maximal 600.000 Textzeichen; die vollständige binäre PDF-Datei wird nicht gespeichert.
- Der SQLite-Korpus und der JSONL-Export benötigen parallel Plattenplatz. Für 500 MiB Text mindestens ca. 2–3 GiB freien Platz einplanen (je nach Metadaten, WAL und temporärem Export).
- Bei einer unbeaufsichtigten Ausführung den Computer vor dem Energiesparmodus schützen und Disk-Speicher beobachten.
- Textseitige Klassifikationen sind heuristisch; `teaching_activity`, `education_content`, `reference_article` müssen stichprobenartig bewertet werden.

## Verbindung zur ursprünglichen DidaDex-Oberfläche

Die Original-GUI liegt **nicht vor**, weshalb eine direkte Einbettung mit dem bestehenden Live-Monitor, Materialviewer, den GUI-Einstellungen und dem Original-Datenbankschema nicht seriös testbar ist. Die JSONL-Ausgabe kann aber bei Bedarf in die vorhandene Indexierung importiert werden. `merge_existing.py` vereinigt eine exportierte alte Sammlung und eine neue.
