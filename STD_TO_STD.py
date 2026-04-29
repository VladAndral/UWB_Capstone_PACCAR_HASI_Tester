import utils, sys, can, re
from can.interfaces import vector


def run__injection_gateway_test():
    """Test script that loops through all gateway networks, injecting CAN messages
        into each bus, and listening on one bus to see if the message was sent

    Args:
        isVirtualInterface (bool): Option to force a virtual interface,
        even if hardware like Vector or Kvaser are connected
    """
    
    # Get the config info from one of the channels on the Vector hardware
    config_ch1 = str(can.detect_available_configs(interfaces=['vector'])[0])
    
    # Find the exact string 'bitrate=#####', focusing on the number (creating a group)
    channelBitrate = re.search(r"bitrate=(\d+)", config_ch1 )
    
    # Only get the string captured in the group (the number; the bitrate)
    if channelBitrate: channelBitrate = channelBitrate.group(1)
    if isinstance(channelBitrate, str):
        BITRATE_CONST = int(channelBitrate)
    else:
        # If what was returned from channelBitrate.group(1) was not a string, don't use it
        raise TypeError("Error returning string from regex searching for bitrate")
    
    # load the dbc filepath entered in filepath.txt
    primaryDBC_filepath = utils.loadFilePath("primaryDBC")
    if not isinstance(primaryDBC_filepath, str): raise TypeError("filepath was returned as 'None'")
    
    # Dictionary of all gateways. Key=arbitrationID, value=list of channels gatewayed
    gatewaySpecDict = utils.scrape_dbc_for_gateways(primaryDBC_filepath)

    for arbitrationID_raw, channelList in gatewaySpecDict.items():
        # Formatting arbitrationID and converting to int format for python-can to use
        int_arbitrationID = int(utils.format_arbitrationID(arbitrationID_raw, "int"))
        
        msg = can.Message(is_rx = False, is_extended_id=True, arbitration_id=int_arbitrationID)
        # msg = can.Message(is_rx = False, is_extended_id=True, arbitration_id=int_arbitrationID, data=[0x00]*8)
        
        # There may be multiple gateways for one arbitrationID
        for gatewayChannelPair in channelList:
            # Splitting this current channel, e.g. "CAN1:CAN2" --> ["CAN1", "CAN2"]
            eachChannel = gatewayChannelPair.split(":")
            senderName = eachChannel[0]
            receiverName = eachChannel[1]
            # This if branch is only for testing non CAN FD ports ADSCAN#, since they require special handling/formatting
            if senderName[0] == ('V' or 'P') and receiverName[0] == ('V' or 'P'):
                
                print("\nThis gateway pair: {} to {}. Order matters. (arbID {})".format(senderName, receiverName, arbitrationID_raw))
                input("Press enter when switched. Test outputs will be affected if the switch is not made.")
            
                sender = vector.VectorBus(serial=535823, channel=0, bitrate = BITRATE_CONST)
                receiver = vector.VectorBus(serial=535823, channel=1, bitrate = BITRATE_CONST)
                
                try:
                    sender.send(msg)
                except can.exceptions.CanOperationError:
                    print(f"Error: {senderName} busObject encountered an error sending message with raw arbID {hex(int(arbitrationID_raw))} .")
                    print(msg)
                else:  # If no exception was raised
                    # If the message was received, the recv() function will return the message received
                    try:
                        receivedMessage = receiver.recv(0.25)
                    except can.exceptions.CanOperationError:
                        print(f"Error: {receiverName} busObject encountered an error trying to receive or acknowledge any sent messages.")
                    else:  # If no exception was raised
                        if receivedMessage is None:
                            print(f"FAIL1: Specified gateway {senderName} to {receiverName} with arbitrationID_raw {hex(int(arbitrationID_raw))} failed.")
                        else: 
                            print(receivedMessage)
                    
                
                # Always shutdown the VectorBus'es
                finally:
                    sender.shutdown()
                    receiver.shutdown()

if __name__ == "__main__":
    run__injection_gateway_test()