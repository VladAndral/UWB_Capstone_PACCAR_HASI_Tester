import utils
import can
import time
import traceback
from can.interfaces import vector
import random
from can.interfaces.vector import exceptions as vector_exceptions

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

# Array to hold active physical connections(# of CAN ports on VN1640A, etc.)
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
                
                # Using the sender:receiver pair as the key for grouping all arbitration IDs that share the same gateway route
                sender, receiver = gatewayChannelPair.split(":")
                route_pair = (sender, receiver)
                
                if route_pair not in route_groups:
                    route_groups[route_pair] = []
                route_groups[route_pair].append(arbitrationID_raw)

        # --- GATEWAY ROUTE SANITY CHECK ---
        print("\n" + "="*70)
        print("PARSED GATEWAY ROUTES FROM DBC FILE")
        print("="*70)
        for route_pair, id_list in route_groups.items():
            # Using :<8 to perfectly align the arrows in the terminal
            print(f" - Mapped Route: {route_pair[0]:<8} -> {route_pair[1]:<8} | {len(id_list)} IDs")
        print("-" * 70)
        print(f" Total Unique Routing Paths: {len(route_groups)}") 

        # --- 2. INITIALIZE ALL 8 CHANNELS
        print("\n" + "="*70)
        print("INITIALIZING ALL 8 VECTOR CHANNELS...")
        print("="*70)
        for bus_name, bus_params in NETWORK_CONFIGS.items():
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
                    raise RuntimeError(f"FATAL SCRIPT LOGIC: Formatting bypassed for ID {arbitrationID_raw}. Halting to prevent ghost frame injection.")

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
                    # --- EVALUATION ---
                    if found_routed_frame:
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
                            # --- THE FIX: Changed PASS to FAIL and removed test_passed = True ---
                            print(f"    [FAIL / MUTATED] Frame routed, but gateway dangerously translated the ID/Protocol! ({elapsed_time_ms:.1f} ms)")
                            print(f"           Expected   : 0x{expected_id:08X} (FD: {expected_is_fd})")
                            print(f"           Received   : 0x{receivedMessage.arbitration_id:08X} (FD: {receivedMessage.is_fd})\n")
                            # By breaking here without setting test_passed = True, the script officially logs it as a FAILED ID
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