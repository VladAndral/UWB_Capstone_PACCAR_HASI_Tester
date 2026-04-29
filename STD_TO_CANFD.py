import utils, can, sys, traceback
from can.interfaces import vector

# Will use this to wrap code intended for use in UWB test environment(2 CH vector device) vs PACCAR lab environment(8 CH vector device)
PACCAR_HIL_ENVIRONMENT = False

CAN_STD = ['VCAN1', 'VCAN10', 'PCAN1', 'PCAN2', 'VCAN2', 'VCAN20']
CAN_FD = ['ADSCAN1', 'ADSCAN2']

SENDER_CHANNEL = 1 
RECEIVER_CHANNEL = 0

def run__injection_gateway_test():
    
    # Copy file path of .dbc being used and put in line underneath "PRIMARYGATEWAYDBC", "SECONDARYGATEWAYDBC", etc. in filepath.txt
    # Don't forget quotation marks around the file path in filepath.txt
    primaryDBC_filepath = utils.loadFilePath("primaryDBC")
    if not isinstance(primaryDBC_filepath, str): 
        raise TypeError("filepath was returned as 'None'")

    # Dictionary of all gateways. Key=arbitrationID, value=list of channels gatewayed
    gatewaySpecDict = utils.scrape_dbc_for_gateways(primaryDBC_filepath)
    
    # Bit timing configuration for CAN-FD, according to error code when script ran while locked by CANoe
    timing = can.BitTimingFd.from_bitrate_and_segments(
        f_clock=80_000_000,
        nom_bitrate=500_000,
        nom_tseg1=63,
        nom_tseg2=16,
        nom_sjw=4,
        data_bitrate=2_000_000,
        data_tseg1=15,
        data_tseg2=4,
        data_sjw=1,
    )
    
    # Initalize sender and receiver variables to None so that they can be safely shutdown in the except block, even if initialization fails and they aren't assigned a bus object
    sender = None
    receiver = None
    
    # Channel initialization
    try:
        # Either set serial from Vector Hardware Manager or set app_name to "Canoe"
        # Sender is standard CAN
        # Set to CH1 for sender(locked by vector hardware for some reason)
        sender = vector.VectorBus(serial=535823, 
                                  channel=SENDER_CHANNEL, 
                                  bitrate=500000)
                    
        # Either set serial from Vector Hardware Manager or set app_name to "Canoe"
        # Set to CH0 for receiver(locked by vector hardware for some reason)
        # Arbitration bitrate is 500 kbps, but data bitrate is 2 Mbps
        # Enabled CAN-FD
        # Set timing=timing if needed
        receiver = vector.VectorBus(serial=535823, 
                                    channel=RECEIVER_CHANNEL, 
                                    fd=True,
                                    timing=timing)
    
    # This error usually only happens if CANoe is running and has locked the channels
    except can.exceptions.CanInitializationError as hardware_error:
        print("\n[Hardware Initialization Error]")
        print("Check if CANoe measurement is running in the background and holding channels hostage")
        print(f"Hardware initialization error: {hardware_error}")
        
        # Just in case sender initialization worked but receiver initialization didn't, or vice versa
        print("Releasing any used channels...")
        if sender is not None:
            sender.shutdown()
        if receiver is not None:
            receiver.shutdown()
        
        # Script end on hardware initialization failure to prevent any further errors from trying to use uninitialized channels   
        sys.exit(1)
    
    # Arbitrary data payload, can change if needed
    dummy_data = [0x12, 0x34, 0x56, 0x78, 0x9A, 0xBC, 0xDE, 0xFF]

    # Injection logic
    try:
        # --- 1. DATA GROUPING LOGIC ---
        # Reorganize the dictionary to group all IDs by their specific route
        route_groups = {}
        
        for arbitrationID_raw, channelList in gatewaySpecDict.items():
            for gatewayChannelPair in channelList:
                
                eachChannel = gatewayChannelPair.split(":")
                senderName = eachChannel[0]
                receiverName = eachChannel[1]
                
                # Filters for only Standard CAN to CAN-FD routes
                if senderName in CAN_STD and receiverName in CAN_FD:
                    route_pair = (senderName, receiverName)
                    
                    # If this route isn't in our new dictionary yet, add it
                    if route_pair not in route_groups:
                        route_groups[route_pair] = []
                        
                    # Append the ID to this specific route's list
                    route_groups[route_pair].append(arbitrationID_raw)


        # --- 2. OPTIMIZED TESTING LOOP ---
        # The outer loop now iterates through the physical networks
        for route_pair, id_list in route_groups.items():
            senderName = route_pair[0]
            receiverName = route_pair[1]
            
            # --- THE DYNAMIC CABLE SWAP PROMPT ---
            # Because of the outer loop, this is guaranteed to only fire ONCE per route
            print(f"\n" + "="*60)
            print(f" NEW ROUTE DETECTED: {senderName} -> {receiverName} ({len(id_list)} IDs grouped)")
            print(f" Please physically plug SENDER (CH {SENDER_CHANNEL}) into {senderName}")
            print(f" Please physically plug RECEIVER (CH {RECEIVER_CHANNEL}) into {receiverName}")
            print("="*60)
            input("Press Enter when cables are physically secure...")
            
            # The inner loop blasts through all the IDs for this specific connection
            for arbitrationID_raw in id_list:
                
                int_arbitrationID = int(utils.format_arbitrationID(arbitrationID_raw, "int"))

                # is_rx=False means it's a message being sent, not received
                # is_extended_id=True means it's using 29-bit extended IDs, which is needed for J1939
                # Set arbitration id to whatever ID is being put on the bus by the sender
                # Arbitrary data payload, can change if needed
                msg = can.Message(is_rx=False, 
                                  is_extended_id=True, 
                                  arbitration_id=int_arbitrationID, 
                                  data=dummy_data)
                
                # Prompt user for arbitration id injection
                input(f"Press enter to inject original ID 0x{int_arbitrationID:08X} ")
                sender.send(msg)
                
                # print the payload similar to receivedMessage 
                formatted_payload = " ".join(f"{x:02x}" for x in msg.data)
                print(f"Sender {senderName} sent:        ID: 0x{msg.arbitration_id:08X}            {formatted_payload}        Channel: {SENDER_CHANNEL}")
        
                # Wait up to 1 seconds for a message
                receivedMessage = receiver.recv(1)  
        
                if receivedMessage:
                    print(f"PASS! Receiver {receiverName} saw: {receivedMessage}")
                else:
                    # FAIL1 if standard CAN message not put on bus at all
                    print(f"FAIL1: Gateway {senderName} to {receiverName} with arbitrationID_raw {arbitrationID_raw} failed.")
    
    except Exception as general_error:
        print("\n[Script Error]")
        print(f"The script crashed: {general_error}")
        
        # --- UNMASK THE HIDDEN LINE NUMBER ---
        print("\n[Stack Trace Diagnostics]")
        traceback.print_exc()
                
    finally:
        # Need to release CAN channels 
        # Very important to prevent channel lock issues
        # Can cause problems with having to switch channels being used as receiver and sender
        print("\nShutting down sender and receiver channels...")
        if sender is not None: 
            sender.shutdown()
        if receiver is not None: 
            receiver.shutdown()

if __name__ == "__main__":
    run__injection_gateway_test()