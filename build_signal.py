from bosdyn.api import signals_pb2

doodle_battery_spec = signals_pb2.SignalSpec()
doodle_battery_spec.info.name = '<MAC>'
doodle_battery_spec.info.description = 'Doodle Battery Infomation'
doodle_battery_spec.info.order = 0
doodle_battery_spec.sensor.resolution.value = 1
doodle_battery_spec.sensor.units.name = "%"

def build_signals(stations):
    signals = {}
    for station in stations:
        signal = signals_pb2.Signal()
        signal.signal_spec.CopyFrom(doodle_battery_spec)
        signal.signal_spec.info.name = f"{station['mac_address']}"
        signal.signal_data.data.int = int(station['battery_percentage'])
        signals[station['mac_address']] = signal
    return signals
