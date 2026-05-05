import utils, can, sys, traceback
from can.interfaces import vector

# Will use this to wrap code intended for use in UWB test environment(2 CH vector device) vs PACCAR lab environment(8 CH vector device)
PACCAR_HIL_ENVIRONMENT = False

# We use this explicit list instead of regex or string slicing to ensure we catch all PCAN and VCAN variants reliably
CAN_STD = ['VCAN1', 'VCAN10', 'PCAN1', 'PCAN2', 'VCAN2', 'VCAN20']

SENDER_CHANNEL = 0
RECEIVER_CHANNEL = 1

def run__injection_gateway_test():
    
    # Copy file path of .dbc being used and put in line underneath "PRIMARYGATEWAYDBC", "SECONDARYGATEWAYDBC", etc. in filepath.txt
    primaryDBC_filepath = utils.loadFilePath("primaryDBC")
    if not isinstance(primaryDBC_filepath, str): 
        raise TypeError("filepath was returned as 'None'")

    # Dictionary of all gateways. Key=arbitrationID, value=list of channels gatewayed
    gatewaySpecDict = utils.scrape_dbc_for_gateways(primaryDBC_filepath)
    
    # Initalize sender and receiver variables to None so they can be safely shutdown in the except block
    sender = None
    receiver = None
    
    
    # Channel initialization (Moved OUTSIDE the loops for hardware stability)
    try:
        # Sender is standard CAN
        sender = vector.VectorBus(serial = allChannelConfigs[0]["serial"],
                                  channel = SENDER_CHANNEL, 
                                  bitrate = 500000)
                    
        # Receiver is standard CAN
        receiver = vector.VectorBus(channel=RECEIVER_CHANNEL, 
                                    bitrate=500000
                                    )
    
    except can.exceptions.CanInitializationError as hardware_error:
        print("\n[Hardware Initialization Error]")
        print("Check if CANoe measurement is running in the background and holding channels hostage")
        print(f"Hardware initialization error: {hardware_error}")
        
        print("Releasing any used channels...")
        if sender is not None: sender.shutdown()
        if receiver is not None: receiver.shutdown()
        sys.exit(1)
    
    # Arbitrary data payload
    dummy_data = [0x12, 0x34, 0x56, 0x78, 0x9A, 0xBC, 0xDE, 0xFF]

    # Injection logic
    try:
        # --- 1. DATA GROUPING LOGIC ---
        route_groups = {}
        
        for arbitrationID_raw, channelList in gatewaySpecDict.items():
            for gatewayChannelPair in channelList:
                
                eachChannel = gatewayChannelPair.split(":")
                senderName = eachChannel[0]
                receiverName = eachChannel[1]
                
                # Filter for strictly Standard CAN to Standard CAN routes
                if senderName in CAN_STD and receiverName in CAN_STD:
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

                # is_rx=False means it's a message being sent
                # is_extended_id=True means 29-bit extended IDs for J1939
                msg = can.Message(is_rx = False, 
                                  is_extended_id = True, 
                                  arbitration_id = int_arbitrationID, 
                                  data = dummy_data)
                
                sender.send(msg)
                
                formatted_payload = " ".join(f"{x:02x}" for x in msg.data)
                print(f"Sender {senderName} sent:        ID: 0x{msg.arbitration_id:08X}            {formatted_payload}        Channel: {SENDER_CHANNEL}")
        
                # Wait up to 1 seconds for a message
                receivedMessage = receiver.recv(1.0)  
        
                if receivedMessage:
                    
                    # Validation logic (Since this is Std to Std, no J1939-22 envelopes exist. It should be a 1:1 echo)
                    is_data_intact = list(receivedMessage.data) == dummy_data
                    is_correct_id = receivedMessage.arbitration_id == int_arbitrationID
                    is_standard_can = not receivedMessage.is_fd

                    if is_data_intact and is_correct_id and is_standard_can:
                        print(f"PASS! Receiver {receiverName} saw: {receivedMessage}")
                    else:
                        print(f"FAIL2: Frame routed, but data/protocol was mutated by the gateway.")
                        print(f"   Expected ID: 0x{int_arbitrationID:08X} | Got: 0x{receivedMessage.arbitration_id:08X}")
                        print(f"   Expected FD: False | Got FD: {receivedMessage.is_fd}")
                else:
                    print(f"FAIL1: Gateway {senderName} to {receiverName} with arbitrationID_raw {arbitrationID_raw} dropped the frame.")
    
    except Exception as general_error:
        print("\n[Script Error]")
        print(f"The script crashed: {general_error}")
        print("\n[Stack Trace Diagnostics]")
        traceback.print_exc()
                
    finally:
        # Shut down once per execution, not per ID
        print("\nShutting down sender and receiver channels...")
        if sender is not None: sender.shutdown()
        if receiver is not None: receiver.shutdown()

if __name__ == "__main__":
    # run__injection_gateway_test()
        # Get the config info from one of the channels on the Vector hardware
    allChannelConfigs = (can.detect_available_configs(interfaces=['vector']))
    print(allChannelConfigs[0]["serial"])
    print(allChannelConfigs[0]["vector_channel_config"])
    print(allChannelConfigs[0]["vector_channel_config"].bus_params.can.bitrate)
    # sender = vector.VectorBus(allChannelConfigs[0]["vector_channel_config"])
    # for listItem in config_ch:
    #     print(listItem)