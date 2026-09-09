# Entwicklung

Diese Anleitung beschreibt, wie eine lokale Entwicklungsumgebung aufgesetzt wird,
in der **Tests und Typprüfung dieselben Ergebnisse liefern wie die CI**.

---

## Voraussetzungen

| Anforderung | Version | Warum |
|---|---|---|
| Python | **≥ 3.13.2** | Home Assistant setzt `Requires-Python >= 3.13.2`. Mit älterem Python schlägt das Setup fehl — siehe [Stolperfallen](#stolperfallen). |
| git | beliebig | — |

Python-Version prüfen:

```bash
python --version
```

Meldet der Befehl 3.12 oder älter, zuerst ein aktuelles Python installieren.
Ohne das funktioniert der Rest dieser Anleitung nicht.

---

## Setup

```bash
# 1. Virtuelle Umgebung anlegen und aktivieren
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 2. Test- und Lint-Abhängigkeiten
pip install -r requirements_test.txt

# 3. Home Assistant NUR als Typquelle installieren (Version ist gepinnt)
pip install --no-deps -r requirements_typing.txt
```

Danach laufen beide Prüfungen lokal:

```bash
# Tests
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest tests/ -p asyncio -p pytest_cov

# Typprüfung (strict)
mypy custom_components/geosphere_austria_plus
```

Erwartet: alle Tests grün, mypy meldet `Success: no issues found`.

---

## Warum `--no-deps`?

Das ist der wichtigste Schritt — und der am leichtesten falsch gemachte.

Für `mypy` muss Home Assistant **nicht lauffähig** sein. Gebraucht werden nur die
getypten Quelldateien und der `py.typed`-Marker, den das Paket mitliefert. Das
Home-Assistant-Wheel ist plattformunabhängig (`py3-none-any`, reines Python), also
genügt `--no-deps`:

- kein Compiler, keine plattformspezifischen Wheels, funktioniert auch unter Windows
- rund hundert Transitivabhängigkeiten entfallen, die für die Typprüfung nichts beitragen
- deutlich schnellere Installation

Die Version ist in `requirements_typing.txt` exakt gepinnt, damit die strict-Prüfung
lokal und in der CI gegen dieselbe Typoberfläche läuft. Dependabot hebt den Pin
automatisch an. Home Assistant steht bewusst **nicht** in `requirements_test.txt`:
ein `pip install -r` würde dort die vollen Abhängigkeiten ziehen — pip unterstützt
`--no-deps` nicht innerhalb einer Requirements-Datei.

Die Testsuite wird davon nicht beeinflusst: `tests/conftest.py` injiziert seine
Home-Assistant-Mocks unbedingt über `sys.modules.update()`, bevor Integrationscode
importiert wird. Ein real installiertes — und mangels Abhängigkeiten nicht
lauffähiges — Home Assistant wird dabei überschrieben und nie importiert.

---

## Stolperfallen

| Symptom | Ursache | Lösung |
|---|---|---|
| `pip install homeassistant` bricht mit `Failed building wheel for PyRIC` ab | Lokales Python ist älter als 3.13.2. pip findet keine aktuelle Home-Assistant-Version und fällt still auf eine mehrere Jahre alte zurück, die eine nicht mehr baubare Abhängigkeit zieht. | Python ≥ 3.13.2 installieren. |
| mypy meldet dutzendfach `Cannot find implementation or library stub for module named "homeassistant.*"` | Home Assistant ist nicht installiert. | Schritt 3 des Setups ausführen. |
| mypy meldet `Skipping analyzing "homeassistant.*": missing library stubs or py.typed marker` | Eine sehr alte Home-Assistant-Version ist installiert; `py.typed` kam erst später dazu. | `pip install --no-deps --force-reinstall -r requirements_typing.txt` |
| mypy meldet `Invalid syntax; you likely need to run mypy using Python 3.13 or newer` | mypy läuft unter einem älteren Interpreter als dem der virtuellen Umgebung. | mypy innerhalb der aktivierten venv aufrufen. |

---

## Die mypy-Konfiguration nicht aufweichen

`pyproject.toml` fährt bewusst `strict = true` (Ziel: Platinum Quality Scale) und die
CI erzwingt das. Fehlt lokal Home Assistant, erzeugt genau diese Konfiguration
dutzende Fehler — das ist ein **Umgebungsproblem, kein Konfigurationsproblem**.

Der richtige Weg ist, die lokale Umgebung anzugleichen (Schritt 3 des Setups).
Flags wie `ignore_missing_imports` für `homeassistant.*`,
`disallow_subclassing_any = false` oder `warn_unused_ignores = false` beheben die
Symptome lokal, schalten aber gleichzeitig die Prüfung in der CI ab, wo Home
Assistant installiert ist und die Typen real vorliegen. Das Gate meldet dann
weiterhin „grün", prüft aber deutlich weniger.

---

## Tests

Die Testsuite braucht **keine** Home-Assistant-Installation — `tests/conftest.py`
mockt alle benötigten Home-Assistant-Module. Home Assistant wird ausschließlich für
`mypy` installiert, deshalb liegt es in `requirements_typing.txt` statt in
`requirements_test.txt`.

`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` hält die Umgebung deterministisch und entspricht
dem CI-Lauf; `asyncio` und `pytest_cov` müssen deshalb explizit über `-p` geladen
werden.

Coverage-Schwelle liegt bei 80 % (`--cov-fail-under=80`).
