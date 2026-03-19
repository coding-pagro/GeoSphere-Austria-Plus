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

| Modell-ID | Beschreibung |
|---|---|
| `nwp-v1-1h-2500m` | Numerische Wettervorhersage, 1h-Auflösung, 2,5 km Gitter (Standard) |
| `ensemble-v1-1h-2500m` | Ensemble-Vorhersage, 1h-Auflösung, 2,5 km |
| `nowcast-v1-15min-1km` | Nowcast, 15 min-Auflösung, 1 km (kurze Vorhersagen) |

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
| 11150 | Salzburg Flughafen |
| 11101 | Innsbruck Flughafen |
| 11240 | Graz Flughafen |
| 11010 | Bregenz |
| 11060 | Klagenfurt Flughafen |
| 11190 | Linz / Hörsching |

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
