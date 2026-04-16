# type "pytest unit_pytest.py -v -s" into terminal

import pytest
import utils, can, sys
from can.interfaces import vector

# Keep globals identical across scripts
CAN_STD = ['VCAN1', 'VCAN10', 'PCAN1', 'PCAN2', 'VCAN2', 'VCAN20']
CAN_FD = ['ADSCAN1', 'ADSCAN2']

SENDER_CHANNEL = 1
RECEIVER_CHANNEL = 0

# Global tracker for pytest to know when the route changes across different test cases
CURRENT_NETWORK_PAIR = None

# --- 1. DATA EXTRACTION ---
def get_all_classic_to_fd_tests():
    
    # Copy file path of .dbc being used and put in line underneath "PRIMARYGATEWAYDBC" in filepath.txt
    # Don't forget quotation marks around the file path
    primaryDBC_filepath = utils.loadFilePath("primaryDBC")
    if not isinstance(primaryDBC_filepath, str): 
        raise TypeError("filepath was returned as 'None'")

    gatewaySpecDict = utils.scrape_dbc_for_gateways(primaryDBC_filepath)
    
    # This will hold tuples of (senderName, receiverName, arbitrationID_raw)
    test_cases = []
    
    for arbitrationID_raw, channelList in gatewaySpecDict.items():
        for gatewayChannelPair in channelList:
            
            eachChannel = gatewayChannelPair.split(":")
            senderName = eachChannel[0]
            receiverName = eachChannel[1]
            
            # Filter for all Standard CAN to CAN-FD routes
            if senderName in CAN_STD and receiverName in CAN_FD:
                test_cases.append((senderName, receiverName, arbitrationID_raw))
                
    # Sort the list alphabetically by senderName, then receiverName.
    # This guarantees all IDs for a specific route are tested consecutively!
    test_cases.sort(key=lambda x: (x[0], x[1]))
    
    return test_cases

# List of valid test cases for pytest to iterate over
TEST_CASES_LIST = get_all_classic_to_fd_tests()


# --- 2. HARDWARE SETUP & TEARDOWN ---

# Using module scope so the buses initialize ONCE for all tests
@pytest.fixture(scope="module")
def sender_bus():
    sender = None
    try:
        # Sender is standard CAN
        # Set to CH1 for sender
        sender = vector.VectorBus(serial=535823, 
                                  channel=SENDER_CHANNEL, 
                                  bitrate=500000)
        
        yield sender
        
    except can.exceptions.CanInitializationError as hardware_error:
        print("\n[Hardware Initialization Error]")
        print("Check if CANoe measurement is running in the background")
        pytest.exit(f"Stopping test suite: {hardware_error}")
        
    finally:
        print("\nShutting down sender channel...")
        if sender is not None:
            sender.shutdown()


@pytest.fixture(scope="module")
def receiver_bus():
    # Bit timing configuration for CAN-FD
    timing = can.BitTimingFd.from_bitrate_and_segments(
        f_clock=80_000_000, 
        nom_bitrate=500_000, 
        nom_tseg1=63, 
        nom_tseg2=16, 
        nom_sjw=4, 
        data_bitrate=2_000_000, 
        data_tseg1=15, 
        data_tseg2=4, 
        data_sjw=1
    )
    
    receiver = None
    try:
        # Receiver is CAN-FD
        # Set to CH0 for receiver
        # Set timing=timing
        receiver = vector.VectorBus(serial=535823, 
                                    channel=RECEIVER_CHANNEL,  
                                    fd=True, 
                                    timing=timing)
        yield receiver
        
    except can.exceptions.CanInitializationError as hardware_error:
        pytest.exit(f"Stopping test suite: {hardware_error}")
        
    finally:
        print("Shutting down receiver channel...")
        if receiver is not None:
            receiver.shutdown()


# --- 3. INJECTION LOGIC ---

# Pytest will automatically loop this function, unpacking the tuple for every test
@pytest.mark.parametrize("senderName, receiverName, arbitrationID_raw", TEST_CASES_LIST)
def test_classic_to_fd_routing(senderName, receiverName, arbitrationID_raw, sender_bus, receiver_bus):
    
    global CURRENT_NETWORK_PAIR
    
    # --- THE DYNAMIC CABLE SWAP PROMPT ---
    if (senderName, receiverName) != CURRENT_NETWORK_PAIR:
        print(f"\n" + "="*60)
        print(f" NEW ROUTE DETECTED: {senderName} -> {receiverName}")
        print(f" Please physically plug SENDER (CH {SENDER_CHANNEL}) into {senderName}")
        print(f" Please physically plug RECEIVER (CH {RECEIVER_CHANNEL}) into {receiverName}")
        print("="*60)
        input("Press Enter when cables are physically secure...")
        CURRENT_NETWORK_PAIR = (senderName, receiverName)

    
    int_arbitrationID = int(utils.format_arbitrationID(arbitrationID_raw, "int"))
    
    # Standard payload
    # Arbitrary data, can change if needed
    # randomize data for more robust testing?
    dummyData = [0x12, 0x34, 0x56, 0x78, 0x9A, 0xBC, 0xDE, 0xFF]

    msg = can.Message(is_rx=False, 
                      is_extended_id=True, 
                      arbitration_id=int_arbitrationID, 
                      data=dummyData)
    
    sender_bus.send(msg)
    
    # Optional visual terminal printout if using the -s flag
    formatted_payload = " ".join(f"{x:02x}" for x in msg.data)
    print(f"Sender {senderName} sent:        ID: 0x{msg.arbitration_id:08X}            {formatted_payload}        Channel: {SENDER_CHANNEL}")
    
    # Wait up to 0.5 seconds for a message
    receivedMessage = receiver_bus.recv(0.5)
    
    # Assert acts as our pass/fail condition for pytest
    assert receivedMessage is not None, f"FAIL1: Gateway {senderName} to {receiverName} dropped ID 0x{int_arbitrationID:08X}"
    
    # summary at end(implement please)