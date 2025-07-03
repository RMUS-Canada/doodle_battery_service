import requests
from requests.adapters import HTTPAdapter
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor
import socket

from urllib3 import Retry

BATTERY_VOLTAGE_MAX = 8.2
BATTERY_VOLTAGE_MIN = 6.6
REQUEST_TIMEOUT = 2  # seconds
MAX_WORKERS = 10  # maximum number of concurrent requests

class StationDiscovery:
    def __init__(self, logger, cache_ttl_minutes: int = 1):
        self.logger = logger
        self.cache_ttl = timedelta(minutes=cache_ttl_minutes)
        self.discovered_stations: Dict[str, str] = {}  # {mac_address: ip_address}
        self.last_discovery: Optional[datetime] = None
        self.failed_login_attempts: Dict[str, int] = {}  # Track failed login attempts per station
    
    def _estimate_percentage(self, voltage: float) -> float:
        return max(0, min(100, ((voltage - BATTERY_VOLTAGE_MIN) / (BATTERY_VOLTAGE_MAX - BATTERY_VOLTAGE_MIN)) * 100.0))
    
    def _mac_to_ip(self, mac_address: str) -> str:
        """Convert MAC address to IP address using the network scheme."""
        return f"10.223.{int(mac_address.split(':')[4], 16)}.{int(mac_address.split(':')[5], 16)}"
    
    def remove_station(self, mac_address: str) -> None:
        """Remove a station from the cache and reset its failed login attempts."""
        if mac_address in self.discovered_stations:
            self.logger.warning(f"Removing unreachable station {mac_address} from cache")
            del self.discovered_stations[mac_address]
        if mac_address in self.failed_login_attempts:
            del self.failed_login_attempts[mac_address]
    
    def should_update_cache(self) -> bool:
        """Check if the station topology cache needs to be updated based on TTL."""
        if self.last_discovery is None:
            return True
        return datetime.now() - self.last_discovery > self.cache_ttl
    
    def _is_radio_responsive(self, ip_address: str) -> bool:
        """Check if a radio is responsive by attempting a TCP connection."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)  # 2 second timeout for connection
            result = sock.connect_ex((ip_address, 443))  # HTTPS port
            sock.close()
            return result == 0
        except Exception:
            return False

    def _process_station(self, station_info: Tuple[str, 'DoodleHelper']) -> Optional[Dict]:
        """Process a single station and return its voltage information."""
        mac_address, station_helper = station_info
        ip_address = station_helper.host_ip

        # Quick check if radio is responsive
        if not self._is_radio_responsive(ip_address):
            self.logger.debug(f"Radio at {ip_address} is not responsive, skipping")
            return None

        voltage = 0.0
        try:
            if station_helper.login():
                # Reset failed attempts on successful login
                self.failed_login_attempts[mac_address] = 0
                voltage = station_helper.get_battery_voltage()
                if voltage is not None:  # Only return result if we got a valid voltage
                    return {
                        'mac_address': mac_address,
                        'ip_address': ip_address,
                        'voltage': voltage,
                        'battery_percentage': self._estimate_percentage(voltage)
                    }
            else:
                # Increment failed attempts
                self.failed_login_attempts[mac_address] = self.failed_login_attempts.get(mac_address, 0) + 1
                if self.failed_login_attempts[mac_address] >= 3:
                    self.remove_station(mac_address)
        except Exception as e:
            self.logger.debug(f"Error processing station {mac_address}: {str(e)}")
        finally:
            station_helper.logout()
        
        return None

    def _discover_neighbors(self, current_station: 'DoodleHelper', visited: set) -> None:
        """Discover neighboring stations from the current station."""
        try:
            stations = current_station.get_associated_stations()
            if not stations:
                return

            for station in stations:
                mac_address = station['mac']
                if mac_address in visited:
                    continue

                visited.add(mac_address)
                ip_address = self._mac_to_ip(mac_address)

                # Only add station if it's responsive
                if self._is_radio_responsive(ip_address):
                    self.discovered_stations[mac_address] = ip_address
                    
                    # Create new helper for this station
                    station_helper = DoodleHelper(ip_address, 
                                               current_station.username,
                                               current_station.password, 
                                               self.logger)
                    
                    if station_helper.login():
                        self._discover_neighbors(station_helper, visited)
                        station_helper.logout()
        except Exception as e:
            self.logger.debug(f"Error discovering neighbors: {str(e)}")

    def update_station_cache(self, root_station: 'DoodleHelper') -> None:
        """Update the cache of all reachable stations (topology only)."""
        self.logger.info("Updating station topology cache...")
        visited = set()
        
        # Reset failed login attempts when updating cache
        self.failed_login_attempts.clear()
        self.discovered_stations.clear()
        
        # Start discovery from root station
        self._discover_neighbors(root_station, visited)
        
        self.last_discovery = datetime.now()
        self.logger.info(f"Topology cache updated. Found {len(self.discovered_stations)} stations.")

    def get_station_voltages(self, root_station: 'DoodleHelper') -> List[Dict[str, any]]:
        """Get fresh voltage readings for all discovered stations concurrently."""
        station_helpers = [
            (mac, DoodleHelper(ip, root_station.username, root_station.password, self.logger))
            for mac, ip in self.discovered_stations.items()
        ]

        results = []
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = [executor.submit(self._process_station, station_info) 
                      for station_info in station_helpers]
            
            for future in concurrent.futures.as_completed(futures):
                try:
                    result = future.result()
                    if result is not None:
                        results.append(result)
                except Exception as e:
                    self.logger.debug(f"Error processing station result: {str(e)}")

        return results

class DoodleHelper:
    def __init__(self, host_ip, username, password, logger):
        self.host_ip = host_ip
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

        try:
            response = self.session.post(self.url, json=login_payload, timeout=REQUEST_TIMEOUT)
            data = response.json()
            if data.get("error"):
                self.logger.error(f"Doodle login failed: {data['error']}")
                return False
            else:
                self.logger.debug("Doodle login success")
                self.token = data["result"][1]["ubus_rpc_session"]
                return True
        except Exception as e:
            self.logger.debug(f"Failed to login to radio at {self.url}: {str(e)}")
            return False
    
    def get_battery_voltage(self) -> Optional[float]:
        try:
            get_battery_payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "call",
                "params": [self.token, "file", "exec", {
                    "command": "cat",
                    "params": ["/tmp/run/pancake.txt"]
                }]
            }

            response = self.session.post(self.url, json=get_battery_payload, timeout=REQUEST_TIMEOUT)
            data = response.json()

            if 'result' in data and data['result'][1]:
                stdout = data['result'][1].get('stdout', '')
                stderr = data['result'][1].get('stderr', '')

                self.logger.debug(f"Command Errors:\n{stderr if stderr else 'No Errors'}")
                
                out = stdout.strip()
                json_data = json.loads(out)

                if "VIN VOLTAGE" in json_data:
                    voltage = float(json_data["VIN VOLTAGE"]) / 20.2
                    self.logger.debug(f"Voltage: {voltage}V")
                    return voltage

            return None
        except Exception as e:
            self.logger.debug(f"Error getting battery voltage from {self.url}: {str(e)}")
            return None
    
    def get_associated_stations(self) -> Optional[List[Dict]]:
        try:
            get_associations_payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "call",
                "params": [self.token, "iwinfo", "assoclist", {
                    "device": "wlan0"
                }]
            }

            response = self.session.post(self.url, json=get_associations_payload, timeout=REQUEST_TIMEOUT)
            data = response.json()

            if 'result' in data and data['result'][1]:
                assoc_list = data['result'][1]['results']
                self.logger.debug(f"Association List:\n{json.dumps(assoc_list, indent=4)}")
                return assoc_list

            return None
        except Exception as e:
            self.logger.debug(f"Error getting associated stations from {self.url}: {str(e)}")
            return None
    
    def get_all_reachable_stations(self) -> List[Dict[str, any]]:
        """Get all reachable stations and their voltages, using cache if available."""
        if self.station_discovery.should_update_cache():
            self.station_discovery.update_station_cache(self)
        return self.station_discovery.get_station_voltages(self)

    def logout(self):
        try:
            self.session.close()
            self.logger.debug("Doodle logout success")
        except Exception as e:
            self.logger.debug(f"Error during logout: {str(e)}")