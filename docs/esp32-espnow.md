# Option D — ESP-NOW Multi-Node

**Empfohlen für:** mehrere ESP32s im Fahrzeug, kurze Sensor-Kabel, kein WLAN-Router nötig.

Sensor-Nodes senden ihre Messwerte per ESP-NOW (Espressifs P2P-Protokoll) an einen Gateway-ESP32.
Der Gateway aggregiert alle Werte und schickt alle 2 s einen HTTP POST an den OPC-UA Server.

## Architektur

![Option D — ESP-NOW Multi-Node](diagrams/esp32-espnow.svg)

**Vorteile gegenüber WiFi-Optionen:**
- Kein WLAN-Router zwischen den Nodes nötig
- ~1 ms Latenz, bis zu 20 Sensor-Nodes
- ESP-NOW und WiFi laufen gleichzeitig auf demselben Gateway-Chip
- Reichweite ~30–50 m im Fahrzeug (Metall dämpft, Freifeld bis ~200 m)

---

## 1. MAC-Adresse des Gateways ermitteln

Diesen Sketch einmal auf den Gateway-ESP32 flashen und die MAC-Adresse notieren:

```cpp
#include <WiFi.h>

void setup() {
    Serial.begin(115200);
    WiFi.mode(WIFI_STA);
    Serial.println("Gateway MAC: " + WiFi.macAddress());
}

void loop() {}
```

Ausgabe: `Gateway MAC: AA:BB:CC:DD:EE:FF` — diese Adresse in den Sensor-Node Sketches eintragen.

---

## 2. Sensor-Node Sketch

Jeder Sensor-Node sendet eine `sensor_msg_t`-Struct an den Gateway. Nur die Felder belegen,
die der Node tatsächlich misst — alle anderen bleiben `0.0`.

```cpp
#include <WiFi.h>
#include <esp_now.h>
#include <ArduinoJson.h>

// ── Gateway MAC-Adresse eintragen ────────────────────────────────────────────
uint8_t GATEWAY_MAC[] = {0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF};

// ── Payload-Struct (muss auf Gateway identisch sein) ─────────────────────────
typedef struct sensor_msg {
    char  node_id[8];           // "node_a", "node_b", "node_c"
    float Speed_kmh;
    float RPM;
    float EngineTemperature_C;
    float FuelLevel_pct;
    float OilPressure_bar;
    float BatteryVoltage_V;
    float TirePressure_bar;
    int   ActiveFaultCount;
} sensor_msg_t;

sensor_msg_t msg;
esp_now_peer_info_t peerInfo;

void onSent(const uint8_t *mac, esp_now_send_status_t status) {
    Serial.printf("ESP-NOW send: %s\n",
        status == ESP_NOW_SEND_SUCCESS ? "OK" : "FAIL");
}

// ── Sensor-spezifisch: Hall RPM + DS18B20 (Node A) ───────────────────────────
#include <OneWire.h>
#include <DallasTemperature.h>

#define RPM_PIN  34
#define TEMP_PIN 32

volatile uint32_t pulseCount = 0;
unsigned long lastCalc = 0;
OneWire oneWire(TEMP_PIN);
DallasTemperature tempSensor(&oneWire);

void IRAM_ATTR onPulse() { pulseCount++; }

void setup() {
    Serial.begin(115200);

    // Sensoren
    tempSensor.begin();
    pinMode(RPM_PIN, INPUT_PULLUP);
    attachInterrupt(digitalPinToInterrupt(RPM_PIN), onPulse, RISING);

    // ESP-NOW initialisieren
    WiFi.mode(WIFI_STA);
    if (esp_now_init() != ESP_OK) {
        Serial.println("ESP-NOW init failed");
        return;
    }
    esp_now_register_send_cb(onSent);

    memcpy(peerInfo.peer_addr, GATEWAY_MAC, 6);
    peerInfo.channel = 0;
    peerInfo.encrypt = false;
    esp_now_add_peer(&peerInfo);

    // Node-ID setzen
    strncpy(msg.node_id, "node_a", sizeof(msg.node_id));
}

void loop() {
    unsigned long now = millis();
    float elapsed = (now - lastCalc) / 1000.0f;
    lastCalc = now;

    // RPM berechnen (4-Takt: 2 Impulse/Umdrehung)
    uint32_t p = pulseCount;
    pulseCount  = 0;
    msg.RPM     = (p / elapsed) * 60.0f / 2.0f;

    // Kühlwassertemperatur
    tempSensor.requestTemperatures();
    msg.EngineTemperature_C = tempSensor.getTempCByIndex(0);

    // Nicht gemessene Felder auf 0 lassen
    msg.Speed_kmh        = 0.0f;
    msg.FuelLevel_pct    = 0.0f;
    msg.OilPressure_bar  = 0.0f;
    msg.BatteryVoltage_V = 0.0f;
    msg.TirePressure_bar = 0.0f;
    msg.ActiveFaultCount = 0;

    esp_now_send(GATEWAY_MAC, (uint8_t *)&msg, sizeof(msg));
    Serial.printf("TX node_a: RPM=%.0f Temp=%.1f\n", msg.RPM, msg.EngineTemperature_C);

    delay(2000);
}
```

**Für Node B / Node C** nur `node_id`, die gemessenen Felder und die Sensor-Initialisierung anpassen.

---

## 3. Gateway Sketch

Der Gateway empfängt die Pakete aller Nodes, merged die Werte und schickt alle 2 s
einen HTTP POST an den OPC-UA Server.

