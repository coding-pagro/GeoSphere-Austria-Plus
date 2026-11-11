# INCA v2 gegen den NWP-Fallback

Für den Pilotlauf am 11. November 2026 gingen die Antworten für vier gemeinsame Abrufe um
13:06, 13:09, 13:12 und 13:13 Uhr MEZ ein. Jeder Abruf umfasst dieselben
[25 TAWES-Standorte](stations.json). Die Auswertung verwendet die beim Abruf gespeicherten
Modellwerte und die am jeweiligen Standort gemessenen TAWES-Referenzwerte.

| Feld | Nutzbar NWP | Nutzbar INCA | Vergleichbare Fälle | MAE NWP | MAE INCA |
|---|---:|---:|---:|---:|---:|
| Temperatur | 100/100 | 100/100 | 48 | 1,64 °C | 0,86 °C |
| Niederschlag | 100/100 | 100/100 | 0 | — | — |

Bei beiden Feldern war die INCA-Analyse zwischen 66,4 und 73,4 Minuten alt, mit einem
Median von 71,0 Minuten. In diesen vier Läufen gab es bei den beiden Kandidatenquellen
keine Rasterlücken, fehlenden Werte oder Abruffehler.

## Temperatur

INCA lag in den 48 vergleichbaren Fällen im Mittel näher an TAWES. Für die übrigen
52 Fälle fehlte eine zeitlich passende Temperaturreferenz. Alle Abrufe erfassten
dieselbe INCA-Analyse. Der NWP-Fallback bleibt vorerst die Quelle für aktuelle
Temperaturwerte ohne Stationsmessung. Ein breiterer Vergleich über verschiedene
Wetterlagen und Analysealter kann zeigen, ob sich der beobachtete Vorteil wiederholt.

## Niederschlag

Der NWP-Zeitschritt endete in allen 100 Fällen um 13:00 Uhr MEZ. Die jüngste verfügbare
INCA-Stundensumme endete um 12:00 Uhr MEZ. Mengenfehler, Treffer, übersehene Ereignisse
und Fehlalarme sind für diese Stichprobe daher nicht berechenbar. Der NWP-Fallback
bleibt die Quelle für aktuelle Niederschlagswerte ohne Stationsmessung.

## Referenz und Fortsetzung

Die Unabhängigkeit der TAWES-Referenz von INCA ist für alle 25 Standorte unbelegt.
GeoSphere verwendet Stationsbeobachtungen als Eingabe für die Analyse. Für Standorte
zwischen Stationen fehlt damit eine unabhängige Validierung.
[GeoSphere DataHub – INCA v2](https://data.hub.geosphere.at/dataset/inca-v2-1h-1km)

Der [Forecast-Logger](README.md) plant weitere Abrufe in drei Phasen der Stunde.
Die Auswertung lässt sich mit `analyze.py --data-dir <datenordner> --inca` wiederholen.
