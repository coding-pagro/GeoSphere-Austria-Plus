# GeoSphere Austria Plus

Custom Integration für Home Assistant mit vollständiger **Wetterbedingungen (Conditions)** und **Vorhersage (Forecast)** Unterstützung – basierend auf dem öffentlichen [GeoSphere Austria DataHub API](https://dataset.api.hub.geosphere.at/).

> Die offizielle `zamg`-Integration liefert weder Conditions noch Forecasts. Diese Integration schließt beide Lücken.

---

## Features

| Feature | Status |
|---|---|
| Aktuelle Temperatur, Feuchte, Druck, Wind | ✅ |
| **Wetterbedingungen (condition)** | ✅ neu |
| **Stündliche Vorhersage (hourly forecast)** | ✅ neu |
| **Tägliche Vorhersage (daily forecast)** | ✅ neu |
| Vorhersagemodell wählbar | ✅ |
| Keine API-Key erforderlich | ✅ |

### Unterstützte Vorhersagemodelle

| Modell-ID | Auflösung | Zeitraum | Beschreibung |
|---|---|---|---|
| `nwp-v1-1h-2500m` | 1 h / 2,5 km | ~48–72 h | **Numerische Wettervorhersage (Standard).** Physikalisches Atmosphärenmodell – gute Gesamtgenauigkeit für Temperatur, Wind und Niederschlag. |
| `ensemble-v1-1h-2500m` | 1 h / 2,5 km | ~48–72 h | **Ensemble-Vorhersage.** Dasselbe Modell, mehrfach mit leicht unterschiedlichen Startwerten gerechnet. Robuster als ein einzelner NWP-Lauf, glättet aber Extremereignisse ab. |
| `nowcast-v1-15min-1km` | 15 min / 1 km | 2–3 h | **Nowcast.** Keine Modellrechnung, sondern Radarextrapolation – aktuell gemessene Niederschlagszellen werden fortgeschrieben. Sehr präzise für unmittelbar bevorstehenden Regen oder Gewitter, danach rapider Qualitätsverlust. |

**Empfehlung:** Für den Alltagseinsatz empfiehlt sich **NWP** (Standard). **Ensemble** liefert verlässlichere Tendenzen mit weniger Ausreißern. **Nowcast** ist sinnvoll, wenn es primär darum geht, ob es in den nächsten 1–2 Stunden regnet.

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
| TAWES-Stations-ID | Numerische ID deiner nächsten Wetterstation | `11035` (Wien/Hohe Warte) |
| Vorhersagemodell | Eines der drei oben genannten Modelle | `nwp-v1-1h-2500m` |

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

Die Condition wird aus den TAWES-Echtzeitdaten abgeleitet:

| Priorität | Bedingung | Quelle |
|---|---|---|
| 1 | `pouring` (Starkregen) | RR > 1 mm/10min |
| 2 | `rainy` (Regen) | RR > 0,2 mm/10min |
| 3 | `snowy-rainy` (Schneeregen) | SH > 0 + RR > 0 |
| 4 | `snowy` (Schnee) | SH > 0,1 cm |
| 5 | `fog` (Nebel) | RF > 97 % + FF < 2 m/s |
| 6 | `cloudy` / `windy-variant` | SO < 12,5 % der möglichen Sonnenscheindauer |
| 7 | `partlycloudy` | SO < 50 % |
| 8 | `windy` | FF > 10 m/s |
| 9 | `sunny` / `clear-night` | Default |

Für die **Vorhersage** werden Wolkenbedeckung (`tcc`), Niederschlag (`rain_acc`, `snow_acc`) und Wind aus dem NWP-Modell verwendet.

---

## Lizenz

Die GeoSphere Austria API-Daten stehen unter [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).

Der Code dieser Integration steht unter der MIT-Lizenz.
