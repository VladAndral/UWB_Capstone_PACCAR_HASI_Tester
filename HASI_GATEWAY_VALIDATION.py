import utils
import can
import sys
import traceback
from can.interfaces import vector

# ==============================================================================
# ENVIRONMENT & HARDWARE CONFIGURATION
# ==============================================================================

# Toggle this to True when you are physically in the PACCAR lab with all 8 channels connected.
# Leave it False when testing at home with your 2-channel Y-splitter.
PACCAR_HIL_ENVIRONMENT = False

CAN_STD = ['VCAN1', 'VCAN10', 'PCAN1', 'PCAN2', 'VCAN2', 'VCAN20']
CAN_FD = ['ADSCAN1', 'ADSCAN2']

# Fallback channels for the 2-Channel home bench
SENDER_CHANNEL = 0
RECEIVER_CHANNEL = 1

# Shared J1939 CAN-FD timing profile to keep the dictionary clean
j1939_fd_timing = can.BitTimingFd.from_bitrate_and_segments(
    f_clock=80_000_000, nom_bitrate=500_000, data_bitrate=2_000_000, 
    nom_tseg1=63, nom_tseg2=16, nom_sjw=4, 
    data_tseg1=15, data_tseg2=4, data_sjw=1
)

VECTOR_APPLICATION_NAME = 'CANoe'

# The Permanent Digital Twin of the PACCAR Lab
NETWORK_CONFIGS = {
    'VCAN1':   {'channel': 0, 'bitrate': 500000, 'app_name': VECTOR_APPLICATION_NAME}, 
    'VCAN10':  {'channel': 1, 'bitrate': 500000, 'app_name': VECTOR_APPLICATION_NAME}, 
    'PCAN1':   {'channel': 2, 'bitrate': 500000, 'app_name': VECTOR_APPLICATION_NAME}, 
    'PCAN2':   {'channel': 3, 'bitrate': 500000, 'app_name': VECTOR_APPLICATION_NAME}, 
    'VCAN2':   {'channel': 4, 'bitrate': 500000, 'app_name': VECTOR_APPLICATION_NAME}, 
    'VCAN20':  {'channel': 5, 'bitrate': 500000, 'app_name': VECTOR_APPLICATION_NAME}, 
    'ADSCAN1': {'channel': 6, 'fd': True, 'timing': j1939_fd_timing, 'app_name': VECTOR_APPLICATION_NAME}, 
    'ADSCAN2': {'channel': 7, 'fd': True, 'timing': j1939_fd_timing, 'app_name': VECTOR_APPLICATION_NAME}
}

# ==============================================================================
# MAIN EXECUTION ENGINE
# ==============================================================================

def run_injection_gateway_test():
    
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
                    # [FULLY AUTOMATED PACCAR SETUP]
                    print(f"\n" + "="*70)
                    print(f" TESTING ROUTE: {senderName} -> {receiverName} ({len(id_list)} IDs grouped)")
                    print("="*70)
                    
                    tx_params = NETWORK_CONFIGS[senderName]
                    rx_params = NETWORK_CONFIGS[receiverName]
                    
                else:
                    # [MANUAL FALLBACK SETUP]
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
                    
            except can.exceptions.CanInitializationError as hardware_error:
                print(f"\n[Hardware Error] Failed to configure Vector channels for {senderName}->{receiverName}.")
                print(f"Error details: {hardware_error}")
                if sender is not None: sender.shutdown()
                if receiver is not None: receiver.shutdown()
                sys.exit(1)


            # --- 3. THE INJECTION LOOP ---
            for arbitrationID_raw in id_list:
                int_arbitrationID = int(utils.format_arbitrationID(arbitrationID_raw, "int"))

                # ---------------------------------------------------------
                # TOPOLOGY ROUTING LOGIC (Format Payload & Set Expectations)
                # ---------------------------------------------------------
                
                # BRANCH A: CAN-FD to Standard (Reverse Routing)
                if is_sender_fd and not is_receiver_fd:
                    envelope_id, envelope_payload = utils.generate_j1939_22_envelope(int_arbitrationID, dummy_data)
                    msg = can.Message(is_rx=False, is_extended_id=True, is_fd=True, bitrate_switch=True, dlc=9, 
                                      arbitration_id=envelope_id, data=envelope_payload)
                    
                    expected_id = int_arbitrationID
                    expected_data = dummy_data
                    expected_is_fd = False

                # BRANCH B: Standard to CAN-FD (Forward Routing)
                elif not is_sender_fd and is_receiver_fd:
                    msg = can.Message(is_rx=False, is_extended_id=True, 
                                      arbitration_id=int_arbitrationID, data=dummy_data)
                    
                    expected_envelope_id, expected_envelope_payload = utils.generate_j1939_22_envelope(int_arbitrationID, dummy_data)
                    expected_id = expected_envelope_id
                    expected_data = expected_envelope_payload
                    expected_is_fd = True

                # BRANCH C: Standard to Standard (Classic Routing)
                elif not is_sender_fd and not is_receiver_fd:
                    msg = can.Message(is_rx=False, is_extended_id=True, 
                                      arbitration_id=int_arbitrationID, data=dummy_data)
                    
                    expected_id = int_arbitrationID
                    expected_data = dummy_data
                    expected_is_fd = False
                    
                # BRANCH D: CAN-FD to CAN-FD (Passthrough)
                else:
                    envelope_id, envelope_payload = utils.generate_j1939_22_envelope(int_arbitrationID, dummy_data)
                    msg = can.Message(is_rx=False, is_extended_id=True, is_fd=True, bitrate_switch=True, dlc=9, 
                                      arbitration_id=envelope_id, data=envelope_payload)
                    
                    expected_id = envelope_id
                    expected_data = envelope_payload
                    expected_is_fd = True

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
            
            # --- SHUTDOWN BEFORE NEXT TOPOLOGY ---
            print(f"\n[Hardware Release] Closing channels for {senderName} -> {receiverName}...")
            sender.shutdown()
            receiver.shutdown()
    
    except Exception as general_error:
        print("\n[Script Error] The script crashed:")
        traceback.print_exc()
        
        if 'sender' in locals() and sender is not None: sender.shutdown()
        if 'receiver' in locals() and receiver is not None: receiver.shutdown()

if __name__ == "__main__":
    # run_injection_gateway_test()
    allChannelConfigs = (can.detect_available_configs(interfaces=['vector']))
    # print(allChannelConfigs[0]["serial"])
    sender = vector.VectorBus(**allChannelConfigs[1])
    print(sender.channel_info)
    sender.shutdown()