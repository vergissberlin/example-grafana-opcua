# AGENTS.md — Claude Code Context for opc-grafana

This file tells AI coding agents everything they need to work effectively in this repo.

## Project Summary

Local Docker Compose demo of an OPC-UA automotive telemetry pipeline:
`opcua-server` → `opcua-exporter` → `prometheus` → `grafana`

All four services run as containers. There is no build system, no test suite, no CI.

## File Map

```plaintext
compose.yml                  Docker Compose (4 services)
prometheus.yml               Prometheus scrape config
opcua-server/
  server.py                  OPC-UA server — defines nodes + simulation loop
  Dockerfile                 python:3.12-slim + asyncua==1.1.5
opcua-exporter/
  exporter.py                Reads OPC-UA nodes, exposes Prometheus metrics
  Dockerfile                 python:3.12-slim + asyncua==1.1.5 + prometheus-client==0.20.0
```

## Key Patterns

### Adding a new vehicle metric

Touch exactly two files:

**1. `opcua-server/server.py`** — add a variable and write it in the loop:

```python
# in main(), after existing variable declarations:
new_sensor = await vehicle.add_variable(idx, "NewSensor_unit", 0.0)
await new_sensor.set_writable()

# in the while loop:
await new_sensor.write_value(round(some_formula(t), 2))
```

**2. `opcua-exporter/exporter.py`** — add to the METRICS dict:

```python
"NewSensor_unit": Gauge("vehicle_new_sensor_unit", "Description of the metric"),
```

Then rebuild both services:

```bash
docker compose up -d --build opcua-server opcua-exporter
```

### Adding a Grafana panel

Use the Grafana HTTP API (Grafana runs on localhost:3000, credentials admin/admin):

```python
import json, urllib.request, base64

AUTH = base64.b64encode(b"admin:admin").decode()

def api(path, data):
    req = urllib.request.Request(
        f"http://localhost:3000{path}",
        data=json.dumps(data).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Basic {AUTH}"},
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())
```

The datasource UID is `cfq6rbyfcxhq8b` (set during initial provisioning).
Dashboard UID is `automotive-opc-ua-demo`.

To update the dashboard, call `POST /api/dashboards/db` with `"overwrite": true`.

## Simulated Vehicle

Carburettor petrol engine, 12 V lead-acid electrics, cross-ply tyres.
Max speed ~130 km/h. Engine warms up from cold start (~20 °C → 82 °C over ~2 min).
Fuel drains slowly. Gear-change RPM spikes simulated every ~30 s.

## OPC-UA Node Address Space

- Endpoint: `opc.tcp://opcua-server:4840/vehicle/`
- Namespace URI: `http://demo.vehicle/opcua`
- Namespace index: 2 (runtime-assigned, resolved via `get_namespace_index`)
- Node path from Objects: `2:Vehicle / 2:<node-name>`

Current nodes in `Vehicle`:

| Node name              | Type  | Init value | Notes                          |
|------------------------|-------|------------|--------------------------------|
| `Speed_kmh`            | Float | 0.0        | max ~130 km/h                  |
| `RPM`                  | Float | 0.0        | 750 idle – 5500 max            |
| `EngineTemperature_C`  | Float | 20.0       | cold start, stabilises at 82°C |
| `FuelLevel_pct`        | Float | 100.0      | drains ~0.008 % / 2 s          |
| `OilPressure_bar`      | Float | 0.0        | rises with RPM                 |
| `BatteryVoltage_V`     | Float | 12.2       | ~13.8 V while running          |
| `TirePressure_bar`     | Float | 1.8        | vintage cross-ply              |
| `ActiveFaultCount`     | Int32 | 0          | carb hiccup every ~5 min       |
| `GPS_Latitude`         | Float | 48.137     | oval route around Munich       |
| `GPS_Longitude`        | Float | 11.575     | oval route around Munich       |

## Prometheus Metrics

All metrics are Gauges with prefix `vehicle_`. Scraped every 15 s from `opcua-exporter:9686`.

| Metric name                    | Source node            |
|--------------------------------|------------------------|
| `vehicle_speed_kmh`            | `Speed_kmh`            |
| `vehicle_rpm`                  | `RPM`                  |
| `vehicle_engine_temperature_c` | `EngineTemperature_C`  |
| `vehicle_fuel_level_pct`       | `FuelLevel_pct`        |
| `vehicle_oil_pressure_bar`     | `OilPressure_bar`      |
| `vehicle_battery_voltage_v`    | `BatteryVoltage_V`     |
| `vehicle_tire_pressure_bar`    | `TirePressure_bar`     |
| `vehicle_active_fault_count`   | `ActiveFaultCount`     |
| `vehicle_gps_latitude`         | `GPS_Latitude`         |
| `vehicle_gps_longitude`        | `GPS_Longitude`        |

## Service Dependencies

```plaintext
grafana       depends_on  prometheus
prometheus    depends_on  opcua-exporter  (relaxed: changed to opcua-server)
opcua-exporter depends_on opcua-server
```

The exporter retries the OPC-UA connection every 10s — it is safe to start the
full stack with `docker compose up -d` even if services come up out of order.

## Constraints & Gotchas

- `open62541/open62541:latest` is a **library image** (headers + CMake only), not a runnable server.
  The server is our own Python container — do not revert to that image.
- `ghcr.io/ctron/prometheus-opcua-exporter` returns `Bad Gateway` from GHCR — the image no longer
  exists. Use our custom `opcua-exporter/` build.
- The stack runs on **arm64** (Apple Silicon). The open62541 image pulled with a platform warning;
  our Python containers build natively for arm64.
- No Grafana provisioning files are used. Datasource and dashboard were created via the HTTP API
  using `/tmp/create_grafana_dashboard.py`. Grafana state is not persisted across `docker compose down`.
  Re-run the script after a fresh stack start.

## What is NOT in this repo

- Grafana provisioning YAML / dashboard JSON files (dashboard lives only in Grafana's DB)
- Tests
- CI configuration
- Real vehicle data (all sensor values are mathematical simulations)
