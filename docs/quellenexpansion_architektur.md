# Architektur und Priorisierung der Bildungsportale

Recherche- und Abgleichstand: 11.11.2026. Die 39 gezielt hinzugefügten Portaleinstiege wurden durch Websuche und öffentliche Seitentexte überprüft, **nicht** im Paket live durch den neuen Crawler ausgeführt. URL-Kandidaten können zur Laufzeit 404/403 liefern.

| Quelle | Nachgewiesene Einstiegsstruktur | Crawler-Entscheidung |
|---|---|---|
| **bpb** | Materialsuche (`/lernen/materialsuche/`), Themenblätter (`/shop/materialien/themenblaetter/`), Thema im Unterricht, Themen und Materialien; `robots.txt` nennt einen XML-Sitemapindex. | Relevante Bereiche `/lernen/` und `/shop/materialien/`; optionale explizite Sitemap. Keine bpb-Suche `/search/`, Login, Admin. |
| **ZUM-Unterrichten** | `Kategorie:Unterrichtsidee` listet über 400 Seiten und erfordert Fortsetzung durch Pagination. Daneben `Kategorie:Methode`, `Kategorie:Lernpfad`, `Informatik/Unterrichtsideen`. | Kategorielinks mit `pagefrom`/`title` in Query behalten, `/wiki/` und `/index.php` zulassen, Materiallinks bevorzugen. |
| **segu Geschichte** | `/lernmodule/` enthält Module nach Epoche, `/arbeitsblaetter/` listet PDFs/ODTs. Materialien explizit OER CC BY-SA 4.0. | Tiefer in Modul-Einzelseiten, herunterladbare editierbare Materialien in Text umwandeln. |
| **inf-schule** | Startseite verlinkt viele Kapitel zu Algorithmen, Datenbanksystemen, Automaten & Sprachen, Kryptologie und Digitaltechnik. | Ganzen fachlich kuratierten Host mit mehreren fokussierten Einstiegen ablaufen; Text von Unterseiten indexieren. |
| **Lehrerfortbildung BW** | Informatik Gymnasium Bildungsplan 2016 und IMP `fb1/fb2` bieten Hintergrundtexte, Unterrichte und Materialpakete. | `/u_matnatech/` indexieren, PDFs/DOCX lesen. Große ZIP-Archive nur optional nach manueller Lizenzprüfung lokal auslesen. |
| **Bildungsserver Berlin-Brandenburg** | Informatikmaterial nach Themen/Lernjahren, Geschichtsdidaktik inklusive historische Karten und Urteilsbildung. | Konkrete Fachportalseiten statt nur Startseite. |
| **Landesbildungsserver BW** | Geschichte: Unterrichtsmodule nach Klassen, Epochen, Methoden, Didaktik, Originalquellen. | Drei gezielte Einstiege mit Pfadfilter für den Geschichtsbereich. |
| **Digital Learning Lab** | `/unterrichtsbausteine` | Unterrichtsbausteine statt Homepage. |
| **Medien in die Schule** | `/unterrichtseinheiten` und `/downloads` | Unterrichtseinheiten und Downloadmaterial. |
| **Umwelt im Unterricht** | `/unterrichtsvorschlaege`, `/materialien` | Zwei Materialpfade, auch für Methoden/Pädagogik. |
| **Zusätzliche ursprüngliche Hosts** | 270 gültige URLs aus `Seed-Runde 1` (mit 227 Hosts) aus deinem Log. | 258 der URLs sind gegenüber den fokussierten Quellen neu, niedrigere Priorität; Legacy-Sitemaps werden gezielt limitiert, um keine flächendeckenden Massencrawls anzustoßen. |
| **Wikipedia (de)** | 5 × 50 thematische Lemmata, `de.wikipedia.org/wiki/...`. | Zusätzliche Referenzartikel, Tiefe 0, 1 Abruf gleichzeitig, 4 Sekunden Hostabstand. KEIN pauschaler Wikipedia-Vollcrawl. |

## Quellen / überprüfte Adressen

- https://www.bpb.de/robots.txt
- https://www.bpb.de/lernen/materialsuche/
- https://www.bpb.de/shop/materialien/themenblaetter/
- https://www.bpb.de/shop/materialien/thema-im-unterricht/
- https://unterrichten.zum.de/wiki/Kategorie:Unterrichtsidee
- https://unterrichten.zum.de/wiki/Kategorie:Methode
- https://segu-geschichte.de/lernmodule/
- https://segu-geschichte.de/arbeitsblaetter/
- https://inf-schule.de/
- https://lehrerfortbildung-bw.de/u_matnatech/informatik/gym/bp2016/fb2/
- https://lehrerfortbildung-bw.de/u_matnatech/imp/gym/bp2016/fb2/z_download/
- https://bildungsserver.berlin-brandenburg.de/unterricht/faecher/mathematik-naturwissenschaften/informatik/unterrichtsmaterialien-und-fachthemen
- https://bildungsserver.berlin-brandenburg.de/unterricht/faecher/gesellschaftswissenschaften/geschichte/didaktik-1
- https://www.schule-bw.de/faecher-und-schularten/gesellschaftswissenschaftliche-und-philosophische-faecher/geschichte/unterrichtsmaterialien/index.html
- https://www.mediawiki.org/wiki/Wikimedia_APIs/Rate_limits
- https://foundation.wikimedia.org/wiki/Policy:Wikimedia_Foundation_User-Agent_Policy

## Warum nicht einfach noch mehr Seeds?

Ein Seed ist nur eine URL, keine garantierte Menge an Lehrmaterialien. Qualität hängt maßgeblich von der Extraktion der **Unterseiten** ab. 250 Wikipedia-Lemmata können einige MiB zusätzlich liefern, aber 300–500 MiB hochwertigen Lehrmaterials wahrscheinlich nicht allein erreichen. XML-Sitemaps und Materialarchive liefern potenziell mehr URLs bzw. Text. Es ist sinnvoller, die Indexierung pro Host zu analysieren, bevor man einzelne Webseiten mit hohen Request-Raten belastet.
