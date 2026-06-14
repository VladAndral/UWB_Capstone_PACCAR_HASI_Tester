"""
Automated PACCAR Hardware-in-the-Loop (HIL) Gateway Validation Suite.
Uses Pytest to validate CAN and CAN-FD routing across physical or virtual Vector hardware.
"""

import os
import random
import threading
import time

import can
import pytest
import pytest_check as check
from can.interfaces import vector
from can.interfaces.vector import exceptions as vector_exceptions

import dbc_parser

# ==============================================================================
# TERMINAL EXECUTION COMMANDS
# ==============================================================================
# Standard execution with physical hardware:
# pytest tests/ --dbcPath "C:\path\to\your\HASI_Primary_ALL_CAN.dbc"
#
# Virtual execution bypass (without physical hardware):
# pytest tests/ --dbcPath "C:\path\to\your\HASI_Primary_ALL_CAN.dbc" --virtual true

# ==============================================================================
# HARDWARE & TIMEOUT CONFIGURATION
# ==============================================================================

# Master Configuration Constants
# DEV NOTE: Set these to 1.0s and 0.1s respectively for final hardware reporting.
# Lower to 0.05s and 0.01s for faster virtual development.
ROUTING_TIMEOUT = 1.0   # Seconds to wait for hardware to route the frame
RECV_POLL_RATE = 0.1    # Interval to check the receive buffer
MAX_RETRIES = 5         # Hardware retry allowance for processing latency

CAN_CLASSIC = ["VCAN1", "VCAN10", "PCAN1", "PCAN2", "VCAN2", "VCAN20"]
CAN_FD = ["ADSCAN1", "ADSCAN2"]

# Shared J1939 CAN-FD timing profile
j1939_fd_timing = can.BitTimingFd.from_bitrate_and_segments(
    f_clock=80_000_000,
    nom_bitrate=500_000,
    data_bitrate=2_000_000,
    nom_tseg1=63,
    nom_tseg2=16,
    nom_sjw=4,
    data_tseg1=15,
    data_tseg2=4,
    data_sjw=1,
)

# Make sure this matches the application name configured in Vector Hardware Manager
VECTOR_APPLICATION_NAME = "CANoe"

# Profiles
# STD for J1939 CAN Classic Ports
# FD for J1939-22 CAN Fast Data Ports
# THE FIX: app_name is set to 'CANoe' to force physical hardware ports to respect protocol switches.
STD_PROFILE = {"fd": False, "bitrate": 500000, "app_name": VECTOR_APPLICATION_NAME}
FD_PROFILE = {"fd": True, "timing": j1939_fd_timing, "app_name": VECTOR_APPLICATION_NAME}

# The Master Channel Dictionary
NETWORK_CONFIGS = {
    "VCAN1": {"channel": 0, **STD_PROFILE},
    "VCAN10": {"channel": 1, **STD_PROFILE},
    "PCAN1": {"channel": 2, **STD_PROFILE},
    "PCAN2": {"channel": 3, **STD_PROFILE},
    "VCAN2": {"channel": 4, **STD_PROFILE},
    "VCAN20": {"channel": 5, **STD_PROFILE},
    "ADSCAN1": {"channel": 6, **FD_PROFILE},
    "ADSCAN2": {"channel": 7, **FD_PROFILE},
}

# ==============================================================================
# DATA FLATTENER & PARAMETERIZATION (Pytest Hook)
# ==============================================================================

