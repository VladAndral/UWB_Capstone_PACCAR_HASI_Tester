import os
import utils
import can
import time
import pytest
import pytest_check as check
from can.interfaces import vector
import random
from can.interfaces.vector import exceptions as vector_exceptions
import threading

# NOTE to run in virtual mode (without physical hardware), run the command below in the terminal.
# NOTE input file path for DBC_PATH environment variable
# $env:DBC_PATH="C:\Users\garci\Downloads\HASI_Primary_ALL_CAN (5).dbc"; $env:VIRTUAL_MODE="True"; pytest
# Otherwise, ensure the Vector VN1640A is plugged in with the correct channels connected to the CAN bus and run:
# $env:DBC_PATH="C:\Users\garci\Downloads\HASI_Primary_ALL_CAN (5).dbc"; $env:VIRTUAL_MODE="False"; pytest

# ==============================================================================
# HARDWARE & TIMEOUT CONFIGURATION
# ==============================================================================

# environmental variable to toggle virtual mode for testing without physical hardware. Defaults to False
env_virtual = os.getenv("VIRTUAL_MODE", "False")
VIRTUAL_MODE = env_virtual.lower() in ('true', '1', 't')

# Master Configuration Constants
ROUTING_TIMEOUT = 1.0   # Seconds to wait for hardware to route the frame
RECV_POLL_RATE = 0.1   # Interval to check the receive buffer
MAX_RETRIES = 5         # Hardware retry allowance for processing latency

CAN_CLASSIC = ['VCAN1', 'VCAN10', 'PCAN1', 'PCAN2', 'VCAN2', 'VCAN20']
CAN_FD = ['ADSCAN1', 'ADSCAN2']

# Shared J1939 CAN-FD timing profile
j1939_fd_timing = can.BitTimingFd.from_bitrate_and_segments(
    f_clock=80_000_000, nom_bitrate=500_000, data_bitrate=2_000_000, 
    nom_tseg1=63, nom_tseg2=16, nom_sjw=4, 
    data_tseg1=15, data_tseg2=4, data_sjw=1
)

# THE FIX: app_name is set to 'None' to bypass the Vector Hardware Config caching bug.
# This forces the physical hardware ports to respect our protocol switches.
STD_PROFILE = {'fd': False, 'bitrate': 500000, 'app_name': None}
FD_PROFILE  = {'fd': True, 'timing': j1939_fd_timing, 'app_name': None}

# The Master Channel Dictionary
NETWORK_CONFIGS = {
    'VCAN1':   {'channel': 0, **STD_PROFILE}, 
    'VCAN10':  {'channel': 1, **STD_PROFILE}, 
    'PCAN1':   {'channel': 2, **STD_PROFILE}, 
    'PCAN2':   {'channel': 3, **STD_PROFILE}, 
    'VCAN2':   {'channel': 4, **STD_PROFILE}, 
    'VCAN20':  {'channel': 5, **STD_PROFILE}, 
    'ADSCAN1': {'channel': 6, **FD_PROFILE}, 
    'ADSCAN2': {'channel': 7, **FD_PROFILE}
}

# ==============================================================================
# DATA FLATTENER & PARAMETERIZATION
# ==============================================================================

# environmental variable to input the DBC file path, defaults to "HASI_Primary_ALL_CAN.dbc" in the current directory
primaryDBC_filepath = os.getenv("DBC_PATH", "HASI_Primary_ALL_CAN.dbc")
if not os.path.exists(primaryDBC_filepath):
    raise FileNotFoundError(
        f"\n[FATAL CONFIG ERROR] Could not find DBC file at: '{primaryDBC_filepath}'\n"
        f"Please check your DBC_PATH terminal argument or ensure the default file exists."
    )

# Unpack both dictionaries from the scraper
gatewaySpecDict, messageNameDict = utils.scrape_dbc_for_gateways(primaryDBC_filepath)

