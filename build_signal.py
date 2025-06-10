from bosdyn.api import signals_pb2, alerts_pb2

doodle_mac_address_spec = signals_pb2.SignalSpec()
doodle_mac_address_spec.info.name = 'doodle_mac_address'
doodle_mac_address_spec.info.description = 'Doodle MAC'
doodle_mac_address_spec.info.order = 0
doodle_mac_address_spec.sensor.resolution.value = 1
doodle_mac_address_spec.sensor.units.name = ""

doodle_battery_spec = signals_pb2.SignalSpec()
doodle_battery_spec.info.name = 'doodle_battery'
doodle_battery_spec.info.description = 'Doodle Battery'
doodle_battery_spec.info.order = 1
doodle_battery_spec.sensor.resolution.value = 1
doodle_battery_spec.sensor.units.name = "%"

DOODLE_MAC_ADDRESS = "MAC"
DOODLE_BATTERY_PERCENTAGE = "Battery"

def build_signals(battery_percentage, mac_address):
    mac_signal = signals_pb2.Signal()
    mac_signal.signal_spec.CopyFrom(doodle_mac_address_spec)
    mac_signal.signal_data.data.string = mac_address

    battery_signal = signals_pb2.Signal()
    battery_signal.signal_spec.CopyFrom(doodle_battery_spec)
    battery_signal.signal_data.data.int = int(battery_percentage)


    return {
        DOODLE_MAC_ADDRESS: mac_signal,
        DOODLE_BATTERY_PERCENTAGE: battery_signal
    }