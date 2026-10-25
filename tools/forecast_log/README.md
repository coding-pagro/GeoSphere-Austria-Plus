# Forecast-Log: Nowcast vs. NWP vs. Messung

Sammelt über Tage und Wochen Prognosen von GeoSphere (Nowcast, NWP) und die tatsächlichen
TAWES-Messungen, damit sich später belegen lässt, welches Modell wann näher an der Realität liegt.
Hintergrund: Die Prognosen sind über die API nicht rückwirkend abrufbar, Vergleiche müssen also
„vorwärts“ aufgezeichnet werden.

Gehört nicht zur Integration (liegt nicht in `custom_components/`, wird nicht ausgeliefert).
Nur Python-Standardbibliothek.

## Was gesammelt wird

Pro Lauf **eine** Datei `data/JJJJ/MM/TT/run_HHMM.json.gz` (ca. 3 KiB, rund 2 bis 3 MB pro Monat bei
stündlichen Läufen) mit

| Inhalt | Quelle | Umfang |
|---|---|---|
| Nowcast | `nowcast-v1-15min-1km`: `t2m` (Temperatur), `rr` (Niederschlag) | alle Schritte, ca. 3 h voraus |
| NWP | `nwp-v2-1h-1km`: `2t`, `tp` | aktuelle Stunde + 6 h |
| Messungen | `tawes-v1-10min`: `TL`, `RR` | letzte ca. 2 h |

für 25 Stationen (`stations.json`): gleichmäßig über die Höhe von 116 m bis 3437 m verteilt, dazu
die Station des Users (11389, St. Pölten Landhaus). Neue Liste erzeugen:
`python forecast_log.py init-stations --n 40`. Pro Lauf sind es nur **3 API-Abfragen**.

## Auswerten

```bash
python tools/forecast_log/analyze.py --data-dir <ordner-mit-den-daten>
```

Die Auswertung vergleicht ausschließlich Prognosen mit Messungen, die **nach** dem Abruf entstanden
sind. Ausgegeben werden:

* **Temperatur** je Modell, Vorlauf und Höhenklasse: Fehler roh, „angeglichen“ (letzte Messung +
  Modelltrend) und Persistenz („bleibt wie jetzt“).
* **Niederschlag** als Stundensumme: mittlerer Fehler, Bias sowie Trefferquote (POD),
  Fehlalarmquote (FAR) und CSI für Ereignisse ab 0,1 mm/h.

Annahmen: TAWES-Zeitstempel bezeichnen das Ende des 10-Minuten-Intervalls, Prognose-Niederschlag gilt
für das Intervall, das am Zeitstempel endet. Sollte der Nowcast-Bias beim Niederschlag auffällig
ein Vielfaches betragen, ist `rr` vermutlich eine Rate in mm/h statt einer Summe je 15 min.

## Lokal laufen lassen

```bash
python tools/forecast_log/forecast_log.py collect --data-dir data
```

Funktioniert nur, solange der Rechner an ist. Dauerhaft ohne PC:

## Ohne PC: GitHub Actions

`.github/workflows/forecast-log.yml` startet den Lauf stündlich (Minute 7) auf GitHubs Servern und
speichert die Dateien auf dem Branch `forecast-data` (wird beim ersten Lauf angelegt, `main` bleibt
unberührt). In öffentlichen Repositories ist das kostenlos.

1. Workflow-Datei muss auf `main` liegen (Zeitpläne laufen nur vom Standard-Branch).
2. Einmal manuell starten: *Actions → Forecast log → Run workflow*.
3. Daten abholen:

   ```bash
   git fetch origin forecast-data
   git worktree add ../forecast-data origin/forecast-data
   python tools/forecast_log/analyze.py --data-dir ../forecast-data
   ```

Zu beachten:

* **Rate-Limit:** GeoSphere begrenzt Abfragen. GitHub-Server teilen sich IP-Adressen mit vielen
  anderen Nutzern, einzelne Läufe können daher mit „API rate limit exceeded“ scheitern. Das Skript
  wiederholt vier Mal mit Pausen; Lücken in den Daten sind danach möglich, aber unkritisch, weil die
  Messungen jedes Laufs die letzten 2 Stunden überlappen. Der Lauf schlägt nur fehl (E-Mail von
  GitHub), wenn gar nichts gesammelt werden konnte.
* **Pünktlichkeit:** Geplante Läufe starten bei GitHub oft einige Minuten zu spät.
* **Abschaltung:** GitHub deaktiviert Zeitpläne in öffentlichen Repositories nach 60 Tagen ohne
  Aktivität. Bei einem aktiven Repo unwahrscheinlich; sonst unter *Actions* wieder einschalten.
* **Beenden:** Workflow-Datei löschen oder unter *Actions* deaktivieren. Der Branch `forecast-data`
  kann danach gelöscht werden.
