from http import HTTPStatus

import requests

COREIO_PORT = "21443"

class CoreIOHelper:
    """Handles CORE I/O login"""

    def __init__(self, hostname, username, password, logger):
        self.base_url = f"https://{hostname}:{COREIO_PORT}"
        self.username = username
        self.password = password
        self.logger = logger
        self.auth_cookies = None
        self._is_authenticated = False
    
    def login(self):
        """Login to CORE I/O"""
        init_response = requests.get(self.base_url, verify=False)
        self.auth_cookies = requests.utils.dict_from_cookiejar(init_response.cookies)
        login_response = requests.post(
            f'{self.base_url}/api/v0/login', data={
                'username': self.username,
                'password': self.password
            }, verify=False, headers={
                'x-csrf-token': self.auth_cookies['x-csrf-token']
            }, cookies=self.auth_cookies).json()
        if 'error' in login_response:
            self._is_authenticated = False
            self.logger.error(login_response['error'])
            return False
        else:
            self._is_authenticated = True
            self.logger.info("CORE I/O login success")
            return True