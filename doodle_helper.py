import requests
import json

class DoodleHelper:
    def __init__(self, host_ip, username, password, logger):
        self.url = f"https://{host_ip}/ubus"
        self.username = username
        self.password = password
        self.logger = logger
        self.session = requests.Session()
        self.session.verify = False

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
            self.logger.info("Doodle login success")
            self.token = data["result"][1]["ubus_rpc_token"]
            return True
    
    def get_battery_data(self) -> float:
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
            
            out = stdout.strip()
            json_data = json.loads(out)

            if "VIN VOLTAGE" in json_data:
                voltage = json_data["VIN VOLTAGE"] / 20.2 # This is a magic number
                self.logger.info(f"Voltage: {voltage}V")

            self.logger.info("Command Errors:\n", stderr if stderr else "No Errors")
            return voltage
        else:
            self.logger.info("No result found or error in execution")
            return None
    
    def get_associations(self):
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
            assoc_list = data['result'][1]
            self.logger.info(f"Association List:\n{json.dumps(assoc_list, indent=4)}")
            return assoc_list
        else:
            self.logger.info("No result found or error in execution")
            return None
    
    def logout(self):
        self.session.close()
        self.logger.info("Doodle logout success")