import requests
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

BATTERY_VOLTAGE_MAX = 8.4
BATTERY_VOLTAGE_MIN = 6.6

class StationDiscovery:
    def __init__(self, logger, cache_ttl_minutes: int = 5):
        self.logger = logger
        self.cache_ttl = timedelta(minutes=cache_ttl_minutes)
        self.discovered_stations: Dict[str, str] = {}  # {mac_address: ip_address}
        self.last_discovery: Optional[datetime] = None
    
    def _estimate_percentage(self, voltage: float) -> float:
        return max(0, min(100, ((voltage - BATTERY_VOLTAGE_MIN) / (BATTERY_VOLTAGE_MAX - BATTERY_VOLTAGE_MIN)) * 100.0))
    
    def _mac_to_ip(self, mac_address: str) -> str:
        """Convert MAC address to IP address using the network scheme."""
        return f"10.223.{int(mac_address.split(':')[4], 16)}.{int(mac_address.split(':')[5], 16)}"
    
    def should_update_cache(self) -> bool:
        """Check if the station topology cache needs to be updated based on TTL."""
        if self.last_discovery is None:
            return True
        return datetime.now() - self.last_discovery > self.cache_ttl
    
    def update_station_cache(self, root_station: 'DoodleHelper') -> None:
        """Update the cache of all reachable stations (topology only)."""
        self.logger.info("Updating station topology cache...")
        visited = set()
        to_visit = [(None, root_station)]  # (parent_mac, station)
        
        while to_visit:
            parent_mac, current_station = to_visit.pop(0)
            
            # Get associated stations
            stations = current_station.get_associated_stations()
            if not stations:
                continue
                
            for station in stations:
                mac_address = station['mac']
                if mac_address in visited:
                    continue
                    
                visited.add(mac_address)
                ip_address = self._mac_to_ip(mac_address)
                self.discovered_stations[mac_address] = ip_address
                
                # Create new helper for this station to discover its neighbors
                station_helper = DoodleHelper(ip_address, 
                                           current_station.username,
                                           current_station.password, 
                                           self.logger)
                
                if station_helper.login():
                    # Add this station to the visit queue to discover its neighbors
                    to_visit.append((mac_address, station_helper))
                    station_helper.logout()
        
        self.last_discovery = datetime.now()
        self.logger.info(f"Topology cache updated. Found {len(self.discovered_stations)} stations.")
    
    def get_station_voltages(self, root_station: 'DoodleHelper') -> List[Dict[str, any]]:
        """Get fresh voltage readings for all discovered stations."""
        results = []
        
        for mac_address, ip_address in self.discovered_stations.items():
            # Create helper for this station
            station_helper = DoodleHelper(ip_address, 
                                        root_station.username,
                                        root_station.password, 
                                        self.logger)
            
            voltage = None
            if station_helper.login():
                voltage = station_helper.get_battery_voltage()
                station_helper.logout()
            
            results.append({
                'mac_address': mac_address,
                'ip_address': ip_address,
                'voltage': voltage,
                'battery_percentage': self._estimate_percentage(voltage)
            })
        
        return results

class DoodleHelper:
    def __init__(self, host_ip, username, password, logger):
        self.url = f"https://{host_ip}/ubus"
        self.username = username
        self.password = password
        self.logger = logger
        self.session = requests.Session()
        self.session.verify = False
        self.station_discovery = StationDiscovery(logger)

        requests.packages.urllib3.disable_warnings(requests.packages.urllib3.exceptions.InsecureRequestWarning)
        
    def login(self):
        login_payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "call",
            "params": ["00000000000000000000000000000000", "session", "login", {"username": self.username, "password": self.password}]
        }

        response = self.session.post(self.url, json=login_payload)
        data = response.json()
        if data.get("error"):
            self.logger.error(f"Doodle login failed: {data['error']}")
            return False
        else:
            self.logger.debug("Doodle login success")
            self.token = data["result"][1]["ubus_rpc_session"]
            return True
    
    def get_battery_voltage(self) -> float:
        get_battery_payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "call",
            "params": [self.token, "file", "exec", {
                "command": "cat",
                "params": ["/tmp/run/pancake.txt"]
            }]
        }

        response = self.session.post(self.url, json=get_battery_payload)
        data = response.json()

        if 'result' in data and data['result'][1]:
            stdout = data['result'][1].get('stdout', '')
            stderr = data['result'][1].get('stderr', '')

            self.logger.debug(f"Command Errors:\n{stderr if stderr else 'No Errors'}")
            
            out = stdout.strip()
            json_data = json.loads(out)

            if "VIN VOLTAGE" in json_data:
                voltage = float(json_data["VIN VOLTAGE"]) / 20.2 # This is a magic number
                self.logger.debug(f"Voltage: {voltage}V")
                return voltage
            else:
                self.logger.debug(f"No voltage data found in: {json_data}")
                return None
        else:
            self.logger.debug("No result found or error in execution")
            return None
    
    def get_associated_stations(self):
        get_associations_payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "call",
            "params": [self.token, "iwinfo", "assoclist", {
                "device": "wlan0"
            }]
        }

        response = self.session.post(self.url, json=get_associations_payload)
        data = response.json()

        if 'result' in data and data['result'][1]:
            assoc_list = data['result'][1]['results']
            self.logger.debug(f"Association List:\n{json.dumps(assoc_list, indent=4)}")
            return assoc_list
        else:
            self.logger.debug("No result found or error in execution")
            return None
    
    def get_all_reachable_stations(self) -> List[Dict[str, any]]:
        """Get all reachable stations and their voltages, using cache if available."""
        if self.station_discovery.should_update_cache():
            self.station_discovery.update_station_cache(self)
        return self.station_discovery.get_station_voltages(self)

    def logout(self):
        self.session.close()
        self.logger.debug("Doodle logout success")