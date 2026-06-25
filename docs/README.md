# Integration Docs

Dokumentation zur Anbindung externer Hardware (ESP32 + Sensoren) an den OPC-UA Server.

## Inhalt

| Dokument                                   | Beschreibung                                             |
|--------------------------------------------|----------------------------------------------------------|
| [esp32-wifi-http.md](esp32-wifi-http.md)   | **Empfohlen** — ESP32 sendet JSON via WiFi HTTP POST     |
| [esp32-mqtt.md](esp32-mqtt.md)             | Produktionsreif — ESP32 → Mosquitto MQTT → OPC-UA Bridge |
| [esp32-serial.md](esp32-serial.md)         | Kabelgebunden — ESP32 Serial USB → Python Bridge         |
| [sensors-vehicle.md](sensors-vehicle.md)   | Sensorauswahl für Fahrzeugsensoren                       |

## Vergleich

|                     | A — WiFi/HTTP    | B — WiFi/MQTT      | C — Serial/USB   |
|---------------------|------------------|--------------------|------------------|
| Aufwand             | Gering           | Mittel             | Gering           |
| Netzwerk            | WiFi             | WiFi               | keins            |
| Offline-Pufferung   | Nein             | Ja (QoS)           | Nein             |
| Mehrere ESP32       | Möglich          | Ideal              | Nein             |
| Stack-Änderung      | +1 HTTP-Endpoint | +Mosquitto +Bridge | +pyserial Script |
| Produktionstauglich | Eingeschränkt    | Ja                 | Nein             |

## Datenfluss (alle Optionen)

![Architekturübersicht — alle drei Integrationswege](diagrams/architecture-overview.svg)

```plaintext
ESP32 + Sensoren
      │
      │  (A) HTTP POST JSON
      │  (B) MQTT publish
      │  (C) Serial JSON
      ▼
OPC-UA Server (opcua-server:4840)
      │  node.write_value()
      ▼
Prometheus Exporter → Prometheus → Grafana
```

## Voraussetzungen

- Arduino IDE oder PlatformIO
- ESP32-Board (z. B. ESP32-DevKitC, WROOM-32)
- Bibliotheken: `ArduinoJson`, `WiFi`, `HTTPClient` (alle im Arduino Board Manager / Library Manager)
