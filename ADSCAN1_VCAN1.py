import utils, can, sys, traceback
from can.interfaces import vector

CAN_STD = ['VCAN1', 'VCAN10', 'PCAN1', 'PCAN2', 'VCAN2', 'VCAN20']
CAN_FD = ['ADSCAN1', 'ADSCAN2']

SENDER_CHANNEL = 0
RECEIVER_CHANNEL = 1

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
        data_sjw=1
    )

    # Initalize sender and receiver variables to None so that they can be safely shutdown in the except block, even if initialization fails and they aren't assigned a bus object
    sender = None
    receiver = None

    # Channel initialization
    try:
        # Sender is CAN-FD 
        # Enabled CAN-FD
        # Set timing=timing if needed
        sender = vector.VectorBus(serial=535823, 
                                  channel=SENDER_CHANNEL, 
                                  fd=True, 
                                  timing=timing)
        
        # Receiver is standard CAN 
        receiver = vector.VectorBus(serial=535823, 
                                    channel=RECEIVER_CHANNEL, 
                                    bitrate=500000)

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

    # Standard payload
    # Arbitrary data, can change if needed
    dummy_data = [0x12, 0x34, 0x56, 0x78, 0x9A, 0xBC, 0xDE, 0xFF]

    # Injection logic
    try:
        for arbitrationID_raw, channelList in gatewaySpecDict.items():
            
            int_arbitrationID = int(utils.format_arbitrationID(arbitrationID_raw, "int"))

            for gatewayChannelPair in channelList:
                senderName, receiverName = gatewayChannelPair.split(":")

                # Hardcoded to only test ADSCAN1:VCAN1
                if senderName == "ADSCAN1" and receiverName == "VCAN1":
                    
                    # J1939-22 Container formatting logic
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
                    
                    # envelope_id = utils.convertFD_toCAN(int_arbitrationID)

                    # is_rx=False means it's a message being sent, not received
                    # is_extended_id=True means it's using 29-bit extended IDs, which is needed for J1939
                    # Set arbitration id to whatever ID is being put on the bus by the sender which is now envelope_id
                    # Arbitrary data payload, can change if needed
                    # is_fd=True means it's a CAN-FD frame
                    # bitrate_switch=True means that the frame will switch to the data bitrate after the arbitration phase, which is needed for CAN-FD
                    # dlc = 9 means byte length 12(4 byte header + 8 byte dummy data) container
                    msg = can.Message(
                        is_rx=False, 
                        is_extended_id=True, 
                        arbitration_id=envelope_id,
                        is_fd=True, 
                        bitrate_switch=True, 
                        dlc=9, 
                        data=container_payload
                    )
                    
                    # Prompt user for arbitration id injection
                    input(f"Press enter to inject original ID 0x{int_arbitrationID:08X} ")
                            # Lockup
                    sender.send(msg)

                    # print the payload similar to receivedMessage 
                    formatted_payload = " ".join(f"{x:02x}" for x in msg.data)
                    print(f"Sender {senderName} sent:        ID: 0x{msg.arbitration_id:08X}            {formatted_payload}        Channel: {SENDER_CHANNEL}")

                    # Wait up to 1 seconds for a message
                    receivedMessage = receiver.recv(1.0)

                    if receivedMessage:
                        
                        is_unpacked = (receivedMessage.arbitration_id == int_arbitrationID and
                                       list(receivedMessage.data) == dummy_data and #receivedMessage.data should be a list since dummy_data is a list
                                       not receivedMessage.is_fd) # unpacked message should be standard CAN, not CAN-FD

                        # Check if CAN FD message was unpacked by HASI ECU
                        if is_unpacked:
                            print(f"PASS! Receiver {receiverName} saw: {receivedMessage}")
                        else:
                            # FAIL2 if Frame was put on the bus but HASI didn't unpack it correctly
                            print(f"FAIL2: Frame routed, but the gateway failed to unpack the J1939-22 container.")
                            print(f"   Expected ID: 0x{int_arbitrationID:08X} | Got: 0x{receivedMessage.arbitration_id:08X}")
                            
                    else:
                        # FAIL1 if CAN FD message not put on bus at all
                        print(f"FAIL1: Gateway {senderName} to {receiverName} with arbitrationID_raw {arbitrationID_raw} failed.")
    
    except Exception as general_error:
        print("\n[Script Error]")
        print(f"The script crashed: {general_error}")
        
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