from py_canoe import CANoe
import utils, sys, can

def cantest1():    
    canoe = CANoe()
    
    # SEAN FILE PATH
    cfg_path = r"C:\Users\seanb\Capstone\J1939_CAN_FD_2ch\J1939_CAN_FD_2ch.cfg"
    canoe.open(cfg_path)
    
    canoe.start_measurement()

    # canoe.set_system_variable_value("PACCAR_HASI::CAN_ID_TX", arbitrationID)  
    canoe.set_system_variable_value("PACCAR_HASI::CAN_ID_TX", 0x18F00527)
    canoe.set_system_variable_value("PACCAR_HASI::Trigger", 1)

    #CAN ID 2
    canoe.set_system_variable_value("PACCAR_HASI::CAN_ID_TX", 0x18DAF903)
    canoe.set_system_variable_value("PACCAR_HASI::Trigger", 1)
        
    canoe.stop_measurement()

if __name__ == "__main__":
    cantest1()