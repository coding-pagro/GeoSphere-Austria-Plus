# Forecast-Log: Nowcast vs. NWP vs. Messung

Sammelt über Tage und Wochen Prognosen von GeoSphere (Nowcast, NWP) und die tatsächlichen
TAWES-Messungen, damit sich später belegen lässt, welches Modell wann näher an der Realität liegt.
Hintergrund: Die Prognosen sind über die API nicht rückwirkend abrufbar, Vergleiche müssen also
„vorwärts“ aufgezeichnet werden.

Gehört nicht zur Integration (liegt nicht in `custom_components/`, wird nicht ausgeliefert).
Nur Python-Standardbibliothek.

## Was gesammelt wird

Pro Lauf **eine** Datei `data/JJJJ/MM/TT/run_HHMM.json.gz` (ca. 5 KiB, rund 4 MB pro Monat bei
stündlichen Läufen) mit

| Inhalt | Quelle | Umfang |
|---|---|---|
| Nowcast | `nowcast-v1-15min-1km`: `t2m` (Temperatur), `rr` (Niederschlag) | alle Schritte, ca. 3 h voraus |
| NWP | `nwp-v2-1h-1km`: `2t`, `tp` | aktuelle Stunde + 6 h |
| Messungen | `tawes-v1-10min`: `TL`, `RR` | letzte 12 h |

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
  Messungen jedes Laufs die letzten 12 Stunden überlappen. Der Lauf schlägt nur fehl (E-Mail von
  GitHub), wenn gar nichts gesammelt werden konnte.
* **Pünktlichkeit:** GitHub startet geplante Läufe oft verspätet und lässt viele ganz ausfallen
  (Okt./Nov. 2026: 3 bis 5 Läufe pro Tag statt 24). Für verlässlich stündliche Läufe den Workflow
  von außen über die API starten (`workflow_dispatch`), etwa per Home-Assistant-Automation:

  ```yaml
  # configuration.yaml
  rest_command:
    forecast_log_dispatch:
      url: https://api.github.com/repos/coding-pagro/GeoSphere-Austria-Plus/actions/workflows/forecast-log.yml/dispatches
      method: POST
      headers:
        Authorization: !secret github_forecast_log_token
        Accept: application/vnd.github+json
        X-GitHub-Api-Version: "2022-11-28"
      payload: '{"ref":"main"}'
      content_type: application/json
  ```

  `github_forecast_log_token` in `secrets.yaml` als `"Bearer github_pat_…"`: ein Fine-grained Token
  nur für dieses Repository mit der Berechtigung *Actions: Read and write*. Die Automation ruft
  `rest_command.forecast_log_dispatch` stündlich zur Minute 7 auf. Der Zeitplan im Workflow bleibt
  als Rückfall aktiv; `concurrency` verhindert parallele Läufe.
* **Abschaltung:** GitHub deaktiviert Zeitpläne in öffentlichen Repositories nach 60 Tagen ohne
  Aktivität. Bei einem aktiven Repo unwahrscheinlich; sonst unter *Actions* wieder einschalten.
* **Beenden:** Workflow-Datei löschen oder unter *Actions* deaktivieren. Der Branch `forecast-data`
  kann danach gelöscht werden.