test_cases = []
for arbitrationID_raw, channelList in gatewaySpecDict.items():
    
    # Get the message name for terminal display 
    msg_name = messageNameDict.get(arbitrationID_raw, "UNKNOWN_MSG")
    
    # Get arbitration ID in hex format for terminal display 
    masked_id = utils.format_arbitrationID(arbitrationID_raw, "int")
    hex_id = f"0x{masked_id:08X}"
    
    for gatewayChannelPair in channelList:
        sender, receiver = gatewayChannelPair.split(":")
        
        # Determine the gateway protocol translation
        sender_protocol = "CAN-FD" if sender in CAN_FD else "CAN Classic"
        receiver_protocol = "CAN-FD" if receiver in CAN_FD else "CAN Classic"
        gateway_type = f"{sender_protocol} -> {receiver_protocol}"
        
        # terminal label route_pair is just the sender and receiver for easy identification in the terminal summary
        route_pair = f"{sender}:{receiver}"
        
        # Terminal summary format
        terminal_label = f"ROUTE: {route_pair:<25} | GATEWAY TYPE: {gateway_type:<28} | {msg_name:<35} ({hex_id} | Raw: {arbitrationID_raw})"
        
        test_cases.append(pytest.param(sender, receiver, arbitrationID_raw, msg_name, id=terminal_label))

print(f"\n---> WARNING: MAPPED {len(test_cases)} UNIQUE GATEWAY ROUTES <---")

# ==============================================================================
# HARDWARE FIXTURE (FAIL-FAST ARCHITECTURE)
# ==============================================================================

@pytest.fixture(scope="module")
def active_buses():
    """Initializes hardware connections. Uses hard fail-fast if hardware is disconnected."""
    print("\n" + "="*70)
    print(f"INITIALIZING ALL 8 VECTOR CHANNELS (Virtual Mode: {VIRTUAL_MODE})...")
    print("="*70)
    
    ACTIVE_BUSES = {}
    
    try:
        for bus_name, bus_params in NETWORK_CONFIGS.items():
            if VIRTUAL_MODE:
                ACTIVE_BUSES[bus_name] = can.interface.Bus(interface='virtual', channel=bus_name, bitrate=500000)
            else:
                try:
                    ACTIVE_BUSES[bus_name] = vector.VectorBus(**bus_params)
                    print(f" - Successfully opened {bus_name}")
                except (can.CanInitializationError, vector_exceptions.VectorInitializationError) as init_error:
                    # Halt immediately if physical hardware is missing
                    pytest.fail(
                        f"\n[FATAL HARDWARE ERROR] Failed to connect to Vector channel: {bus_name}\n"
                        f"Is the Vector VN1640A physically plugged into the USB port?\n"
                        f"Original Error: {init_error}"
                    )
        
        yield ACTIVE_BUSES

    finally:
        print("\n[Hardware Release] Closing all active channels and shutting down...")
        for bus_name, bus in ACTIVE_BUSES.items():
            if bus is not None:
                try: 
                    bus.shutdown()
                    print(f" - Closed {bus_name}")
                except: 
                    pass

# ==============================================================================
# GATEWAY EXECUTION LOGIC (GATHER-ALL ARCHITECTURE)
# ==============================================================================

