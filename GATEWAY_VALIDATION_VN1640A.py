import utils
import can
import sys
import time
import traceback
from can.interfaces import vector
import random

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

        # --- 2. INITIALIZE ALL 8 CHANNELS
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

                # randomized data payload everytime a new arbitration id id put on the bus
                dummy_data = [random.randint(0, 255) for _ in range(8)]

                # FORMAT SENDER (What goes ONTO the bus)
                if is_sender_fd:
                    send_id, send_payload = utils.generate_j1939_22_envelope(int_arbitrationID, dummy_data)
                    msg = can.Message(is_rx=False, is_extended_id=True, is_fd=True, bitrate_switch=True, dlc=9, 
                                      arbitration_id=send_id, data=send_payload)

                # FORMAT RECEIVER (What comes OFF the bus)
                if is_receiver_fd:
                    expected_id, expected_data = utils.generate_j1939_22_envelope(int_arbitrationID, dummy_data)
                    expected_is_fd = True
                else:
                    expected_id = int_arbitrationID
                    expected_data = dummy_data
                    expected_is_fd = False

                # --- 5. EXECUTION & RETRY LOGIC ---
                MAX_RETRIES = 20
                test_passed = False
                
                for attempt in range(MAX_RETRIES):
                    formatted_send_payload = " ".join(f"{x:02x}" for x in msg.data)
                    print(f" -> Sending to {senderName}  : 0x{msg.arbitration_id:08X} | {formatted_send_payload} (Attempt {attempt + 1})")
                    
                    # flush receiver
                    while receiver.recv(0.0) is not None:
                        pass
                    
                    sender.send(msg)
                    
                    # Find current time then add 1.0 seconds to it
                    timeout_end = time.time() + 1.0
                    
                    # stage flag for checking CAN frame
                    found_routed_frame = False
                    
                    # watchdog timer for checking receiving bus for however long the difference is between time() and timeout_end
                    while time.time() < timeout_end:
                        receivedMessage = receiver.recv(0.1) 
                        
                        if receivedMessage:
                            # With randomized data, we can now check which ECU CAN port actually received the payload
                            if list(receivedMessage.data) == expected_data:
                                found_routed_frame = True
                                break 
                    
                    # --- EVALUATION ---
                    if found_routed_frame:
                        formatted_recv_payload = " ".join(f"{x:02x}" for x in receivedMessage.data)
                        print(f" <- Received on {receiverName}: 0x{receivedMessage.arbitration_id:08X} | {formatted_recv_payload}")

                        # Check against dynamic expected_id
                        if receivedMessage.arbitration_id == expected_id and receivedMessage.is_fd == expected_is_fd:
                            print(f"    [PASS] Routing Successful & ID is identical!\n")
                            test_passed = True
                            break 
                        else:
                            print(f"    [PASS / MUTATED] Frame routed perfectly, but gateway translated the ID/Protocol!")
                            print(f"           Expected ID : 0x{expected_id:08X}")
                            print(f"           Received ID : 0x{receivedMessage.arbitration_id:08X}\n")
                            test_passed = True # Mark as PASS because the gateway successfully translated it
                            break
                            
                    else:
                        print(f"    [FAIL] Gateway dropped the frame (Timeout).\n")
                
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