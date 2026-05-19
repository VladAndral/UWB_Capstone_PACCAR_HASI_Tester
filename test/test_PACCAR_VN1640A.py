import utils
import can
import time
from can.interfaces import vector
import random
from can.interfaces.vector import exceptions as vector_exceptions
import pytest
import pytest_check as check

# type: "pytest test_PACCAR_VN1640A.py -v -s" in terminal to run
# type: "python -m pytest test/test_PACCAR_VN1640A.py --junitxml=report.xml" in terminal to generate XML

# ==============================================================================
# HARDWARE CONFIGURATION
# ==============================================================================

CAN_CLASSIC = ['VCAN1', 'VCAN10', 'PCAN1', 'PCAN2', 'VCAN2', 'VCAN20']
CAN_FD = ['ADSCAN1', 'ADSCAN2']

# Shared J1939 CAN-FD timing profile
j1939_fd_timing = can.BitTimingFd.from_bitrate_and_segments(
    f_clock=80_000_000, nom_bitrate=500_000, data_bitrate=2_000_000, 
    nom_tseg1=63, nom_tseg2=16, nom_sjw=4, 
    data_tseg1=15, data_tseg2=4, data_sjw=1
)

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
# PACCAR GATEWAY TEST SCRIPT (8-CHANNEL FULL AUTOMATION)
# ==============================================================================

# Please put HASI_Primary_ALL_CAN.dbc in the same folder as this script!
primaryDBC_filepath = utils.loadFilePath("primaryDBC")
if not isinstance(primaryDBC_filepath, str): 
    raise TypeError("filepath was returned as 'None'")

gatewaySpecDict = utils.scrape_dbc_for_gateways(primaryDBC_filepath)

# --- 1. MASTER DATA GROUPING LOGIC ---
route_groups = {}
for arbitrationID_raw, channelList in gatewaySpecDict.items():
    for gatewayChannelPair in channelList:
        eachChannel = gatewayChannelPair.split(":")
        route_pair = (eachChannel[0], eachChannel[1])
        
        if route_pair not in route_groups:
            route_groups[route_pair] = []
        route_groups[route_pair].append(arbitrationID_raw)

# Create Tuple for pytest.mark.parametrize() function unpacking
TEST_CASES_LIST = []
for (sender, receiver), all_IDs in route_groups.items():
    group_count = len(all_IDs)

    for arb_ID in all_IDs:
        terminal_label = f"{sender} to {receiver} - {arb_ID}"
        TEST_CASES_LIST.append(pytest.param(sender, receiver, arb_ID, group_count, id=terminal_label))

# --- GATEWAY ROUTE SANITY CHECK ---
print("\n" + "="*70)
print("PARSED GATEWAY ROUTES FROM DBC FILE")
print("="*70)
for route_pair, id_list in route_groups.items():
    # Using :<8 to perfectly align the arrows in the terminal
    print(f" - Mapped Route: {route_pair[0]:<8} -> {route_pair[1]:<8} | {len(id_list)} IDs")
print("-" * 70)
print(f" Total Unique Routing Paths: {len(route_groups)}") 

# ==============================================================================
# HARDWARE SETUP FIXTURE
# ==============================================================================

@pytest.fixture(scope="module")
def bus_dict():
    buses = {}
    # --- 2. INITIALIZE ALL 8 CHANNELS
    print("\n" + "="*70)
    print("INITIALIZING ALL 8 VECTOR CHANNELS...")
    print("="*70)
    for bus_name, bus_params in NETWORK_CONFIGS.items():
        try:
            buses[bus_name] = vector.VectorBus(**bus_params)
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
        
    yield buses

    # Shutdown of every initialized bus
    print("\n[Hardware Release] Closing all active channels and shutting down...")
    for bus_name, bus in buses.items():
        if bus is not None:
            try: 
                bus.shutdown()
                print(f" - Closed {bus_name}")
            except: 
                pass
    
