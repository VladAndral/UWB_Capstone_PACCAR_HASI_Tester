import utils
import can
import sys
import traceback
from can.interfaces import vector

# ==============================================================================
# ENVIRONMENT & HARDWARE CONFIGURATION
# ==============================================================================

# Set to True if All 8 CAN Ports are Connected to a Vector Hardware Device Simultaneously(Double VN1640A Setup)
# Set to False if Using VN1610 + CANcable 2Y Setup
PACCAR_HIL_ENVIRONMENT = True

CAN_STD = ['VCAN1', 
           'VCAN10', 
           'PCAN1', 
           'PCAN2', 
           'VCAN2', 
           'VCAN20']

CAN_FD = ['ADSCAN1', 
          'ADSCAN2']

# Channels for VN1610A + CANcable 2Y Setup
SENDER_CHANNEL = 0
RECEIVER_CHANNEL = 1

# Shared J1939 CAN-FD timing profile to keep the dictionary clean
j1939_fd_timing = can.BitTimingFd.from_bitrate_and_segments(
    f_clock=80_000_000, nom_bitrate=500_000, data_bitrate=2_000_000, 
    nom_tseg1=63, nom_tseg2=16, nom_sjw=4, 
    data_tseg1=15, data_tseg2=4, data_sjw=1
)

# Change This to the Application Name specified in Application Channels Configuration in Vector Hardware Manager
VECTOR_APPLICATION_NAME = 'CANoe'

# J1939 CAN Extended Classic Profile
STD_PROFILE = {'bitrate': 500000, 'app_name': VECTOR_APPLICATION_NAME}

# J1939 CAN Extended FD(Fast Data) Profile
FD_PROFILE  = {'fd': True, 'timing': j1939_fd_timing, 'app_name': VECTOR_APPLICATION_NAME}

# 2. Unpack them into the specific physical channels
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

# Global array to hold all active physical connections
ACTIVE_BUSES = {}

# ==============================================================================
# MAIN GATEWAY TEST SCRIPT
# ==============================================================================

