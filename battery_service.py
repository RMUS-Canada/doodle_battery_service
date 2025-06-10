import logging
from google.protobuf import json_format

from bosdyn.api import data_acquisition_pb2, data_acquisition_plugin_service_pb2_grpc
from bosdyn.client.data_acquisition_store import DataAcquisitionStoreClient
from bosdyn.client.data_acquisition_plugin_service import Capability, DataAcquisitionPluginService, DataAcquisitionStoreHelper
from bosdyn.client.directory_registration import (DirectoryRegistrationClient, DirectoryRegistrationKeepAlive)
from bosdyn.client.robot_state import RobotStateClient
import bosdyn.client.util
from bosdyn.client.util import setup_logging
from bosdyn.client.server_util import GrpcServiceRunner
from bosdyn.client.signals_helpers import build_capability_live_data, build_live_data_response

from build_signal import build_signals

DIRECTORY_NAME = 'data-acquisition-battery'
AUTHORITY = 'data-acquisition-battery'
CAPABILITY = Capability(name='battery', description='Battery level', channel_name='battery', has_live_data=True)

_LOGGER = logging.getLogger('battery_plugin')

class BatteryAdapter:
    def __init__(self, sdk_robot):
        self.client = sdk_robot.ensure_client(RobotStateClient.default_service_name)

    def get_battery_data(self, request, store_helper):
        data_id = data_acquisition_pb2.DataIdentifier(action_id=request.action_id, channel=CAPABILITY.channel_name)
        state = self.client.get_robot_state(timeout=1)
        
        store_helper.cancel_check()
        store_helper.state.set_status(data_acquisition_pb2.GetStatusResponse.STATUS_SAVING)
        
        message = data_acquisition_pb2.AssociatedMetadata()
        message.reference_id.action_id.CopyFrom(request.action_id)
        message.metadata.data.update({
            "battery_percentage":
                self.state.power_state.locomotion_charge_percentage.value,
            "battery_runtime":
                json_format.MessageToJson(self.state.power_state.locomotion_estimated_runtime)
        })
        _LOGGER.info(f"Retrieving battery data : {message.metadata.data}")

        store_helper.store_metadata(message, data_id)
    
    def get_live_data(self, request):
        request_caps =  ", ".join(
            data_capture.name for data_capture in request.data_captures)
        _LOGGER.info(f"get_live_data called, request capabilities {request_caps}")

        state = self.client.get_robot_state(timeout=1)
        data = {
            "battery_percentage":
                state.power_state.locomotion_charge_percentage.value,
            "battery_runtime":
                json_format.MessageToJson(state.power_state.locomotion_estimated_runtime)
        }

        signals = build_signals(data)
        return build_live_data_response([build_capability_live_data(signals, CAPABILITY.name)])

    
def make_servicer(sdk_robot):
    adapter = BatteryAdapter(sdk_robot)
    return DataAcquisitionPluginService(sdk_robot, [CAPABILITY], adapter.get_battery_data, live_response_fn=adapter.get_live_data, logger=_LOGGER)

def run_service(sdk_robot, port):
    add_servicer_to_server_fn = data_acquisition_plugin_service_pb2_grpc.add_DataAcquisitionPluginServiceServicer_to_server

    return GrpcServiceRunner(make_servicer(sdk_robot), add_servicer_to_server_fn, port, logger=_LOGGER)

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    bosdyn.client.util.add_base_arguments(parser)
    bosdyn.client.util.add_payload_credentials_arguments(parser)
    bosdyn.client.util.add_service_endpoint_arguments(parser)
    options = parser.parse_args()

    setup_logging(options.verbose)

    sdk = bosdyn.client.create_standard_sdk("BatteryPlugin")
    robot = sdk.create_robot(options.hostname)
    guid, secret = bosdyn.client.util.get_guid_and_secret(options)
    robot.authenticate_from_payload_credentials(guid, secret)

    service_runner = run_service(robot, options.port)

    dir_reg_client = robot.ensure_client(DirectoryRegistrationClient.default_service_name)
    keep_alive = DirectoryRegistrationKeepAlive(dir_reg_client, logger=_LOGGER)
    keep_alive.start(DIRECTORY_NAME, DataAcquisitionPluginService.service_type, AUTHORITY, options.host_ip, service_runner.port)

    with keep_alive:
        service_runner.run_until_interrupt()
