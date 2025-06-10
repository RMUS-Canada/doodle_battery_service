import logging

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

from doodle_helper import DoodleHelper


HOST_IP = "10.223.68.37"
USERNAME = "configurator"
PASSWORD = "test"

_LOGGER = logging.getLogger('test_main')

def main():
    doodle_helper = DoodleHelper(HOST_IP, USERNAME, PASSWORD, _LOGGER)
    doodle_helper.login()
    
    # Get all reachable stations with their voltages
    stations = doodle_helper.get_all_reachable_stations()
    
    # Print the results
    for station in stations:
        _LOGGER.info(f"MAC Address: {station['mac_address']}")
        _LOGGER.info(f"IP Address: {station['ip_address']}")
        _LOGGER.info(f"Battery Voltage: {station['voltage']}")
        _LOGGER.info("---")
    
    doodle_helper.logout()


if __name__ == "__main__":
    main()