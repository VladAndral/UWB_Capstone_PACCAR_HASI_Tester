# from py_canoe import CANoe
import utils, sys, can

def run__injection_gateway_test(isVirtualInterface:bool):
    """Test script that loops through all gateway networks, injecting CAN messages
        into each bus, and listening on one bus to see if the message was sent

    Args:
        isVirtualInterface (bool): Option to force a virtual interface,
        even if hardware like Vector or Kvaser are connected
    """    
    

    
    # Typesetting the variable given the user's choice
        # Interface is set to none to let the system autodetect, making code hardware agnostic
    interfaceChoice:str|None = "virtual" if isVirtualInterface else None

    # For now at least, we have to manually make ever bus object
    VCAN1 = can.Bus(channel="CAN1", interface=interfaceChoice)
    VCAN10 = can.Bus(channel="CAN2", interface=interfaceChoice)
    PCAN1 = can.Bus(channel="CAN3", interface=interfaceChoice)
    PCAN2 = can.Bus(channel="CAN4", interface=interfaceChoice)
    VCAN2 = can.Bus(channel="CAN5", interface=interfaceChoice)
    VCAN20 = can.Bus(channel="CAN6", interface=interfaceChoice)
    ADSCAN1 = can.Bus(channel="CAN7", interface=interfaceChoice)
    ADSCAN2 = can.Bus(channel="CAN8", interface=interfaceChoice)
    
    # This 'with' statement is for handling graceful exits given any unexpected errors or interrupts thrown
    with VCAN1, VCAN10, PCAN1, PCAN2, VCAN2, VCAN20, ADSCAN1, ADSCAN2:
    
        HASI_bus_dict = {"VCAN1":VCAN1,
                        "VCAN10":VCAN10,
                        "PCAN1":PCAN1,
                        "PCAN2":PCAN2,
                        "VCAN2":VCAN2,
                        "VCAN20":VCAN20,
                        "ADSCAN1":ADSCAN1,
                        "ADSCAN2":ADSCAN2
                        }

        # Dictionary of all gateways. Key=arbitrationID, value=list of channels gatewayed
        gatewaySpecDict = utils.scrape_dbc_for_gateways("NOPUSH_DBC_Files/HASI_Primary_ALL_CAN.dbc")
        
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
                for busName, busObject in HASI_bus_dict.items():
                    # Do not send from the bus that is specified as receiver
                    if busName == eachChannel[1]: continue
                    
                    # Send message. Might have to change when this happens relative to bus.recv()
                    busObject.send(msg)
                    
                    # If the bus that sent is the specified sender
                    if busName == eachChannel[0]:
                        # If the receiver did not receive or do anything
                        if not HASI_bus_dict[eachChannel[1]].recv(0.5):
                            print("FAIL: Specified gateway {} to {} with arbitrationID {} failed.".format(eachChannel[0], eachChannel[1], arbitrationID))
                    # If the bus that sent is not the specified sender
                    elif busName != eachChannel[0]:
                        # If the receiver did anything (it's not supposed to)
                        if HASI_bus_dict[eachChannel[1]].recv(0.5):
                            print("FAIL: For gateway {0} to {1} with arbitrationID {2}, receiving channel {1} woke when {3} sent the signal.".format(eachChannel[0], eachChannel[1], arbitrationID, busName))
    
    # canoe = CANoe()
    
    # cfg_path = r"C:\Users\Public\Documents\Vector\CANoe\Projects\J1939_CAN_FD_2ch\J1939_CAN_FD_2ch.cfg"
    # canoe.open(cfg_path)
    
    # canoe.start_measurement()
    
    
    # for arbitrationID, channelList in gatewaySpecDict.items():
    #         for channel in channelList:
    #             gatewayNodes = channel.split(":")
    #             senderNode = gatewayNodes[0]
    #             canoe.set_system_variable_value("PACCAR_HASI::CAN_ID_TX", arbitrationID)  
    #             # canoe.set_system_variable_value("PACCAR_HASI::CAN_ID_TX", 0x18DAF903)
    #             # canoe.set_system_variable_value("PACCAR_HASI::Trigger", 1)
    
    #     # #CAN ID 2
    #     # canoe.set_system_variable_value("PACCAR_HASI::CAN_ID_TX", 0x18DAF903)
    #     # canoe.set_system_variable_value("PACCAR_HASI::Trigger", 1)
        
    # canoe.stop_measurement()

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "-v":
        run__injection_gateway_test(True)
    else:
        run__injection_gateway_test(False)