import asyncio
import math
import logging
from asyncua import Server

logging.basicConfig(level=logging.INFO)


async def main():
    server = Server()
    await server.init()
    server.set_endpoint("opc.tcp://0.0.0.0:4840/vehicle/")
    server.set_server_name("1974 Oldtimer OPC-UA Server")

    uri = "http://demo.vehicle/opcua"
    idx = await server.register_namespace(uri)

    objects = server.nodes.objects
    vehicle = await objects.add_object(idx, "Vehicle")

    speed           = await vehicle.add_variable(idx, "Speed_kmh",          0.0)
    engine_temp     = await vehicle.add_variable(idx, "EngineTemperature_C", 20.0)
    rpm             = await vehicle.add_variable(idx, "RPM",                 0.0)
    fuel_level      = await vehicle.add_variable(idx, "FuelLevel_pct",       100.0)
    oil_pressure    = await vehicle.add_variable(idx, "OilPressure_bar",     0.0)
    battery_voltage = await vehicle.add_variable(idx, "BatteryVoltage_V",    12.2)
    tire_pressure   = await vehicle.add_variable(idx, "TirePressure_bar",    1.8)
    fault_count     = await vehicle.add_variable(idx, "ActiveFaultCount",    0)

    for node in [speed, engine_temp, rpm, fuel_level,
                 oil_pressure, battery_voltage, tire_pressure, fault_count]:
        await node.set_writable()

    logging.info("1974 Oldtimer OPC-UA Server running on opc.tcp://0.0.0.0:4840")

    async with server:
        t = 0
        fuel = 100.0
        coolant_temp = 20.0   # cold start

        while True:
            await asyncio.sleep(2)
            t += 1

            # ── Speed: 1974 Oldtimer, max ~130 km/h ──────────────────────────
            v_speed = max(0.0, 65 + 55 * math.sin(t * 0.07) + 8 * math.sin(t * 0.28))

            # ── RPM: correlated with speed, carburettor noise ─────────────────
            # Simulate rough gear changes every ~15 ticks
            gear_phase = (t % 15) / 15.0
            gear_spike = 300 * math.exp(-10 * (gear_phase - 0.1) ** 2) if gear_phase < 0.3 else 0
            v_rpm = max(750, 800 + v_speed * 27 + gear_spike
                        + 80 * math.sin(t * 0.45)
                        + 30 * math.sin(t * 1.3))
            v_rpm = min(5500, v_rpm)

            # ── Coolant temperature: cold start, stabilises at ~82 °C ─────────
            target = 82.0 + 5 * math.sin(t * 0.04)
            coolant_temp += (target - coolant_temp) * 0.04
            v_engine_temp = coolant_temp + 2 * math.sin(t * 0.18)

            # ── Fuel: ~10 L/100 km, gauges sloshes on bumps ──────────────────
            fuel = max(0.0, fuel - 0.008)
            v_fuel = max(0.0, fuel + 0.4 * math.sin(t * 0.11))

            # ── Oil pressure: rises with RPM, old pump less efficient ─────────
            v_oil_pressure = max(0.3, 1.6 + (v_rpm / 5500) * 3.1
                                 + 0.12 * math.sin(t * 0.32))

            # ── Battery voltage: 13.8 V while alternator runs ─────────────────
            v_battery_voltage = 13.8 + 0.25 * math.sin(t * 0.06) \
                                - 0.15 * math.sin(t * 0.9)
            v_battery_voltage = max(11.8, v_battery_voltage)

            # ── Tire pressure: vintage cross-ply tyres, ~1.8 bar ─────────────
            v_tire_pressure = 1.8 + 0.04 * math.sin(t * 0.025)

            # ── Faults: carburettor hiccup every ~5 min ───────────────────────
            v_fault_count = 1 if t % 150 == 0 else 0

            await speed.write_value(round(v_speed, 2))
            await engine_temp.write_value(round(v_engine_temp, 2))
            await rpm.write_value(round(v_rpm, 0))
            await fuel_level.write_value(round(v_fuel, 2))
            await oil_pressure.write_value(round(v_oil_pressure, 2))
            await battery_voltage.write_value(round(v_battery_voltage, 2))
            await tire_pressure.write_value(round(v_tire_pressure, 3))
            await fault_count.write_value(v_fault_count)


asyncio.run(main())
