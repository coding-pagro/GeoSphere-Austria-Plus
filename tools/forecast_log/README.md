# Forecast-Log

Sammelt über Tage und Wochen Prognosen von GeoSphere (Nowcast, NWP), INCA-Analysen und
TAWES-Messungen. Damit lassen sich Vorhersagen und die Quellen für aktuelle Wetterwerte auswerten.
Hintergrund: Die Prognosen sind über die API nicht rückwirkend abrufbar, Vergleiche müssen also
„vorwärts“ aufgezeichnet werden.

Gehört nicht zur Integration (liegt nicht in `custom_components/`, wird nicht ausgeliefert).
Nur Python-Standardbibliothek.

## Was gesammelt wird

Pro Lauf **eine** Datei `data/JJJJ/MM/TT/run_HHMM.json.gz` (ca. 7 KiB, rund 5 MB pro Monat bei
stündlichen Läufen) mit

| Inhalt | Quelle | Umfang |
|---|---|---|
| Nowcast | `nowcast-v1-15min-1km`: `t2m` (Temperatur), `rr` (Niederschlag) | alle Schritte, ca. 3 h voraus |
| NWP | `nwp-v2-1h-1km`: `2t`, `tp`, `rain`, `sf` | aktuelle Stunde + 6 h; für den INCA-Vergleich ab 2 h vor der aktuellen Stunde |
| INCA | `inca-v2-1h-1km`: `2t`, `tp` | jüngster zurückgelieferter Zeitschritt bis maximal 2 h vor Abruf |
| Messungen | `tawes-v1-10min`: `TL`, `RR` | letzte 12 h |

für 25 Stationen (`stations.json`): gleichmäßig über die Höhe von 116 m bis 3437 m verteilt, dazu
die Station des Users (11389, St. Pölten Landhaus). Neue Liste erzeugen:
`python forecast_log.py init-stations --n 40`. Im Normalfall sind es **4 API-Abfragen** pro Lauf.

## Aktuelle Werte aus INCA und NWP vergleichen

```bash
python tools/forecast_log/analyze.py --data-dir data --inca
```

Die ersten Live-Ergebnisse stehen im [Pilotbericht](INCA_REPORT.md).

Der Logger fragt beide Quellen parallel an denselben Stationskoordinaten ab. Er speichert den gemeinsamen
Erhebungszeitpunkt nach Eingang der Antworten, die Empfangszeit pro Quelle und die ausgewählten Werte mit
Gültigkeitszeit. Wie die NWP-Standardentität von Plus wählt der Logger den ersten Zeitschritt in
API-Reihenfolge, der höchstens eine Stunde zurückliegt. Für INCA verwendet er den jüngsten bereits gültigen
Zeitschritt innerhalb von zwei Stunden wie im Entwurf #69. Die Auswertung liest die gespeicherten
Kandidaten. Aufzeichnungen ohne gleichzeitigen INCA-Abruf fließen nur in die Vorhersageauswertung ein.

- **Temperatur** wird mit der TAWES-Messung am Erhebungszeitpunkt verglichen. Zwischen zwei
  unmittelbar benachbarten 10-Minuten-Messungen wird linear interpoliert.
- **Niederschlag** wird in mm pro Stunde verglichen. Plus verwendet `rain + sf`. Der Logger
  speichert zusätzlich den Entitätswert, der bei Trockenheit leer ist. Für den
  Mengenvergleich zählt eine vollständig beobachtete trockene Stunde als 0 mm. Es zählen
  nur Fälle, in denen das Stundenintervall beider Kandidaten identisch ist und alle sechs
  TAWES-Summen vorliegen. Treffer, übersehene Ereignisse und Fehlalarme beziehen sich auf
  mindestens 0,1 mm pro Stunde. Der angezeigte Fallback gilt für die laufende Stunde, die
  jüngste INCA-Analyse ist beim Abruf aber über eine Stunde alt. Ihre Intervalle stimmen
  daher nie überein. Der Logger fragt die NWP-Zeitreihe deshalb ab zwei Stunden vor der
  laufenden Stunde ab und speichert zusätzlich den NWP-Wert für das INCA-Intervall
  (`precipitation_inca_interval`). Die Fehler beim Niederschlag beruhen auf diesem Wert,
  die Verfügbarkeit auf dem angezeigten Fallback.
- **Nowcast** wird bei jedem Abruf parallel als dritter Kandidat erfasst. Wie die
  Nowcast-Entität von Plus gilt der erste Zeitschritt, der höchstens eine Stunde
  zurückliegt. Die Temperatur vergleicht der Bericht auf den gemeinsamen Fällen aller drei
  Quellen und nach Tageszeit in Ortszeit, weil sich die Verzögerung von INCA vor allem
  morgens und abends auswirkt. Beim Niederschlag fehlt Nowcast. Er liefert 15-Minuten-Summen
  erst ab seinem Referenzzeitpunkt und deckt das zurückliegende INCA-Intervall nicht ab.
- **Verfügbarkeit** und **Analysealter** werden für jedes Feld berichtet. Ein fehlender
  Parameterwert, eine von der API gemeldete Rasterlücke und ein Abruffehler werden
  getrennt gezählt. TAWES-Messungen werden anhand von Stations-ID und Koordinaten zugeordnet.
  Spätere Läufe können fehlende TAWES-Referenzen ergänzen.

TAWES ist die erste Referenz. Stationsbeobachtungen können in INCA einfließen. Der Bericht
weist die Unabhängigkeit je Standort aus. In `stations.json` kann
`inca_independence_source` eine Quelle für belegte Unabhängigkeit enthalten. Beim vorhandenen
Stationssatz ist sie unbelegt. [GeoSphere DataHub – INCA v2](https://data.hub.geosphere.at/dataset/inca-v2-1h-1km)

Die Idee zur INCA-Nutzung stammt von [slettmayer und GeoSphere Austria Next](https://github.com/slettmayer/ha-geosphere-next#entities).

## Vorhersagen auswerten

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

`.github/workflows/forecast-log.yml` plant Läufe zur Minute 7, 27 und 47 auf GitHubs Servern und
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
  anderen Nutzern, einzelne Abrufe können daher mit „API rate limit exceeded“ scheitern.
  Der Vergleich verwendet pro Quelle einen Abrufversuch, damit spätere Antworten nicht mit der
  ursprünglichen Stichprobe vermischt werden. Nowcast, TAWES und das NWP-Vorhersagearchiv werden
  bei temporären Fehlern erneut abgefragt. Lücken in den Messungen sind unkritisch, weil jeder
  Lauf die letzten 12 Stunden abdeckt. Der Lauf schlägt nur fehl (E-Mail von GitHub), wenn gar
  nichts gesammelt werden konnte.
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
  `rest_command.forecast_log_dispatch` stündlich auf. Für den INCA-Vergleich die Minute
  wechseln (etwa 7, 27, 47), damit verschiedene Analysealter vorkommen. Um einen PR-Branch
  auszuwerten, dessen Namen als `ref` eintragen. Der Workflow nutzt dann den Code dieses Branches.
  Der Zeitplan im Workflow bleibt als Rückfall aktiv; `concurrency` verhindert parallele Läufe.
* **Abschaltung:** GitHub deaktiviert Zeitpläne in öffentlichen Repositories nach 60 Tagen ohne
  Aktivität. Bei einem aktiven Repo unwahrscheinlich; sonst unter *Actions* wieder einschalten.
* **Beenden:** Workflow-Datei löschen oder unter *Actions* deaktivieren. Der Branch `forecast-data`
  kann danach gelöscht werden.
