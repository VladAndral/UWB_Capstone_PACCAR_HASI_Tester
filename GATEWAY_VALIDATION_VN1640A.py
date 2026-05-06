import utils
import can
import sys
import traceback
from can.interfaces import vector

# Be Sure to Install python-can
# pip install python-can

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

# Global array to hold all 8 active physical connections
ACTIVE_BUSES = {}

# ==============================================================================
# PACCAR GATEWAY TEST SCRIPT (8-CHANNEL FULL AUTOMATION)
# ==============================================================================

def run_paccar_hil_test():
    global ACTIVE_BUSES
    
    # Please put HASI_Primary_ALL_CAN.dbc in the same folder as this script!
    primaryDBC_filepath = utils.loadFilePath("primaryDBC")
    if not isinstance(primaryDBC_filepath, str): 
        raise TypeError("filepath was returned as 'None'")

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

        # --- 2. INITIALIZE ALL 8 CHANNELS (PASSIVE LISTENERS) ---
        print("\n" + "="*70)
        print(" [PACCAR LAB] INITIALIZING ALL 8 VECTOR CHANNELS...")
        print("="*70)
        for bus_name, bus_params in NETWORK_CONFIGS.items():
            ACTIVE_BUSES[bus_name] = vector.VectorBus(**bus_params)
            print(f" - Successfully opened {bus_name}")

        # --- 3. THE TOPOLOGY EXECUTION LOOP ---
        for route_pair, id_list in route_groups.items():
            senderName = route_pair[0]
            receiverName = route_pair[1]
            
            is_sender_fd = senderName in CAN_FD
            is_receiver_fd = receiverName in CAN_FD
            
            # Point our sender and receiver variables to the already-open buses
            sender = ACTIVE_BUSES[senderName]
            receiver = ACTIVE_BUSES[receiverName]

            print(f"\n" + "-"*70)
            print(f" TESTING Gateway: {senderName} to {receiverName} ({len(id_list)} IDs grouped)")
            print("-"*70)

            # CAN Signal Injection Logic
            for arbitrationID_raw in id_list:
                int_arbitrationID = int(utils.format_arbitrationID(arbitrationID_raw, "int"))

                # FORMAT SENDER (What goes ONTO the bus)
                if is_sender_fd:
                    send_id, send_payload = utils.generate_j1939_22_envelope(int_arbitrationID, dummy_data)
                    msg = can.Message(is_rx=False, is_extended_id=True, is_fd=True, bitrate_switch=True, dlc=9, 
                                      arbitration_id=send_id, data=send_payload)
                else:
                    msg = can.Message(is_rx=False, is_extended_id=True, 
                                      arbitration_id=int_arbitrationID, data=dummy_data)

                # FORMAT RECEIVER (What comes OFF the bus)
                if is_receiver_fd:
                    expected_id, expected_data = utils.generate_j1939_22_envelope(int_arbitrationID, dummy_data)
                    expected_is_fd = True
                else:
                    expected_id = int_arbitrationID
                    expected_data = dummy_data
                    expected_is_fd = False

                # --- 5. EXECUTION & RETRY LOGIC ---
                MAX_RETRIES = 3
                test_passed = False
                
                for attempt in range(MAX_RETRIES):
                    # --- NEW: Print exactly what is going onto the wire ---
                    formatted_send_payload = " ".join(f"{x:02x}" for x in msg.data)
                    print(f" -> Sending to {senderName}: 0x{msg.arbitration_id:08X} | {formatted_send_payload} (Attempt {attempt + 1})")
                    
                    sender.send(msg)
                    receivedMessage = receiver.recv(1.0)

                    if receivedMessage:
                        is_correct_id = receivedMessage.arbitration_id == expected_id
                        is_data_intact = list(receivedMessage.data) == expected_data
                        is_correct_protocol = receivedMessage.is_fd == expected_is_fd

                        if is_correct_id and is_data_intact and is_correct_protocol:
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
            
    except Exception as general_error:
        print("\n[Script Error] The script crashed:")
        traceback.print_exc()
        
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

if __name__ == "__main__":
    run_paccar_hil_test()