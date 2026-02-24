from py_canoe import CANoe

def run_gateway_injection_test():
    
    canoe = CANoe()
    
    cfg_path = r"C:\Users\Public\Documents\Vector\CANoe\Projects\J1939_CAN_FD_2ch\J1939_CAN_FD_2ch.cfg"
    canoe.open(cfg_path)
    
    canoe.start_measurement()
    
    canoe.set_system_variable_value("PACCAR_HASI::Trigger_18F00527", 1)
    
    canoe.stop_measurement() 
    

if __name__ == "__main__":
    run_gateway_injection_test()