@pytest.mark.parametrize("senderName, receiverName, arbitrationID_raw, group_count", TEST_CASES_LIST)
def test_VN1640A(senderName, receiverName, arbitrationID_raw, group_count, bus_dict):
    print(f"\n" + "-"*70)
    print(f" TESTING Gateway: {senderName} to {receiverName} ({group_count} IDs grouped)")
    print("-"*70)

    is_sender_fd = senderName in CAN_FD
    is_receiver_fd = receiverName in CAN_FD

    sender = bus_dict[senderName]
    receiver = bus_dict[receiverName]

    int_arbitrationID = int(utils.format_arbitrationID(arbitrationID_raw, "int"))

    # if msg isn't formatted correctly according to is_sender_fd boolean, then I want to throw an error so I know that the boolean is the issue
    msg = None

    # randomized data payload everytime a new arbitration id id put on the bus
    dummy_data = [random.randint(0, 255) for _ in range(8)]

  # FORMAT SENDER (What goes ONTO the bus)
    if is_sender_fd:
        send_id, send_payload = utils.generate_j1939_22_envelope(int_arbitrationID, dummy_data)
        msg = can.Message(is_rx=False, is_extended_id=True, is_fd=True, bitrate_switch=True, dlc=9, 
                            arbitration_id=send_id, data=send_payload)
    else:
        # I accidentally deleted this...
        msg = can.Message(is_rx=False, is_extended_id=True, 
                            arbitration_id=int_arbitrationID, data=dummy_data)
        
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
    MAX_RETRIES = 5
    test_passed = False
    
    for attempt in range(MAX_RETRIES):
        formatted_send_payload = " ".join(f"{x:02x}" for x in msg.data)
        print(f" -> Sending to {senderName}  : 0x{msg.arbitration_id:08X} | {formatted_send_payload} (Attempt {attempt + 1})")
        
        # flush receiver at the start of each gateway test attempt by
        # checking the receiver for CAN messages, until there's nothing being received
        # THEN we start inject the new CAN message
        while receiver.recv(0.0) is not None:
            pass
        
        # Get Current time
        start_time = time.time()
        
        sender.send(msg)
        
        # Find current time then add 1.0 seconds to it
        timeout_end = start_time + 1.0
        
        # stage flag for checking CAN frame
        found_routed_frame = False
        
        # want to check how long it takes for a pass to test
        elapsed_time_ms = 0.0
        
        # watchdog timer for checking receiving bus for however long the difference is between time() and timeout_end
        while time.time() < timeout_end:
            receivedMessage = receiver.recv(0.1) 
            
            if receivedMessage:
                # With randomized data, we can now check which ECU CAN port actually received the payload
                if list(receivedMessage.data) == expected_data:
                    elapsed_time_ms = (time.time() - start_time) * 1000
                    found_routed_frame = True
                    break 
        
        # --- EVALUATION ---
        if found_routed_frame and receivedMessage is not None:
            formatted_recv_payload = " ".join(f"{x:02x}" for x in receivedMessage.data)
            print(f" <- Received on {receiverName}: 0x{receivedMessage.arbitration_id:08X} | {formatted_recv_payload}")

            # Check against dynamic expected_id
            if receivedMessage.arbitration_id == expected_id and receivedMessage.is_fd == expected_is_fd:
                
                # change wording of [PASS] to better reflect gateway test case
                if is_sender_fd and not is_receiver_fd:
                    print(f"    [PASS] Routing Successful (FD Envelope Unpacked)! ({elapsed_time_ms:.1f} ms) | Target: 0x{expected_id:08X} == Received: 0x{receivedMessage.arbitration_id:08X}\n")
                elif not is_sender_fd and is_receiver_fd:
                    print(f"    [PASS] Routing Successful (FD Envelope Packed)! ({elapsed_time_ms:.1f} ms) | Expected: 0x{expected_id:08X} == Received: 0x{receivedMessage.arbitration_id:08X}\n")
                else:
                    print(f"    [PASS] Routing Successful (Logical ID Verified)! ({elapsed_time_ms:.1f} ms) | Expected: 0x{expected_id:08X} == Received: 0x{receivedMessage.arbitration_id:08X}\n")
                test_passed = True
                break 
            else:
                
                print(f"    [PASS / MUTATED] Frame routed perfectly, but gateway translated the ID/Protocol! ({elapsed_time_ms:.1f} ms)")
                print(f"           Expected ID : 0x{expected_id:08X}")
                print(f"           Received ID : 0x{receivedMessage.arbitration_id:08X}\n")
                test_passed = True 
                break
                
        else:
            print(f"    [FAIL] Gateway dropped the frame (Timeout).\n")
    
    check.is_true(test_passed, f"    [FAIL] Gateway {senderName} to {receiverName} FAILED ID {arbitrationID_raw}.")
    
    if not test_passed:
        print(f"--> FINAL RESULT: Gateway {senderName} to {receiverName} FAILED ID {arbitrationID_raw}.")
    
def pytest_terminal_summary(terminalreporter, exitstatus, config):
    stats = terminalreporter.stats

    if 'failed' in stats:
        numFails = len(stats['failed'])
        print(f"\n" + "="*60)
        print(f" GATEWAY TEST SUMMARY ({numFails} FAILED) ")
        print(f"="*60)

        print(f"Sender-Receiver-ArbitrationID")
        for test in stats['failed']:
            # Check if failure is parameterized test
            if '[' in test.nodeid:
                tx_rx_arb = test.nodeid.split('[')[-1].rstrip(']')
                print(f"{tx_rx_arb}")
            else:
                print(f"{test.nodeid}")
        
        print(f"="*60)