def run_injection_gateway_test():
    global ACTIVE_BUSES
    
    primaryDBC_filepath = utils.loadFilePath("primaryDBC")
    if not isinstance(primaryDBC_filepath, str): 
        raise TypeError("filepath was returned as 'None'")

    # Dictionary of all gateways. Key=arbitrationID, value=list of channels gatewayed
    gatewaySpecDict = utils.scrape_dbc_for_gateways(primaryDBC_filepath)
    
    dummy_data = [0x12, 0x34, 0x56, 0x78, 0x9A, 0xBC, 0xDE, 0xFF]

    try:
        # --- 1. MASTER DATA GROUPING LOGIC ---
        route_groups = {}
        for arbitrationID_raw, channelList in gatewaySpecDict.items():
            for gatewayChannelPair in channelList:
                eachChannel = gatewayChannelPair.split(":")
                route_pair = (eachChannel[0], eachChannel[1])
                
                if route_pair not in route_groups:
                    route_groups[route_pair] = []
                route_groups[route_pair].append(arbitrationID_raw)


        # --- 2. THE TOPOLOGY EXECUTION LOOP ---
        for route_pair, id_list in route_groups.items():
            senderName = route_pair[0]
            receiverName = route_pair[1]
            
            is_sender_fd = senderName in CAN_FD
            is_receiver_fd = receiverName in CAN_FD
            
            # --- DYNAMIC HARDWARE INITIALIZATION ---
            sender = None
            receiver = None
            try:
                if PACCAR_HIL_ENVIRONMENT:
                    # [8-CHANNEL MULTICAST FIX]
                    # If the dictionary is empty, initialize ALL 8 channels once and leave them open.
                    if not ACTIVE_BUSES:
                        print(f"\n" + "="*70)
                        print(" INITIALIZING ALL 8 VECTOR CHANNELS FOR MULTICAST ACKs...")
                        print("="*70)
                        for bus_name, bus_params in NETWORK_CONFIGS.items():
                            ACTIVE_BUSES[bus_name] = vector.VectorBus(**bus_params)

                    # Grab the specific buses needed for this injection
                    sender = ACTIVE_BUSES[senderName]
                    receiver = ACTIVE_BUSES[receiverName]
                    
                    print(f"\n" + "="*70)
                    print(f" TESTING ROUTE: {senderName} -> {receiverName} ({len(id_list)} IDs grouped)")
                    print("="*70)
                    
                else:
                    # [2-CHANNEL MANUAL OVERRIDE SETUP]
                    # Shut down the previous route's buses before swapping cables
                    for bus in ACTIVE_BUSES.values():
                        bus.shutdown()
                    ACTIVE_BUSES.clear()
                    
                    print(f"\n" + "="*70)
                    print(f" [MANUAL OVERRIDE] 2-Channel Test Bench Detected")
                    print(f" Please physically plug SENDER (CH {SENDER_CHANNEL}) into {senderName}")
                    print(f" Please physically plug RECEIVER (CH {RECEIVER_CHANNEL}) into {receiverName}")
                    print("="*70)
                    input("Press Enter when cables are physically secure to blast IDs... ")
                    
                    # Copy the dictionary parameters so we don't accidentally overwrite the master config
                    tx_params = NETWORK_CONFIGS[senderName].copy()
                    rx_params = NETWORK_CONFIGS[receiverName].copy()
                    
                    # Override the physical channels to match the 2-channel box
                    tx_params['channel'] = SENDER_CHANNEL
                    rx_params['channel'] = RECEIVER_CHANNEL

                    # Unpack and Initialize
                    sender = vector.VectorBus(**tx_params)
                    receiver = vector.VectorBus(**rx_params)
                    
                    # Store them so they can be cleaned up on the next loop or at the end
                    ACTIVE_BUSES[senderName] = sender
                    ACTIVE_BUSES[receiverName] = receiver
                    
            except can.exceptions.CanInitializationError as hardware_error:
                print(f"\n[Hardware Error] Failed to configure Vector channels for {senderName} to {receiverName}.")
                print(f"Error details: {hardware_error}")
                sys.exit(1)

            # --- 3. THE INJECTION LOOP ---
            for arbitrationID_raw in id_list:
                int_arbitrationID = int(utils.format_arbitrationID(arbitrationID_raw, "int"))

                # ---------------------------------------------------------
                # Routing Topologies
                # ---------------------------------------------------------
                
                # 1. FORMAT SENDER (What goes ONTO the bus)
                if is_sender_fd:
                    send_id, send_payload = utils.generate_j1939_22_envelope(int_arbitrationID, dummy_data)
                    msg = can.Message(is_rx=False, is_extended_id=True, is_fd=True, bitrate_switch=True, dlc=9, 
                                      arbitration_id=send_id, data=send_payload)
                else:
                    msg = can.Message(is_rx=False, is_extended_id=True, 
                                      arbitration_id=int_arbitrationID, data=dummy_data)

                # 2. FORMAT RECEIVER (What comes OFF the bus)
                if is_receiver_fd:
                    expected_id, expected_data = utils.generate_j1939_22_envelope(int_arbitrationID, dummy_data)
                    expected_is_fd = True
                else:
                    expected_id = int_arbitrationID
                    expected_data = dummy_data
                    expected_is_fd = False

                # ---------------------------------------------------------
                # EXECUTION & RETRY LOGIC
                # ---------------------------------------------------------
                MAX_RETRIES = 3
                test_passed = False
                
                for attempt in range(MAX_RETRIES):
                    sender.send(msg)
                    receivedMessage = receiver.recv(1.0)  

                    if receivedMessage:
                        is_correct_id = receivedMessage.arbitration_id == expected_id
                        is_data_intact = list(receivedMessage.data) == expected_data
                        is_correct_protocol = receivedMessage.is_fd == expected_is_fd

                        if is_correct_id and is_data_intact and is_correct_protocol:
                            # Format payload cleanly for printing
                            formatted_payload = " ".join(f"{x:02x}" for x in receivedMessage.data)
                            print(f"PASS! {receiverName} received: 0x{receivedMessage.arbitration_id:08X} | {formatted_payload} (Attempt {attempt + 1})")
                            test_passed = True
                            break 
                        else:
                            print(f"Attempt {attempt + 1}: FAIL2 - Frame routed, but data/protocol mutated incorrectly.")
                    else:
                        print(f"Attempt {attempt + 1}: FAIL1 - Gateway dropped the frame (Timeout).")
                
                if not test_passed:
                    print(f"--> FINAL RESULT: Gateway {senderName} to {receiverName} FAILED ID {arbitrationID_raw}.")
                    print("-" * 50)
            
            # (Notice there is NO hardware shutdown here! The loop just smoothly continues.)
            
    except Exception as general_error:
        print("\n[Script Error] The script crashed:")
        traceback.print_exc()
        
    finally:
        # --- TRUE HARDWARE TEARDOWN ---
        # This only runs when EVERY route is finished, or if the script crashes.
        print("\n[Hardware Release] Closing all active channels and shutting down...")
        for bus_name, bus in ACTIVE_BUSES.items():
            if bus is not None:
                try: 
                    bus.shutdown()
                    print(f" - Closed {bus_name}")
                except: 
                    pass

if __name__ == "__main__":
    run_injection_gateway_test()