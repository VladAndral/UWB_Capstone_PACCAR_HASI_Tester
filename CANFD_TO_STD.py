import utils, can, sys, traceback
from can.interfaces import vector

# Will use this to wrap code intended for use in UWB test environment(2 CH vector device) vs PACCAR lab environment(8 CH vector device)
PACCAR_HIL_ENVIRONMENT = False

CAN_STD = ['VCAN1', 'VCAN10', 'PCAN1', 'PCAN2', 'VCAN2', 'VCAN20']
CAN_FD = ['ADSCAN1', 'ADSCAN2']

SENDER_CHANNEL = 0
RECEIVER_CHANNEL = 1

def run__injection_gateway_test():
    
    # Copy file path of .dbc being used and put in line underneath "PRIMARYGATEWAYDBC", "SECONDARYGATEWAYDBC", etc. in filepath.txt
    primaryDBC_filepath = utils.loadFilePath("primaryDBC")
    if not isinstance(primaryDBC_filepath, str):
        raise TypeError("filepath was returned as 'None'")

    # Dictionary of all gateways. Key=arbitrationID, value=list of channels gatewayed
    gatewaySpecDict = utils.scrape_dbc_for_gateways(primaryDBC_filepath)
    
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

    sender = None
    receiver = None

    # Channel initialization
    try:
        # Sender is CAN-FD
        sender = vector.VectorBus(channel=SENDER_CHANNEL, 
                                  fd=True, 
                                  timing=timing)
        
        # Receiver is standard CAN 
        receiver = vector.VectorBus(channel=RECEIVER_CHANNEL, 
                                    bitrate=500000)

    except can.exceptions.CanInitializationError as hardware_error:
        print("\n[Hardware Initialization Error]")
        print("Check if CANoe measurement is running in the background and holding channels hostage")
        print(f"Hardware initialization error: {hardware_error}")
        
        print("Releasing any used channels...")
        if sender is not None: sender.shutdown()
        if receiver is not None: receiver.shutdown()
        sys.exit(1)

    # Standard payload
    dummy_data = [0x12, 0x34, 0x56, 0x78, 0x9A, 0xBC, 0xDE, 0xFF]

    # Injection logic
    try:
        # --- 1. DATA GROUPING LOGIC (Imported from Script 2) ---
        route_groups = {}
        
        for arbitrationID_raw, channelList in gatewaySpecDict.items():
            for gatewayChannelPair in channelList:
                
                eachChannel = gatewayChannelPair.split(":")
                senderName = eachChannel[0]
                receiverName = eachChannel[1]
                
                # Filters for only CAN-FD to Standard CAN routes
                if senderName in CAN_FD and receiverName in CAN_STD:
                    route_pair = (senderName, receiverName)
                    
                    if route_pair not in route_groups:
                        route_groups[route_pair] = []
                        
                    route_groups[route_pair].append(arbitrationID_raw)

        # --- 2. OPTIMIZED TESTING LOOP ---
        for route_pair, id_list in route_groups.items():
            senderName = route_pair[0]
            receiverName = route_pair[1]
            
            # --- THE DYNAMIC CABLE SWAP PROMPT ---
            print(f"\n" + "="*60)
            print(f" NEW ROUTE DETECTED: {senderName} -> {receiverName} ({len(id_list)} IDs grouped)")
            print(f" Please physically plug SENDER (CH {SENDER_CHANNEL}) into {senderName}")
            print(f" Please physically plug RECEIVER (CH {RECEIVER_CHANNEL}) into {receiverName}")
            print("="*60)
            
            # Pause ONCE before the route testing begins
            input("Press Enter when cables are physically secure to blast all IDs... ")

            for arbitrationID_raw in id_list:
                
                int_arbitrationID = int(utils.format_arbitrationID(arbitrationID_raw, "int"))

                # J1939-22 Container formatting logic (Packing the envelope before sending)
                pdu_format = (int_arbitrationID >> 16) & 0xFF
                pdu_specific = (int_arbitrationID >> 8) & 0xFF

                if pdu_format < 240:
                    byte_2 = 0x00
                    container_ps = pdu_specific
                else:
                    byte_2 = pdu_specific
                    container_ps = 0xFF
                
                header = [0x40, pdu_format, byte_2, 0x08]

                priority_edp_dp_sa = int_arbitrationID & 0x1F0000FF
                envelope_id = priority_edp_dp_sa | (0x25 << 16) | (container_ps << 8)

                container_payload = header + dummy_data
                
                msg = can.Message(
                    is_rx=False, 
                    is_extended_id=True, 
                    arbitration_id=envelope_id,
                    is_fd=True, 
                    bitrate_switch=True, 
                    dlc=9, 
                    data=container_payload
                )
                
                sender.send(msg)

                formatted_payload = " ".join(f"{x:02x}" for x in msg.data)
                print(f"Sender {senderName} sent:        ID: 0x{msg.arbitration_id:08X}            {formatted_payload}        Channel: {SENDER_CHANNEL}")

                receivedMessage = receiver.recv(1.0)

                if receivedMessage:
                    
                    # Validation logic (Checking if it unpacked successfully)
                    is_unpacked = (receivedMessage.arbitration_id == int_arbitrationID and
                                   list(receivedMessage.data) == dummy_data and
                                   not receivedMessage.is_fd) 

                    if is_unpacked:
                        print(f"PASS! Receiver {receiverName} saw: {receivedMessage}")
                    else:
                        print(f"FAIL2: Frame routed, but the gateway failed to unpack the J1939-22 container.")
                        print(f"   Expected ID: 0x{int_arbitrationID:08X} | Got: 0x{receivedMessage.arbitration_id:08X}")
                        print(f"   Expected FD: False | Got FD: {receivedMessage.is_fd}")
                        
                else:
                    print(f"FAIL1: Gateway {senderName} to {receiverName} with arbitrationID_raw {arbitrationID_raw} failed.")
    
    except Exception as general_error:
        print("\n[Script Error]")
        print(f"The script crashed: {general_error}")
        print("\n[Stack Trace Diagnostics]")
        traceback.print_exc()

    finally:
        print("\nShutting down sender and receiver channels...")
        if sender is not None: sender.shutdown()
        if receiver is not None: receiver.shutdown()

if __name__ == "__main__":
    run__injection_gateway_test()