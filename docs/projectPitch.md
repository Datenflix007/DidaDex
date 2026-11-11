# DidaDex – Der Index für guten Unterricht

**Eine methodisch-didaktische Suchmaschine für Unterrichtsideen, Methoden und Materialien**  
*Information Retrieval · Semesterprojekt · Stand: 11. November 2026*

> **Nicht einfach nach Unterrichtsmaterial googeln – sondern gezielt finden, was im Unterricht funktioniert.**

## 1. Die Idee

Lehrkräfte suchen bei der Unterrichtsvorbereitung häufig nicht nur Informationen zu einem Thema. Sie suchen nach einer **konkreten Idee für eine bestimmte Unterrichtssituation**: einem motivierenden Einstieg, einer geeigneten Methode für die Erarbeitungsphase, einem differenzierten Arbeitsauftrag oder einer kurzen Reflexion am Stundenende.

Allgemeine Suchmaschinen liefern dazu oft eine Mischung aus Portalseiten, theoretischen Fachtexten, Werbung und verstreuten Materialien. **DidaDex** soll diese Suche fokussieren: Wir entwickeln eine Suchmaschine, die öffentlich zugängliche Unterrichtsideen und Materialien **unter methodisch-didaktischen Gesichtspunkten erschließt** und auffindbar macht.

**Unser Leitgedanke:** Nicht nur *Worum geht es?*, sondern vor allem *Wie lässt sich das im Unterricht einsetzen?*

## 2. Eine beispielhafte Suchanfrage

**„Einstieg Klimawandel, 8. Klasse, 10 Minuten, ohne digitale Geräte“**

Statt einer allgemeinen Themenübersicht soll DidaDex möglichst konkrete Vorschläge mit folgenden Angaben anzeigen:

- **Unterrichtsidee und Kurzbeschreibung:** Was machen die Lernenden?
- **Fach und Jahrgangsstufe:** Für wen ist das Material geeignet?
- **Unterrichtsphase und Methode:** Einstieg, Erarbeitung, Sicherung oder Reflexion?
- **Dauer und Sozialform:** Passt die Idee in die verfügbare Zeit?
- **Voraussetzungen und Materialien:** Was wird für die Umsetzung benötigt?
- **Direktlink zur Originalquelle:** Wo ist die vollständige Idee beziehungsweise das Material erreichbar?

Fehlende Angaben werden als **unbekannt** gekennzeichnet und nicht erfunden.

## 3. Für wen ist DidaDex gedacht?

DidaDex richtet sich vor allem an **Lehramtsstudierende, Lehrkräfte im Vorbereitungsdienst und praktizierende Lehrkräfte**. Die Suche soll sowohl für fachbezogene als auch für methodische Fragen nützlich sein, beispielsweise:

- „Rollenspiel zur Weimarer Republik in Klasse 9“
- „ER-Diagramme anschaulich einführen“
- „Sicherung nach Gruppenarbeit in fünf Minuten“
- „Quellenanalyse mit differenzierten Arbeitsaufträgen“

## 4. Was unterscheidet DidaDex von einer gewöhnlichen Suche?

**DidaDex sucht nach didaktischer Einsetzbarkeit statt nur nach passenden Schlagwörtern.** Dafür unterscheiden wir zwischen drei Ebenen:

1. **Unterrichtsinhalte:** Aufgabenstellungen, Lernziele, methodische Hinweise, Ablaufbeschreibungen und Materiallinks.
2. **Didaktische Metadaten:** Fach, Klassenstufe, Unterrichtsphase, Methode, Sozialform, Dauer, Voraussetzungen und Lizenzangaben – soweit vorhanden.
3. **Suchrelevanz:** Konkrete Unterrichtsideen und Aufgaben sollen stärker gewichtet werden als bloße Portalseiten oder Linksammlungen.

DidaDex ist dabei **kein Generator für automatisch erfundene Unterrichtsentwürfe**, sondern zunächst eine **quellenbasierte Suchmaschine**, die vorhandene Angebote gezielt erschließt und zur Originalquelle führt.

## 5. Woher stammen die Daten?

Wir beginnen mit ausgewählten Bildungs- und OER-Angeboten, insbesondere **ZUM-Unterrichten** und der **OER-Sammlung von edulabs**. Perspektivisch können weitere öffentliche Bildungsserver der deutschen Bundesländer, bundesweite Bildungsplattformen und geeignete internationale Angebote folgen – besonders mit Blick auf Informatik und Medienbildung.

