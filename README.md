# GeoSphere Austria Plus

Custom Integration für Home Assistant mit vollständiger **Wetterbedingungen (Conditions)** und **Vorhersage (Forecast)** Unterstützung – basierend auf dem öffentlichen [GeoSphere Austria DataHub API](https://dataset.api.hub.geosphere.at/).

> Die offizielle `zamg`-Integration liefert weder Conditions noch Forecasts. Diese Integration schließt beide Lücken.

---

## Features

| Feature | Status |
|---|---|
| **11 TAWES-Sensoren** (Temperatur, Feuchte, Druck, Wind, …) | ✅ |
| **Wetterbedingungen (condition)** | ✅ |
| **Stündliche Vorhersage (hourly forecast, 48 h)** | ✅ |
| **Tägliche Vorhersage (daily forecast, 7 Tage)** | ✅ |
| **Wetterwarnungen (Unwetterwarnungen)** | ✅ |
| **Luftqualitätsindex (NO₂, O₃, PM10, PM2.5 + AQI)** | ✅ |
| 0–3 Vorhersagemodelle pro Station wählbar | ✅ |
| Keine API-Key erforderlich | ✅ |

### TAWES-Sensoren

Die Integration fragt die TAWES-Station alle **10 Minuten** ab – dieselbe Anfrage, die auch die aktuellen Wetterbedingungen liefert. Weil die Rohdaten damit ohnehin vorhanden sind, werden sie als **11 einzelne Sensor-Entitäten** direkt im Gerät exponiert, ohne einen einzigen zusätzlichen API-Call:

| Sensor | Parameter | Einheit |
|---|---|---|
| Temperature | TL | °C |
| Dew Point | TP | °C |
| Humidity | RF | % |
| Wind Direction | DD | ° |
| Wind Speed | FF | m/s |
| Wind Gust | FX | m/s |
| Pressure | P | hPa |
| Pressure (Reduced) | PRED | hPa |
| Precipitation | RR | mm |
| Sunshine Duration | SO | s / 10 min |
| Snow Height | SH | cm |

Alle Sensoren teilen sich dasselbe Gerät (Wetterstation) mit der Wetterentität und stehen sofort in Automationen, Dashboards und dem Energiemanagement zur Verfügung.

> Die TAWES-Station ist optional. Ohne Station werden Temperatur, Feuchte, Windgeschwindigkeit, Windrichtung und Niederschlag aus dem ersten Vorhersagepunkt des gewählten Modells abgeleitet. Taupunkt, Luftdruck und Böen haben kein Modell-Äquivalent und bleiben in diesem Fall leer.

### Wetterwarnungen

Der Warnungs-Sensor zeigt die **höchste aktive Warnstufe** (0 = keine, 1 = gelb, 2 = orange, 3 = rot). Als Attribute werden alle aktiven Warnungen mit Typ, Stufe, Zeitraum, Auswirkungen und Empfehlungen aufgelistet.

Unterstützte Warntypen: Sturm, Regen, Schnee, Glatteeis, Gewitter, Hitze, Kälte.

### Luftqualitätssensoren

Vier stündliche Schadstoffsensoren (NO₂, O₃, PM10, PM2.5 in µg/m³) sowie ein aggregierter **EU-Luftqualitätsindex (AQI, Stufe 1–6)** aus dem GeoSphere Chemie-Modell (`chem-v2-1h-3km`). Jeder Sensor enthält zusätzlich eine 24-Stunden-Vorhersage als Attribut.

| Stufe | Bedeutung |
|---|---|
| 1 | Gut |
| 2 | Mäßig |
| 3 | Empfindlichen Gruppen schädlich |
| 4 | Ungesund |
| 5 | Sehr ungesund |
| 6 | Extrem schlecht |

### Unterstützte Vorhersagemodelle

| Modell-ID | Auflösung | Zeitraum | Beschreibung |
|---|---|---|---|
| `nwp-v1-1h-2500m` | 1 h / 2,5 km | ~48–72 h | **Numerische Wettervorhersage (Standard).** Physikalisches Atmosphärenmodell – gute Gesamtgenauigkeit für Temperatur, Wind und Niederschlag. |
| `ensemble-v1-1h-2500m` | 1 h / 2,5 km | ~48–72 h | **Ensemble-Vorhersage.** Dasselbe Modell, mehrfach mit leicht unterschiedlichen Startwerten gerechnet. Robuster als ein einzelner NWP-Lauf, glättet aber Extremereignisse ab. |
| `nowcast-v1-15min-1km` | 15 min / 1 km | 2–3 h | **Nowcast.** Keine Modellrechnung, sondern Radarextrapolation – aktuell gemessene Niederschlagszellen werden fortgeschrieben. Sehr präzise für unmittelbar bevorstehenden Regen oder Gewitter, danach rapider Qualitätsverlust. Liefert nur stündliche Vorhersage (kein Daily-Forecast). |

**Empfehlung:** Für den Alltagseinsatz empfiehlt sich **NWP** (Standard). **Ensemble** liefert verlässlichere Tendenzen mit weniger Ausreißern. **Nowcast** ist sinnvoll, wenn es primär darum geht, ob es in den nächsten 1–2 Stunden regnet.

Es können auch **0 Modelle** gewählt werden – in diesem Fall wird keine Wetterentität angelegt.

---

## Installation via HACS

1. HACS → Integrationen → `+ Hinzufügen`
2. „Custom repositories" → diese Repo-URL eingeben → Kategorie: Integration
3. „GeoSphere Austria Plus" installieren
4. Home Assistant neu starten
5. Einstellungen → Geräte & Dienste → `+ Integration hinzufügen` → **GeoSphere Austria Plus**

---

## Konfiguration

| Parameter | Beschreibung | Beispiel |
|---|---|---|
| Name | Anzeigename des Geräts | `Wien` |
| Breitengrad | Geografische Breite des Standorts | `48.249` |
| Längengrad | Geografische Länge des Standorts | `16.356` |
| TAWES-Station | Nächste Wetterstation (optional) | `11035` (Wien/Hohe Warte) |
| Vorhersagemodelle | 0–3 Modelle (NWP, Ensemble, Nowcast) | NWP (Standard) |
| Wetterwarnungen | Warnungs-Sensor aktivieren | ✅ (Standard) |
| Luftqualität | Luftqualitäts-Sensoren aktivieren | ✅ (Standard) |

Pro Standort wird **ein Gerät** angelegt. Jedes gewählte Vorhersagemodell erscheint als eigene Wetterentität darunter; die TAWES-Sensoren (sofern Station gewählt), der Warnungs-Sensor und die Luftqualitäts-Sensoren werden einmalig pro Gerät angelegt.

Alle Parameter können nach der Ersteinrichtung über **Einstellungen → Geräte & Dienste → Konfigurieren** geändert werden.

### Wichtige österreichische Stationen

| Station-ID | Name |
|---|---|
| 11035 | Wien / Hohe Warte |
| 11036 | Wien / Schwechat (Flughafen) |
| 11389 | St.Pölten |
| 11190 | Linz / Hörsching |
| 11150 | Salzburg Flughafen |
| 11101 | Innsbruck Flughafen |
| 11240 | Graz Flughafen |
| 11010 | Bregenz |
| 11060 | Klagenfurt Flughafen |

Alle Stations-IDs: https://dataset.api.hub.geosphere.at/v1/station/current/tawes-v1-10min/metadata

---

## Wetterbedingungen (Conditions)

Die Condition wird aus den TAWES-Echtzeitdaten abgeleitet (Priorität höchste zuerst):

| Priorität | Bedingung | Quelle |
|---|---|---|
| 1 | `snowy-rainy` (Schneeregen) | SH > 0,1 cm + RR ≥ 0,2 mm/10min |
| 2 | `pouring` (Starkregen) | RR ≥ 1 mm/10min |
| 3 | `rainy` (Regen) | RR ≥ 0,2 mm/10min |
| 4 | `snowy` (Schnee) | SH > 0,1 cm |
| 5 | `fog` (Nebel) | RF ≥ 97 % + FF < 2 m/s |
| 6 | `cloudy` / `windy-variant` | SO < 12,5 % der möglichen Sonnenscheindauer |
| 7 | `partlycloudy` | SO < 50 % |
| 8 | `windy` | FF ≥ 10 m/s |
| 9 | `sunny` / `clear-night` | Default |

Ist keine TAWES-Station konfiguriert, werden alle aktuellen Werte (Condition, Temperatur, Feuchte, Wind, Niederschlag) aus dem ersten verfügbaren Vorhersagepunkt abgeleitet. Taupunkt, Luftdruck und Böen bleiben leer, da die Modelle diese Größen nicht liefern.

Für die **Vorhersage** werden Wolkenbedeckung (`tcc`), Niederschlag (`rain_acc`, `snow_acc`) und Wind aus dem NWP-Modell verwendet.

---

## Lizenz

Die GeoSphere Austria API-Daten stehen unter [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).

Der Code dieser Integration steht unter der MIT-Lizenz.
