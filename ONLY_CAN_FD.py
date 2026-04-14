import utils, sys, can, re
from can.interfaces import vector

def run__injection_gateway_test():
    primaryDBC_filepath = utils.loadFilePath("primaryDBC")
    if not isinstance(primaryDBC_filepath, str): raise TypeError("filepath was returned as 'None'")

    gatewaySpecDict = utils.scrape_dbc_for_gateways(primaryDBC_filepath)

    for arbitrationID_raw, channelList in gatewaySpecDict.items():
        
        # Testing arbitrationID 2565799706 (0x18EEFF1A) 
        raw_id_as_int = int(arbitrationID_raw)
        if raw_id_as_int != 2565799706:
            continue
            
        int_arbitrationID = int(utils.format_arbitrationID(arbitrationID_raw, "int"))
        
        # Dummy data from
        dummy_data = [0x12, 0x34, 0x56, 0x78, 0x9A, 0xBC, 0xDE, 0xFF]
        msg = can.Message(is_rx=False, 
                          is_extended_id=True, 
                          arbitration_id=int_arbitrationID, 
                          data=dummy_data)
        
        for gatewayChannelPair in channelList:
            eachChannel = gatewayChannelPair.split(":")
            senderName = eachChannel[0]
            receiverName = eachChannel[1]
            
            # Hardcoded to only test arbitrationID 2565799706 between VCAN2:ADSCAN1
            if senderName == 'VCAN1' and receiverName == 'ADSCAN1':
                
                input("Press enter to inject ")
            
                # Sender is standard CAN
                sender = vector.VectorBus(serial=535823, channel=0, bitrate=500000)
                
                # Receiver is CAN-FD, dual bitrate
                receiver = vector.VectorBus(serial=535823, channel=1, bitrate=500000, 
                                          data_bitrate=2000000, fd=True)
                
                try:
                    sender.send(msg)
                    print(f"Standard CAN message sent from {senderName}...")
                    
                    receivedMessage = receiver.recv(0.5) # Wait up to 0.5 seconds for a message to be received(was 0.25 seconds before)
                    if receivedMessage:
                        print("PASS! Receiver saw:")
                        print(receivedMessage)
                    else:
                        print(f"FAIL1: Specified gateway {senderName} to {receiverName} with arbitrationID_raw {hex(int(arbitrationID_raw))} failed.")
                
                finally:
                    sender.shutdown()
                    receiver.shutdown()

if __name__ == "__main__":
    run__injection_gateway_test()