Wichtig ist uns, **bis zu den eigentlichen Material- und Unterrichtsdetailseiten vorzudringen**. Übersichten und Kategorien können dem Crawler als Wegweiser dienen, müssen aber nicht selbst als Suchtreffer erscheinen.

Wir beachten technische Zugriffsregeln, `robots.txt`, Nutzungsbedingungen, Urheber- und Lizenzhinweise sowie den Datenschutz. **Crawlen bedeutet nicht automatisch, dass Inhalte selbst weiterveröffentlicht werden dürfen.**

## 6. Wie funktioniert DidaDex technisch?

```text
Ausgewählte Bildungsplattformen (Seed-URLs)
                 ↓
      Kontrollierter Web-Crawler
  (Domainregeln, robots.txt, Limits)
                 ↓
    Extraktion der Unterrichtsinhalte
  (Text, Aufgaben, Methoden, Metadaten)
                 ↓
     Qualitätsfilter und Deduplikation
  (Landingpages erkennen, URL-/Inhaltshash)
                 ↓
         Strukturierter Datenkorpus
              (z. B. JSONL)
                 ↓
       Suchindex und Ranking (BM25)
                 ↓
       DidaDex-Suchoberfläche
       (Treffer, Filter, Quellen)
```

**Technischer Kern des Semesterprojekts:** Crawling, Information Extraction, Datenbereinigung, Indexierung und Retrieval. Ein späterer Ausbau um Synonymerkennung oder semantische Suche ist denkbar, aber nicht Voraussetzung für die erste Version.

## 7. Was wollen wir im Semester erreichen?

Unser Ziel ist ein **funktionsfähiger Prototyp** mit einem Korpus von ungefähr **500 MB**. Dabei müssen Rohdaten, bereinigte Dokumente und Indexgröße klar getrennt ausgewiesen werden: Die Datenmenge allein ist kein Qualitätskriterium.

Der erste Prototyp soll:

- fach- und methodenbezogene Suchanfragen mittels **BM25-Volltextsuche** unterstützen,
- Treffer mit **Titel, Textausschnitt, Quellenlink und vorhandenen Metadaten** anzeigen,
- soweit die Datenlage es erlaubt, nach **Fach, Schulstufe, Unterrichtsphase und Methode** filtern,
- ungeeignete Seiten, redundante Inhalte und Duplikate möglichst zuverlässig aussortieren.

Wir prüfen die Qualität anhand typischer Suchanfragen und einer **manuellen Bewertung der Treffer** – etwa mit *Precision@5*, dem Anteil relevanter Ergebnisse unter den ersten fünf Treffern.

## 8. Der Projektpitch in 45 Sekunden

> **DidaDex – Der Index für guten Unterricht.**
>
> Wer Unterricht plant, sucht häufig nicht bloß Informationen, sondern konkrete Ideen: Wie gelingt ein Einstieg? Welche Methode passt zu einer Lerngruppe? Wo finde ich ein geeignetes Arbeitsblatt?
>
> Genau hier setzt DidaDex an. Wir entwickeln eine methodisch-didaktische Suchmaschine, die öffentlich zugängliche Unterrichtsideen und Materialien aus Bildungsplattformen sammelt, strukturiert erschließt und gezielt durchsuchbar macht. Im Mittelpunkt stehen nicht allgemeine Portalseiten, sondern konkrete Aufgaben, Unterrichtsabläufe und Methoden – möglichst mit Angaben zu Fach, Klassenstufe, Unterrichtsphase und Dauer.
>
> Technisch verbinden wir dafür Web-Crawling, Datenextraktion und Qualitätsfilter mit einem Suchindex. Unser Ziel im Information-Retrieval-Semester ist ein funktionierender Prototyp, der zeigt, ob Lehrkräfte dadurch schneller zu passenden Unterrichtsideen gelangen.

---

**Kurzclaim:** *DidaDex – Finden, was Unterricht weiterbringt.*

**Ausgangspunkte:** [ZUM-Unterrichten](https://unterrichten.zum.de/wiki/Unterrichtsideen) · [edulabs OER](https://edulabs.de/oer/)