@pytest.mark.parametrize("senderName, receiverName, arbitrationID_raw, msg_name", test_cases)
def test_paccar_routing_logic(active_buses, senderName, receiverName, arbitrationID_raw, msg_name, record_property):
    
    # 1. CI/CD Pipeline Tracking Injections
    record_property("sender_node", senderName)
    record_property("receiver_node", receiverName)
    record_property("target_id", arbitrationID_raw)

    sender = active_buses[senderName]
    receiver = active_buses[receiverName]

    is_sender_fd = senderName in CAN_FD
    is_receiver_fd = receiverName in CAN_FD
    
    # --- PROTOCOL IDENTIFIER LOGIC ---
    sender_protocol = "CAN-FD" if is_sender_fd else "CAN Classic"
    receiver_protocol = "CAN-FD" if is_receiver_fd else "CAN Classic"
    gateway_type = f"{sender_protocol} -> {receiver_protocol}"

    int_arbitrationID = int(utils.format_arbitrationID(arbitrationID_raw, "int"))
    dummy_data = [random.randint(0, 255) for _ in range(8)]
    msg = None

    # Format sender message (What goes ONTO the bus)
    if is_sender_fd:
        send_id, send_payload = utils.generate_j1939_22_envelope(int_arbitrationID, dummy_data)
        msg = can.Message(is_rx=False, is_extended_id=True, is_fd=True, bitrate_switch=True, dlc=9, 
                          arbitration_id=send_id, data=send_payload)
    else:
        msg = can.Message(is_rx=False, is_extended_id=True, 
                          arbitration_id=int_arbitrationID, data=dummy_data)
        
    if msg is None:
        pytest.fail(f"FATAL SCRIPT LOGIC: Formatting bypassed for ID {arbitrationID_raw}.")

    # Format receiver message (What comes OFF the bus)
    if is_receiver_fd:
        expected_id, expected_data = utils.generate_j1939_22_envelope(int_arbitrationID, dummy_data)
        expected_is_fd = True
    else:
        expected_id = int_arbitrationID
        expected_data = dummy_data
        expected_is_fd = False

    test_passed = False
    elapsed_time_ms = 0.0

    # 2. Hardware Retry Loop
    print(f"\n=== Testing: {msg_name} | 0x{expected_id:08X} (Raw: {arbitrationID_raw}) ({gateway_type}) ===")
    
    for attempt in range(MAX_RETRIES):
        formatted_send_payload = " ".join(f"{x:02x}" for x in msg.data)
        print(f" [TX] {senderName:<8} : 0x{msg.arbitration_id:08X} ({msg_name}) | {formatted_send_payload} (Attempt {attempt + 1})")

        # Flush the receive buffer to prevent reading stale frames
        while receiver.recv(0.0) is not None:
            pass
        
        start_time = time.time()
        sender.send(msg)
        
        # Virtual Fault Injection Thread
        if VIRTUAL_MODE:
            def fake_hardware_gateway():
                time.sleep(0.015) 
                if random.random() < 0.20:
                    injected_id = expected_id ^ 0xFF 
                else:
                    injected_id = expected_id
                fake_msg = can.Message(is_extended_id=True, is_fd=expected_is_fd, arbitration_id=injected_id, data=expected_data)
                with can.interface.Bus(interface='virtual', channel=receiverName) as dummy_ecu:
                    dummy_ecu.send(fake_msg)

            threading.Thread(target=fake_hardware_gateway, daemon=True).start()

        timeout_end = start_time + ROUTING_TIMEOUT
        found_routed_frame = False
        receivedMessage = None
        
        # Watchdog loop
        while time.time() < timeout_end:
            receivedMessage = receiver.recv(RECV_POLL_RATE) 
            
            if receivedMessage:
                if list(receivedMessage.data) == expected_data:
                    elapsed_time_ms = (time.time() - start_time) * 1000
                    found_routed_frame = True
                    break 
        
        # 3. Soft Evaluation (Logs the error but continues the loop)
        if found_routed_frame and receivedMessage is not None:
            formatted_recv_payload = " ".join(f"{x:02x}" for x in receivedMessage.data)
            print(f"   [RX] {receiverName:<8} : 0x{receivedMessage.arbitration_id:08X} | {formatted_recv_payload}")

            # Mutations on arbitration IDs are marked as failures
            if receivedMessage.arbitration_id == expected_id and receivedMessage.is_fd == expected_is_fd:
                record_property("latency_ms", round(elapsed_time_ms, 2))
                print(f"    [PASS] Routing Successful! ({elapsed_time_ms:.1f} ms) | Expected: 0x{expected_id:08X} == Received: 0x{receivedMessage.arbitration_id:08X}")
                test_passed = True
                break 
            else:
                print(f"    [FAIL / MUTATED] Frame routed, but gateway incorrectly translated the ID/Protocol! ({elapsed_time_ms:.1f} ms)")
                print(f"           Expected   : 0x{expected_id:08X} (FD: {expected_is_fd})")
                print(f"           Received   : 0x{receivedMessage.arbitration_id:08X} (FD: {receivedMessage.is_fd})")
                break # Break retry loop, but let pytest_check flag it as a failure
                
        else:
            print(f"    [FAIL] Gateway dropped the frame (Timeout).")
                
    # 4. Final Non-Blocking Assertion
    # If the hardware never succeeded in MAX_RETRIES attempts, this logs the failure for the terminal summary without crashing the script.
    check.is_true(test_passed, f"Gateway {senderName}:{receiverName} FAILED ID {arbitrationID_raw}.")