def pytest_generate_tests(metafunc):
    """
    Native Pytest hook that dynamically generates test cases based on the 
    --dbcPath CLI argument passed in the terminal.
    """
    # Check if the current test function expects our gateway parameters
    if "sender_name" in metafunc.fixturenames:
        
        # Grab the file path directly from the terminal argument
        dbc_filepath = metafunc.config.getoption("--dbcPath")
        
        if not os.path.exists(dbc_filepath):
            raise FileNotFoundError(
                f"\n[FATAL CONFIG ERROR] Could not find DBC file at: '{dbc_filepath}'\n"
                "Please check your --dbcPath terminal argument."
            )

        # Unpack both dictionaries from the scraper
        gateway_spec_dict, message_name_dict = dbc_parser.scrape_dbc_for_gateways(dbc_filepath)

        test_cases = []
        test_ids = []

        for raw_id, channel_paths in gateway_spec_dict.items():
            parsed_msg_name = message_name_dict.get(raw_id, "UNKNOWN_MSG")
            masked_id = dbc_parser.format_arbitration_id(raw_id, "int")
            hex_id = f"0x{masked_id:08X}"

            for gateway_channel_pair in channel_paths:
                src_node, dst_node = gateway_channel_pair.split(":")

                sender_protocol = "CAN-FD" if src_node in CAN_FD else "CAN Classic"
                receiver_protocol = "CAN-FD" if dst_node in CAN_FD else "CAN Classic"
                gateway_type = f"{sender_protocol} -> {receiver_protocol}"
                route_pair = f"{src_node}:{dst_node}"

                terminal_label = (
                    f"ROUTE: {route_pair:<14} | GATEWAY TYPE: {gateway_type:<27} | "
                    f"{parsed_msg_name:<42} ({hex_id} | Raw: {raw_id})"
                )

                test_cases.append((src_node, dst_node, raw_id, parsed_msg_name))
                test_ids.append(terminal_label)

        # Inject the parameterized data directly into the test suite
        metafunc.parametrize(
            "sender_name, receiver_name, arbitration_id_raw, msg_name",
            test_cases,
            ids=test_ids
        )

# ==============================================================================
# HARDWARE FIXTURE (FAIL-FAST ARCHITECTURE)
# ==============================================================================

@pytest.fixture(scope="module")
def active_buses(request):
    """Initializes hardware connections. Uses hard fail-fast if hardware is disconnected."""
    
    # Grab the virtual flag from the terminal
    is_virtual = str(request.config.getoption("--virtual")).lower() == "true"

    print("\n" + "=" * 70)
    print(f"INITIALIZING ALL 8 VECTOR CHANNELS (Virtual Mode: {is_virtual})...")
    print("=" * 70)

    connected_buses = {}

    try:
        for bus_name, bus_params in NETWORK_CONFIGS.items():
            if is_virtual:
                connected_buses[bus_name] = can.interface.Bus(
                    interface="virtual", channel=bus_name, bitrate=500000
                )
            else:
                try:
                    connected_buses[bus_name] = vector.VectorBus(**bus_params)
                    print(f" - Successfully opened {bus_name}")
                except (
                    can.CanInitializationError,
                    vector_exceptions.VectorInitializationError,
                ) as init_error:
                    pytest.fail(
                        f"\n[HARDWARE ERROR] Failed to connect to Vector channel: {bus_name}\n"
                        "Is the Vector VN1640A physically plugged into the USB port?\n"
                        f"Original Error: {init_error}"
                    )

        yield connected_buses

    finally:
        print("\n[Hardware Release] Closing all active channels and shutting down...")
        for bus_name, bus in connected_buses.items():
            if bus is not None:
                try:
                    bus.shutdown()
                    print(f" - Closed {bus_name}")
                except can.CanError:
                    pass

# ==============================================================================
# GATEWAY EXECUTION LOGIC (GATHER-ALL ARCHITECTURE)
# ==============================================================================

