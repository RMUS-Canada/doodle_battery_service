import logging
import os
import time

from bosdyn.api import data_acquisition_pb2, data_acquisition_plugin_service_pb2_grpc
from bosdyn.client.data_acquisition_store import DataAcquisitionStoreClient
from bosdyn.client.data_acquisition_plugin_service import Capability, DataAcquisitionPluginService, DataAcquisitionStoreHelper
from bosdyn.client.directory_registration import (DirectoryRegistrationClient, DirectoryRegistrationKeepAlive)
from bosdyn.client.robot_state import RobotStateClient

import bosdyn.client.util
from bosdyn.client.util import setup_logging
from bosdyn.client.server_util import GrpcServiceRunner
from bosdyn.client.signals_helpers import build_capability_live_data, build_live_data_response

from doodle_helper import DoodleHelper
from build_signal import build_signals
import bosdyn.client.exceptions as bd_exceptions

DIRECTORY_NAME = 'data-acquisition-doodle-battery'
AUTHORITY = 'data-acquisition-doodle-battery'
CAPABILITY = Capability(name='doodle-battery', description='Doodle Battery Level', channel_name='doodle-battery', has_live_data=True)

_LOGGER = logging.getLogger('doodle_battery_service')

class DoodleBatteryAdapter:
    def __init__(self, host_ip, username, password):
        self.host_ip = host_ip
        self.username = username
        self.password = password
        self.doodle_helper = DoodleHelper(host_ip, username, password, _LOGGER)
        self.doodle_helper.login()
    
    def get_battery_data(self, request, store_helper):
        data_id = data_acquisition_pb2.DataIdentifier(action_id=request.action_id, channel=CAPABILITY.channel_name)
        data = self.doodle_helper.get_battery_voltage()
        
        store_helper.cancel_check()
        store_helper.state.set_status(data_acquisition_pb2.GetStatusResponse.STATUS_SAVING)
        
        message = data_acquisition_pb2.AssociatedMetadata()
        message.reference_id.action_id.CopyFrom(request.action_id)
        message.metadata.data.update({
            "battery_voltage": data
        })
        _LOGGER.info(f"Retrieving battery data : {message.metadata.data}")

        store_helper.store_metadata(message, data_id)
    
    def get_live_data(self, request):
        # Get all reachable stations with fresh voltage readings except the local station
        stations = [station for station in self.doodle_helper.get_all_reachable_stations() if station['ip_address'] != self.host_ip]

        # Build signals for all stations
        signals = build_signals(stations)

        return build_live_data_response([build_capability_live_data(signals, CAPABILITY.name)])

def make_servicer(sdk_robot, host_ip, username, password):
    adapter = DoodleBatteryAdapter(host_ip, username, password)
    return DataAcquisitionPluginService(sdk_robot, [CAPABILITY], adapter.get_battery_data, live_response_fn=adapter.get_live_data, logger=_LOGGER)

def run_service(sdk_robot, host_ip, username, password, port):
    add_servicer_to_server_fn = data_acquisition_plugin_service_pb2_grpc.add_DataAcquisitionPluginServiceServicer_to_server

    return GrpcServiceRunner(make_servicer(sdk_robot,host_ip, username, password), add_servicer_to_server_fn, port, logger=_LOGGER)

def authenticate_with_backoff(robot, guid, secret, max_retries=5, base_interval=5.0):
    for attempt in range(max_retries):
        try:
            robot.authenticate_from_payload_credentials(guid, secret, retry_interval=base_interval)
            return True
        except bd_exceptions.TooManyRequestsError as e:
            wait_time = base_interval * (2 ** attempt)
            _LOGGER.info(f"Too many requests, retrying in {wait_time} seconds...")
            time.sleep(wait_time)
    raise RuntimeError("Failed to authenticate after multiple attempts due to TooManyRequestsError.")

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    bosdyn.client.util.add_base_arguments(parser)
    bosdyn.client.util.add_payload_credentials_arguments(parser)
    bosdyn.client.util.add_service_endpoint_arguments(parser)
    options = parser.parse_args()

    setup_logging(options.verbose)
    
    sdk = bosdyn.client.create_standard_sdk("DoodleBatteryService")
    robot = sdk.create_robot(options.hostname)
    guid, secret = bosdyn.client.util.get_guid_and_secret(options)
    authenticate_with_backoff(robot, guid, secret)

    # Read RPC credentials from file
    rpc_cred = open("/doodle_rpc_credentials", "r").read().splitlines()
    HOST_IP = rpc_cred[0]
    USERNAME = rpc_cred[1]
    PASSWORD = rpc_cred[2]

    service_runner = run_service(robot, host_ip=HOST_IP, username=USERNAME, password=PASSWORD, port=options.port)

    dir_reg_client = robot.ensure_client(DirectoryRegistrationClient.default_service_name)
    keep_alive = DirectoryRegistrationKeepAlive(dir_reg_client, logger=_LOGGER)
    keep_alive.start(DIRECTORY_NAME, DataAcquisitionPluginService.service_type, AUTHORITY, options.host_ip, service_runner.port)

    with keep_alive:
        service_runner.run_until_interrupt()
