import utils, sys, can, re
from can.interfaces import vector

dbc_ID = 2633727015
print(f"initial arbID: {dbc_ID}")
formattedID = int(utils.format_arbitrationID(str(dbc_ID), "int"))
print(f"formatted id: {formattedID}")
FD_formattedID = utils.convertFD_toCAN(formattedID)
print(f"result: {hex(FD_formattedID)}")


def run__injection_gateway_test():
    
    # load the dbc filepath entered in filepath.txt
    primaryDBC_filepath = utils.loadFilePath("primaryDBC")
    if not isinstance(primaryDBC_filepath, str): raise TypeError("filepath was returned as 'None'")
    
    # Dictionary of all gateways. Key=arbitrationID, value=list of channels gatewayed
    gatewaySpecDict = utils.scrape_dbc_for_gateways(primaryDBC_filepath)
    
    print(f"Found {len(gatewaySpecDict)} gateway IDs in DBC.")
    if len(gatewaySpecDict) == 0:
        return

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
            if senderName in ('ADSCAN1', 'ADSCAN2') or receiverName in ('ADSCAN1', 'ADSCAN2'):
                
                print("\nThis gateway pair: {} to {}. Order matters. (arbID {})".format(senderName, receiverName, arbitrationID_raw))
                input("Press enter when switched. Test outputs will be affected if the switch is not made.")
            
                sender = vector.VectorBus(serial=535823, channel=0, bitrate = 500000)
                receiver = vector.VectorBus(serial=535823, channel=1, bitrate = 500000)
                
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
    