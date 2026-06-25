import asyncio
import logging
import os
from asyncua import Client
from prometheus_client import start_http_server, Gauge

logging.basicConfig(level=logging.INFO)

ENDPOINT        = os.getenv("OPCUA_ENDPOINT", "opc.tcp://opcua-server:4840/vehicle/")
SCRAPE_INTERVAL = int(os.getenv("SCRAPE_INTERVAL", "5"))

METRICS = {
    "Speed_kmh":          Gauge("vehicle_speed_kmh",          "Vehicle speed in km/h"),
    "EngineTemperature_C":Gauge("vehicle_engine_temperature_c","Engine coolant temperature in Celsius"),
    "RPM":                Gauge("vehicle_rpm",                 "Engine revolutions per minute"),
    "FuelLevel_pct":      Gauge("vehicle_fuel_level_pct",      "Fuel tank level in percent"),
    "OilPressure_bar":    Gauge("vehicle_oil_pressure_bar",    "Engine oil pressure in bar"),
    "BatteryVoltage_V":   Gauge("vehicle_battery_voltage_v",   "12V lead-acid battery voltage"),
    "TirePressure_bar":   Gauge("vehicle_tire_pressure_bar",   "Tire pressure in bar"),
    "ActiveFaultCount":   Gauge("vehicle_active_fault_count",  "Number of active faults"),
}


async def scrape():
    while True:
        try:
            async with Client(url=ENDPOINT) as client:
                logging.info("Connected to OPC-UA server at %s", ENDPOINT)
                ns = await client.get_namespace_index("http://demo.vehicle/opcua")
                vehicle = await client.nodes.objects.get_child([f"{ns}:Vehicle"])

                while True:
                    for node_name, gauge in METRICS.items():
                        try:
                            node = await vehicle.get_child(f"{ns}:{node_name}")
                            gauge.set(float(await node.read_value()))
                        except Exception as e:
                            logging.warning("Could not read %s: %s", node_name, e)
                    await asyncio.sleep(SCRAPE_INTERVAL)

        except Exception as e:
            logging.error("Connection failed: %s — retrying in 10s", e)
            await asyncio.sleep(10)


async def main():
    start_http_server(9686)
    logging.info("Prometheus exporter listening on :9686")
    await scrape()


asyncio.run(main())
