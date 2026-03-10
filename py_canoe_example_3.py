import utils, sys, can, time
from can.interfaces import vector

def run__injection_gateway_test():
    """Test script that loops through all gateway networks, injecting CAN messages
        into each bus, and listening on one bus to see if the message was sent

    Args:
        isVirtualInterface (bool): Option to force a virtual interface,
        even if hardware like Vector or Kvaser are connected
    """    
    HASI_bus_list = ["VCAN1",
                    "VCAN10",
                    "PCAN1",
                    "PCAN2",
                    "VCAN2",
                    "VCAN20",
                    "ADSCAN1",
                    "ADSCAN2"
                    ]
    
    configs = can.detect_available_configs(interfaces=['vector'])
    cfg = configs[0]
    print(cfg)
    vector.VectorBus.set_application_config(app_name="CANoe", app_channel=0, **cfg)
    
    
    #vector.VectorBus.popup_vector_hw_configuration(wait_for_finish=0)
    gatewaySpecDict = utils.scrape_dbc_for_gateways(r"C:\Users\garci\Downloads\HASI_Primary_ALL_CAN (2).dbc")

    for arbitrationID, channelList in gatewaySpecDict.items():
       
        int_arbitrationID = int(utils.format_arbitrationID(arbitrationID, "int"))
        
        
        msg = can.Message(is_rx = False, is_extended_id=True, arbitration_id=int_arbitrationID)
        # msg = can.Message(is_rx = False, is_extended_id=True, arbitration_id=int_arbitrationID, data=[0x00]*8)
        
        # There may be multiple gateways for one arbitrationID
        for gatewayChannelPair in channelList:
            # Splitting this current channel, e.g. "CAN1:CAN2" --> ["CAN1", "CAN2"]
            eachChannel = gatewayChannelPair.split(":")
            if eachChannel[0][0] == ('V' or 'P') and eachChannel[1][0] == ('V' or 'P'):
                
                print("\nThis gateway pair: {} to {}".format(eachChannel[0], eachChannel[1]))
                input("Press enter when switched. Test outputs will be affected if the switch is not made.")
            
                # Worked only when bitrate == 500kHz
                sender = vector.VectorBus(serial=535823, channel=0, bitrate=500000)
                receiver = vector.VectorBus(serial=535823, channel=1, bitrate=500000)
                
                time.sleep(0.1)
                try:
                    
                    sender.send(msg)
                    print(msg)
                    
                    msg_rx = receiver.recv(0.25)
                    if msg_rx is None:
                        print(f"FAIL1: Specified gateway {eachChannel[0]} to {eachChannel[1]} with arbitrationID {hex(int(arbitrationID))} failed.")
                    else: 
                        print(msg_rx)
                        
                finally:
                    sender.shutdown()
                    receiver.shutdown()

if __name__ == "__main__":
    run__injection_gateway_test()