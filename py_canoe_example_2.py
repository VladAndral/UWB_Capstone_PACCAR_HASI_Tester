# from py_canoe import CANoe
import utils, sys, can
from can.interfaces import vector

# configs = can.detect_available_configs(interfaces=['vector'])
# cfg = configs[0]
# # print(cfg)
# VectorBus.set_application_config(app_name="Python", app_channel=0, **cfg)



def run__injection_gateway_test(isVirtualInterface:bool):
    """Test script that loops through all gateway networks, injecting CAN messages
        into each bus, and listening on one bus to see if the message was sent

    Args:
        isVirtualInterface (bool): Option to force a virtual interface,
        even if hardware like Vector or Kvaser are connected
    """    
    
    # can.util.load_config(r"C:\Users\seanb\Capstone\J1939_CAN_FD_2ch\J1939_CAN_FD_2ch.cfg")
    
    # Typesetting the variable given the user's choice
        # Interface is set to none to let the system autodetect, making code hardware agnostic
    # interfaceChoice:str|None = "virtual" if isVirtualInterface else "vector"

    # for config in vector.get_channel_configs(): print(config)
    # return

    # cfg_path = r"C:\Users\seanb\Capstone\J1939_CAN_FD_2ch\J1939_CAN_FD_2ch.cfg"
    # can.util.load_file_config(cfg_path)
    
    HASI_bus_list = ["VCAN1",
                    "VCAN10",
                    "PCAN1",
                    "PCAN2",
                    "VCAN2",
                    "VCAN20",
                    "ADSCAN1",
                    "ADSCAN2"
                    ]

    # Dictionary of all gateways. Key=arbitrationID, value=list of channels gatewayed
    # gatewaySpecDict = utils.scrape_dbc_for_gateways("NOPUSH_DBC_Files/HASI_Primary_ALL_CAN.dbc")
    gatewaySpecDict = utils.scrape_dbc_for_gateways(utils.loadFilePath("primaryDBC"))

    # configs = can.detect_available_configs(interfaces=['vector'])
    # cfg = configs[0]
    # can.interfaces.vector.VectorBus.set_application_config(app_name="Python", app_channel=0, **cfg)
    
    for arbitrationID, channelList in gatewaySpecDict.items():
        # Formatting arbitrationID and converting to int format for python-can to use
        int_arbitrationID = int(utils.format_arbitrationID(arbitrationID, "int"))
        # Message is just arbitrationID
        msg = can.Message(is_extended_id=True, arbitration_id=int_arbitrationID)
        # There may be multiple gateways for one arbitrationID
        for gatewayChannelPair in channelList:
            # Splitting this current channel, e.g. "CAN1:CAN2" --> ["CAN1", "CAN2"]
            eachChannel = gatewayChannelPair.split(":")
            print("\nThis gateway pair: {} to {}".format(eachChannel[0], eachChannel[1]))
            input("Press enter when switched. Test outputs will be affected if the switch is not made.")
            
            # For each bus
            for busName in HASI_bus_list:
                # Do not send from the bus that is specified as receiver
                if busName == eachChannel[1]: continue
                
                # Send message. Might have to change when this happens relative to bus.recv()
                # busObject.send(msg)
                
                # If the bus that sent is the specified sender
                if busName == eachChannel[0]:
                    print("Sender inside if: {}".format(busName))
                    sender = vector.VectorBus(serial=535823, channel=0)
                    receiver = vector.VectorBus(serial=535823, channel=1)
                    # If the receiver did not receive or do anything
                    sender.send(msg)
                    print(msg)
                    if receiver.recv(1) is None:
                        print("FAIL1: Specified gateway {} to {} with arbitrationID {} failed.".format(eachChannel[0], eachChannel[1], arbitrationID))
                    else: print("pass")
                    sender.shutdown()
                    receiver.shutdown()
                    break
                # # If the bus that sent is not the specified sender
                # elif busName != eachChannel[0]:
                #     # If the receiver did anything (it's not supposed to)
                #     if HASI_bus_list[eachChannel[1]].recv(0.5) is not None and not busObject.send(msg):
                #         print("FAIL2: For gateway {0} to {1} with arbitrationID {2}, receiving channel {1} woke when {3} sent the signal.".format(eachChannel[0], eachChannel[1], arbitrationID, busName))

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "-v":
        run__injection_gateway_test(True)
    else:
        run__injection_gateway_test(False)