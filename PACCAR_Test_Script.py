import os
from py_canoe import CANoe

def test_connection():
    print("Initializing CANoe wrapper...")
    canoe = CANoe()
    
    
    cfg_path = r"C:\Users\Public\Documents\Vector\CANoe\Projects\J1939_CAN_FD_2ch\J1939_CAN_FD_2ch.cfg"
    
    print(f"Telling Windows to open/attach to: {cfg_path}")
    
    
    canoe.open(cfg_path)
    
    print("Fetching version info...")
    version_info = canoe.get_canoe_version_info()
    
    print(f"Success! Connected to CANoe version: {version_info}")

if __name__ == "__main__":
    test_connection()