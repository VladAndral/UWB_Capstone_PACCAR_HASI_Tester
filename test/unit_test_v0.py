import utils
import can
import time
import pytest
from can.interfaces import vector
import random
from can.interfaces.vector import exceptions as vector_exceptions
import threading

# If unit_test_v0 is in the root directory, run the test with: pytest unit_test_v0.py -v -s
# If it's in a subdirectory called "test", run with: pytest test/unit_test_v0.py -v -s

# Be sure to check MAX_RETRIES, timeout_end & receivedMessage, these can be adjusted for faster testing during development, but make sure to change them back to the original values for final testing and reporting

# ==============================================================================
# HARDWARE CONFIGURATION
# ==============================================================================

VIRTUAL_MODE = True  # Set to False when plugged into the VN1640A

CAN_CLASSIC = ['VCAN1', 'VCAN10', 'PCAN1', 'PCAN2', 'VCAN2', 'VCAN20']
CAN_FD = ['ADSCAN1', 'ADSCAN2']

# Shared J1939 CAN-FD timing profile
j1939_fd_timing = can.BitTimingFd.from_bitrate_and_segments(
    f_clock=80_000_000, nom_bitrate=500_000, data_bitrate=2_000_000, 
    nom_tseg1=63, nom_tseg2=16, nom_sjw=4, 
    data_tseg1=15, data_tseg2=4, data_sjw=1
)

# Make sure this matches the application name configured in Vector Hardware Manager for the VN1640A channels (Default is "CANoe")
VECTOR_APPLICATION_NAME = 'CANoe'

# Profiles
# STD for J1939 CAN Classic Ports
# FD for J1939-22 CAN Fast Data Ports
STD_PROFILE = {'bitrate': 500000, 'app_name': VECTOR_APPLICATION_NAME}
FD_PROFILE  = {'fd': True, 'timing': j1939_fd_timing, 'app_name': VECTOR_APPLICATION_NAME}

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
# DATA FLATTENER
# ==============================================================================

# Please put HASI_Primary_ALL_CAN.dbc in the same folder as this script!
primaryDBC_filepath = utils.loadFilePath("primaryDBC")
if not isinstance(primaryDBC_filepath, str): 
    raise TypeError("filepath was returned as 'None'")

gatewaySpecDict = utils.scrape_dbc_for_gateways(primaryDBC_filepath)

test_cases = []

# --- 1. MASTER DATA GROUPING LOGIC ---
for arbitrationID_raw, channelList in gatewaySpecDict.items():
    for gatewayChannelPair in channelList:
        sender, receiver = gatewayChannelPair.split(":")
        
        # Create test stack for each gateway route
        # We don't want to group the ID's by route because we want to the test
        # to continue even if one of the ID's in the route fails. If we group them, then one failure would cause us to skip all the ID's in that route. 
        test_cases.append((sender, receiver, arbitrationID_raw))

# Sort the tests by alphabetical order on sender, then receiver, then arbitration ID
test_cases.sort(key=lambda x: (x[0], x[1], x[2]))

print(f"\n---> WARNING: FOUND {len(test_cases)} TEST CASES <---")

# Create human readable test names for each test case to make debugging easier. These will show up in the pytest output.
test_names = []
for sender, receiver, arbitrationID_raw in test_cases:
    test_names.append(f"GATEWAY: {sender}:{receiver} | ID: {arbitrationID_raw}")


# ==============================================================================
# Hardware Fixture
# ==============================================================================

@pytest.fixture(scope="module")
def active_buses():
    
    # --- 2. INITIALIZE ALL 8 CHANNELS ---
    print("\n" + "="*70)
    print("\nINITIALIZING ALL 8 VECTOR CHANNELS...")
    print("="*70)
    
    # Array to hold active physical connections(# of CAN ports on VN1640A, etc.)
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
                    raise RuntimeError(
                        f"\n\n{'!'*70}\n"
                        f"[FATAL HARDWARE ERROR] Failed to connect to Vector channel: {bus_name}\n"
                        f"{'!'*70}\n"
                        f"\nPlease check the following:\n"
                        f"\nIs the Vector VN1640A physically plugged into the USB port?\n"
                        f"\nOriginal Vector Error: {init_error}\n"
                    ) from None
        
        yield ACTIVE_BUSES

    finally:
        # Shutdown of every initialized bus
        print("\n[Hardware Release] Closing all active channels and shutting down...")
        for bus_name, bus in ACTIVE_BUSES.items():
            if bus is not None:
                try: 
                    bus.shutdown()
                    print(f" - Closed {bus_name}")
                except: 
                    pass

# ==============================================================================
# PACCAR GATEWAY TEST SCRIPT (8-CHANNEL FULL AUTOMATION)
# ==============================================================================