def test_paccar_routing_logic(
    active_buses, sender_name, receiver_name, arbitration_id_raw, msg_name, record_property, request
):
    # pylint: disable=redefined-outer-name
    """
    Executes a gateway routing test for a specific CAN/CAN-FD path.
    """
    
    # Grab the virtual flag from the terminal for the fake ECU thread
    is_virtual = str(request.config.getoption("--virtual")).lower() == "true"

    # CI/CD Pipeline Tracking Injections
    record_property("sender_node", sender_name)
    record_property("receiver_node", receiver_name)
    record_property("target_id", arbitration_id_raw)

    tx_bus = active_buses[sender_name]
    rx_bus = active_buses[receiver_name]

    is_sender_fd = sender_name in CAN_FD
    is_receiver_fd = receiver_name in CAN_FD

    # --- PROTOCOL IDENTIFIER LOGIC ---
    tx_protocol = "CAN-FD" if is_sender_fd else "CAN Classic"
    rx_protocol = "CAN-FD" if is_receiver_fd else "CAN Classic"
    routing_type = f"{tx_protocol} -> {rx_protocol}"

    int_arbitration_id = int(dbc_parser.format_arbitration_id(arbitration_id_raw, "int"))
    dummy_data = [random.randint(0, 255) for _ in range(8)]
    msg = None

    # Format sender message (What goes ONTO the bus)
    if is_sender_fd:
        send_id, send_payload = dbc_parser.generate_j1939_22_envelope(
            int_arbitration_id, dummy_data
        )
        msg = can.Message(
            is_rx=False,
            is_extended_id=True,
            is_fd=True,
            bitrate_switch=True,
            dlc=9,
            arbitration_id=send_id,
            data=send_payload,
        )
    else:
        msg = can.Message(
            is_rx=False,
            is_extended_id=True,
            arbitration_id=int_arbitration_id,
            data=dummy_data,
        )

    if msg is None:
        pytest.fail(f"FATAL SCRIPT LOGIC: Formatting bypassed for ID {arbitration_id_raw}.")

    # Format receiver message (What comes OFF the bus)
    if is_receiver_fd:
        expected_id, expected_data = dbc_parser.generate_j1939_22_envelope(
            int_arbitration_id, dummy_data
        )
        expected_is_fd = True
    else:
        expected_id = int_arbitration_id
        expected_data = dummy_data
        expected_is_fd = False

    test_passed = False
    elapsed_time_ms = 0.0

    # Hardware Retry Loop
    print(
        f"\n=== Testing: {msg_name} | 0x{expected_id:08X} "
        f"(Raw: {arbitration_id_raw}) ({routing_type}) ==="
    )

    for attempt in range(MAX_RETRIES):
        formatted_send_payload = " ".join(f"{x:02x}" for x in msg.data)
        print(
            f" [TX] {sender_name:<8} : 0x{msg.arbitration_id:08X} ({msg_name}) | "
            f"{formatted_send_payload} (Attempt {attempt + 1})"
        )

        # Flush the receive buffer to prevent reading stale frames
        while rx_bus.recv(0.0) is not None:
            pass

        start_time = time.time()
        tx_bus.send(msg)

        # Virtual Fault Injection Thread
        if is_virtual:
            def fake_hardware_gateway():
                time.sleep(0.015)
                if random.random() < 0.20:
                    injected_id = expected_id ^ 0xFF
                else:
                    injected_id = expected_id
                fake_msg = can.Message(
                    is_extended_id=True,
                    is_fd=expected_is_fd,
                    arbitration_id=injected_id,
                    data=expected_data,
                )
                with can.interface.Bus(
                    interface="virtual", channel=receiver_name
                ) as dummy_ecu:
                    dummy_ecu.send(fake_msg)

            threading.Thread(target=fake_hardware_gateway, daemon=True).start()

        timeout_end = start_time + ROUTING_TIMEOUT
        found_routed_frame = False
        received_message = None

        # Watchdog loop
        while time.time() < timeout_end:
            received_message = rx_bus.recv(RECV_POLL_RATE)

            if received_message:
                if list(received_message.data) == expected_data:
                    elapsed_time_ms = (time.time() - start_time) * 1000
                    found_routed_frame = True
                    break

        # Soft Evaluation (Logs the error but continues the loop)
        if found_routed_frame and received_message is not None:
            formatted_recv_payload = " ".join(f"{x:02x}" for x in received_message.data)
            print(
                f"   [RX] {receiver_name:<8} : 0x{received_message.arbitration_id:08X} | "
                f"{formatted_recv_payload}"
            )

            # Mutations on arbitration IDs are marked as failures
            if (
                received_message.arbitration_id == expected_id
                and received_message.is_fd == expected_is_fd
            ):
                record_property("latency_ms", round(elapsed_time_ms, 2))
                print(
                    f"    [PASS] Routing Successful! ({elapsed_time_ms:.1f} ms) | "
                    f"Expected: 0x{expected_id:08X} == Received: 0x{received_message.arbitration_id:08X}"
                )
                test_passed = True
                break
            else:
                print(
                    f"    [FAIL / MUTATED] Frame routed, but gateway incorrectly "
                    f"translated the ID/Protocol! ({elapsed_time_ms:.1f} ms)"
                )
                print(f"           Expected   : 0x{expected_id:08X} (FD: {expected_is_fd})")
                print(
                    f"           Received   : 0x{received_message.arbitration_id:08X} "
                    f"(FD: {received_message.is_fd})"
                )
                break

        else:
            print("    [FAIL] Gateway dropped the frame (Timeout).")

    # Final Non-Blocking Assertion
    check.is_true(
        test_passed, f"Gateway {sender_name}:{receiver_name} FAILED ID {arbitration_id_raw}."
    )