```cpp
#include <WiFi.h>
#include <esp_now.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <map>

// ── Konfiguration ────────────────────────────────────────────────────────────
const char* WIFI_SSID  = "DEIN-WLAN";
const char* WIFI_PASS  = "DEIN-PASSWORT";
const char* SERVER_URL = "http://192.168.1.100:4841/sensor";  // IP anpassen
const int   SEND_INTERVAL_MS = 2000;

// ── Payload-Struct (identisch zu Sensor-Nodes) ───────────────────────────────
typedef struct sensor_msg {
    char  node_id[8];
    float Speed_kmh;
    float RPM;
    float EngineTemperature_C;
    float FuelLevel_pct;
    float OilPressure_bar;
    float BatteryVoltage_V;
    float TirePressure_bar;
    int   ActiveFaultCount;
} sensor_msg_t;

// ── Aggregierte Werte (letzter bekannter Wert pro Node) ──────────────────────
std::map<String, float> agg = {
    {"Speed_kmh", 0}, {"RPM", 0}, {"EngineTemperature_C", 0},
    {"FuelLevel_pct", 0}, {"OilPressure_bar", 0}, {"BatteryVoltage_V", 0},
    {"TirePressure_bar", 0}, {"ActiveFaultCount", 0}
};
portMUX_TYPE aggMux = portMUX_INITIALIZER_UNLOCKED;

// ── ESP-NOW Callback ─────────────────────────────────────────────────────────
void onReceive(const esp_now_recv_info_t *info, const uint8_t *data, int len) {
    if (len != sizeof(sensor_msg_t)) return;
    sensor_msg_t msg;
    memcpy(&msg, data, sizeof(msg));

    portENTER_CRITICAL(&aggMux);
    if (msg.RPM              > 0) agg["RPM"]                 = msg.RPM;
    if (msg.Speed_kmh        > 0) agg["Speed_kmh"]           = msg.Speed_kmh;
    if (msg.EngineTemperature_C > 0) agg["EngineTemperature_C"] = msg.EngineTemperature_C;
    if (msg.FuelLevel_pct    > 0) agg["FuelLevel_pct"]       = msg.FuelLevel_pct;
    if (msg.OilPressure_bar  > 0) agg["OilPressure_bar"]     = msg.OilPressure_bar;
    if (msg.BatteryVoltage_V > 0) agg["BatteryVoltage_V"]    = msg.BatteryVoltage_V;
    if (msg.TirePressure_bar > 0) agg["TirePressure_bar"]    = msg.TirePressure_bar;
    if (msg.ActiveFaultCount > 0) agg["ActiveFaultCount"]    = msg.ActiveFaultCount;
    portEXIT_CRITICAL(&aggMux);

    Serial.printf("RX from %s: RPM=%.0f Temp=%.1f\n",
        msg.node_id, msg.RPM, msg.EngineTemperature_C);
}

void setup() {
    Serial.begin(115200);

    // WiFi verbinden (für HTTP POST zum Server)
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASS);
    Serial.print("WiFi connecting");
    while (WiFi.status() != WL_CONNECTED) { delay(500); Serial.print("."); }
    Serial.println("\nIP: " + WiFi.localIP().toString());

    // ESP-NOW initialisieren (läuft parallel zu WiFi)
    if (esp_now_init() != ESP_OK) {
        Serial.println("ESP-NOW init failed");
        return;
    }
    esp_now_register_recv_cb(onReceive);
    Serial.println("Gateway ready — waiting for sensor nodes");
}

void loop() {
    if (WiFi.status() != WL_CONNECTED) { WiFi.reconnect(); delay(500); return; }

    // JSON aus aggregierten Werten bauen
    JsonDocument doc;
    portENTER_CRITICAL(&aggMux);
    for (auto& kv : agg) doc[kv.first] = kv.second;
    portEXIT_CRITICAL(&aggMux);

    String body;
    serializeJson(doc, body);

    HTTPClient http;
    http.begin(SERVER_URL);
    http.addHeader("Content-Type", "application/json");
    http.setTimeout(1500);
    int code = http.POST(body);
    Serial.printf("POST %d: %s\n", code, http.getString().c_str());
    http.end();

    delay(SEND_INTERVAL_MS);
}
```

---

## 4. Bibliotheken (Arduino Library Manager)

| Bibliothek | Zweck |
|---|---|
| `ArduinoJson` by Benoit Blanchon (≥ v7) | JSON-Serialisierung |
| `DallasTemperature` + `OneWire` | DS18B20 (Node A) |
| `esp_now.h` | Im ESP32 Board Package enthalten |
| `WiFi.h` / `HTTPClient.h` | Im ESP32 Board Package enthalten |

ESP32 Board Package: **≥ 2.0** (Arduino IDE → Boards Manager → `esp32` by Espressif).

---

## 5. Testen ohne zweiten ESP32

Gateway bereits mit WiFi verbunden, noch kein Sensor-Node vorhanden:

```bash
# Direkt einen Wert simulieren
curl -X POST http://localhost:4841/sensor \
  -H "Content-Type: application/json" \
  -d '{"RPM": 2400, "EngineTemperature_C": 82.3, "OilPressure_bar": 3.1}'
```

Sobald Sensor-Nodes dazukommen, erscheinen deren Werte automatisch im Serial Monitor
des Gateways und fließen in den nächsten HTTP POST ein.

---

## Rebuild (nur bei Server-Änderungen nötig)

```bash
docker compose up -d --build opcua-server
```
