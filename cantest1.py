from py_canoe import CANoe
import utils, sys, can

def cantest1():    
    canoe = CANoe()
    
    ## MUST EDIT FILEPATH.TXT FOR THIS TO WORK
    cfg_path = utils.loadFilePath("cfg")
    canoe.open(cfg_path)
    
    canoe.start_measurement()

    # canoe.set_system_variable_value("PACCAR_HASI::CAN_ID_TX", arbitrationID)
    # Arb ID: 2565866791 "VCAN2:VCAN20"  
    canoe.set_system_variable_value("PACCAR_HASI::CAN_ID_TX", 0x18F00527)
    canoe.set_system_variable_value("PACCAR_HASI::Trigger", 1)

    # CAN ID 2
    # Arb ID: 2564487427 "VCAN20:VCAN2"
    canoe.set_system_variable_value("PACCAR_HASI::CAN_ID_TX", 0x18DAF903)
    canoe.set_system_variable_value("PACCAR_HASI::Trigger", 1)

    # CAN ID 3
    # Arb ID: 2566541214 "ADSCAN1:VCAN2, ADSCAN1:VCAN20"
    canoe.set_system_variable_value("PACCAR_HASI::CAN_ID_TX", 0x18FA4F9E)
    canoe.set_system_variable_value("PACCAR_HASI::Trigger", 1)
        
    canoe.stop_measurement()

if __name__ == "__main__":
    cantest1()