@pytest.mark.parametrize("senderName, receiverName, arbitrationID_raw", test_cases, ids=test_names)
def test_paccar_routing_logic(active_buses, senderName, receiverName, arbitrationID_raw):
    
    # --- 3. THE TOPOLOGY EXECUTION LOOP ---
    
    # Point our sender and receiver variables to the already-open buses
    sender = active_buses[senderName]
    receiver = active_buses[receiverName]

    is_sender_fd = senderName in CAN_FD
    is_receiver_fd = receiverName in CAN_FD

    # CAN Signal Injection Logic
    int_arbitrationID = int(utils.format_arbitrationID(arbitrationID_raw, "int"))
    
    # randomized data payload everytime a new arbitration id is put on the bus
    dummy_data = [random.randint(0, 255) for _ in range(8)]
    
    # FORMAT SENDER (What goes ONTO the bus)
    msg = None

    if is_sender_fd:
        send_id, send_payload = utils.generate_j1939_22_envelope(int_arbitrationID, dummy_data)
        msg = can.Message(is_rx=False, is_extended_id=True, is_fd=True, bitrate_switch=True, dlc=9, 
                          arbitration_id=send_id, data=send_payload)
    else:
        # I accidentally deleted this...
        msg = can.Message(is_rx=False, is_extended_id=True, 
                          arbitration_id=int_arbitrationID, data=dummy_data)
        
    # if msg isn't formatted correctly according to is_sender_fd boolean, then I want to throw an error so I know that the boolean is the issue
    if msg is None:
        pytest.fail(f"FATAL SCRIPT LOGIC: Formatting bypassed for ID {arbitrationID_raw}. Halting to prevent ghost frame injection.")

    # FORMAT RECEIVER (What comes OFF the bus)
    if is_receiver_fd:
        expected_id, expected_data = utils.generate_j1939_22_envelope(int_arbitrationID, dummy_data)
        expected_is_fd = True
    else:
        expected_id = int_arbitrationID
        expected_data = dummy_data
        expected_is_fd = False
    
    # --- 5. EXECUTION & RETRY LOGIC ---
    MAX_RETRIES = 1 # Set to 1 for development, but change to 5 for final testing and reporting
    found_routed_frame = False
    receivedMessage = None
    
    # want to check how long it takes for a pass to test
    elapsed_time_ms = 0.0

    for attempt in range(MAX_RETRIES):
        formatted_send_payload = " ".join(f"{x:02x}" for x in msg.data)
        print(f"\n -> Sending to {senderName}  : 0x{msg.arbitration_id:08X} | {formatted_send_payload} (Attempt {attempt + 1})")

        # flush receiver at the start of each gateway test attempt by
        # checking the receiver for CAN messages, until there's nothing being received
        # THEN we start inject the new CAN message
        while receiver.recv(0.0) is not None:
            pass
        
        # =========================================================
        # SOFTWARE MOCK FOR VIRTUAL TESTING
        # =========================================================
        # Get Current time
        start_time = time.time()
        
        sender.send(msg)
        
        # =========================================================
        # SOFTWARE MOCK FOR VIRTUAL TESTING (WITH FAULT INJECTION)
        # =========================================================
        if VIRTUAL_MODE:
            
            def mock_hardware_gateway():
                # Simulate hardware processing latency
                time.sleep(0.015) 
                
                # Random Fault Injection
                # 20% change to inject a fault by corrupting the arbitration ID, which should cause the test to fail
                # Want to check if test holds up against random data corruption
                if random.random() < 0.20:
                    injected_id = expected_id ^ 0xFF # Flip bits to corrupt ID
                else:
                    injected_id = expected_id
                    
                # 3. Build the translated frame
                fake_msg = can.Message(
                    is_extended_id=True,
                    is_fd=expected_is_fd,
                    arbitration_id=injected_id,
                    data=expected_data
                )
                
                # 4. Temporarily attach to the receiver's channel to inject the frame
                with can.interface.Bus(interface='virtual', channel=receiverName) as dummy_ecu:
                    dummy_ecu.send(fake_msg)

            # Fire off the mock ECU in the background so the main test loop can immediately start listening
            threading.Thread(target=mock_hardware_gateway, daemon=True).start()
        # =========================================================

        # Find current time then add 1.0 seconds to it
        # change 1.0 to 0.05 for faster timeout during development...
        timeout_end = start_time + 0.05

        # watchdog timer for checking receiving bus for however long the difference is between time() and timeout_end
        while time.time() < timeout_end:
            # change timeout value in recv() to 0.01 for faster checking during development, but make sure to change it back to 0.1 for final testing and reporting since some frames can take a while to route through the gateway
            receivedMessage = receiver.recv(0.01)

            # With randomized data, we can now check which ECU CAN port actually received the payload
            if receivedMessage and list(receivedMessage.data) == expected_data:
                elapsed_time_ms = (time.time() - start_time) * 1000
                found_routed_frame = True
                break
        
        if found_routed_frame:
            break

    # --- EVALUATION ---
    
    if not found_routed_frame:
        pytest.fail(f"[FAIL] Timeout: Frame injected on {senderName} failed to appear on {receiverName} within {timeout_end - start_time:.2f}s.")

    formatted_recv_payload = " ".join(f"{x:02x}" for x in receivedMessage.data)
    print(f" <- Received on {receiverName}: 0x{receivedMessage.arbitration_id:08X} | {formatted_recv_payload}")

    # Check against dynamic expected_id
    assert receivedMessage.arbitration_id == expected_id, \
        f"[PASS / MUTATED] Frame was routed, but gateway translated the ID Unexpectedly! Expected: 0x{expected_id:08X}, Got: 0x{receivedMessage.arbitration_id:08X}"
    
    assert receivedMessage.is_fd == expected_is_fd, \
        f"[PASS / MUTATED] Protocol translated! Expected FD: {expected_is_fd}, Got FD: {receivedMessage.is_fd}"

    # change wording of [PASS] to better reflect gateway test case
    if is_sender_fd and not is_receiver_fd:
        print(f"    [PASS] Routing Successful (FD Envelope Unpacked)! ({elapsed_time_ms:.1f} ms)")
    elif not is_sender_fd and is_receiver_fd:
        print(f"    [PASS] Routing Successful (FD Envelope Packed)! ({elapsed_time_ms:.1f} ms)")
    else:
        print(f"    [PASS] Routing Successful (Arbitration ID Preserved)! ({elapsed_time_ms:.1f} ms)")