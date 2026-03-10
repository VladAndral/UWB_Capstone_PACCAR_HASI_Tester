import utils, sys, can
from can.interfaces import vector

BITRATE_CONST = 500000

def run__injection_gateway_test():
    """Test script that loops through all gateway networks, injecting CAN messages
        into each bus, and listening on one bus to see if the message was sent

    Args:
        isVirtualInterface (bool): Option to force a virtual interface,
        even if hardware like Vector or Kvaser are connected
    """
    
    ######### Will it work without this?
    # configs = can.detect_available_configs(interfaces=['vector'])
    # cfg = configs[0]
    # print(cfg)
    # vector.VectorBus.set_application_config(app_name="CANoe", app_channel=0, **cfg)
    
    
    # vector.VectorBus.popup_vector_hw_configuration(wait_for_finish=0)
    
    # load the dbc filepath entered in filepath.txt
    primaryDBC_filepath = utils.loadFilePath("primaryDBC")
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
            # This if branch is only for testing non CAN FD ports ADSCAN#, since they require special handling/formatting
            if eachChannel[0][0] == ('V' or 'P') and eachChannel[1][0] == ('V' or 'P'):
                
                print("\nThis gateway pair: {} to {}. Order matters. (arbID {})".format(eachChannel[0], eachChannel[1], arbitrationID_raw))
                input("Press enter when switched. Test outputs will be affected if the switch is not made.")
            
                # Worked only when bitrate == 500kHz (up from 250000)
                sender = vector.VectorBus(serial=535823, channel=0, bitrate=BITRATE_CONST)
                receiver = vector.VectorBus(serial=535823, channel=1, bitrate=BITRATE_CONST)
                
                try:
                    sender.send(msg)
                    print(msg)
                    
                    # If the message was received, the recv() function will return the message received
                    msg_rx = receiver.recv(0.25)
                    if msg_rx is None:
                        print(f"FAIL1: Specified gateway {eachChannel[0]} to {eachChannel[1]} with arbitrationID_raw {hex(int(arbitrationID_raw))} failed.")
                    else: 
                        print(msg_rx)
                
                # Always shutdown the VectorBus'es
                finally:
                    sender.shutdown()
                    receiver.shutdown()

if __name__ == "__main__":
    run__injection_gateway_test()