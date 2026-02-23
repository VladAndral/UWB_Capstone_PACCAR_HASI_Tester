#!/usr/bin/env python

"""
This example shows how sending a single message works.
"""

import can


def send_one(): 
    """Sends a single message."""

    # this uses the default configuration (for example from the config file)
    # see https://python-can.readthedocs.io/en/stable/configuration.html
    # BA_ "Network" BO_ 2566540803 "VCAN20:ADSCAN1";
    with can.Bus() as bus:
        # Using specific buses works similar:
        bus = can.Bus(interface='socketcan', channel='vcan20', bitrate=250000)
      
     

        msg = can.Message(
            arbitration_id=0xC0FFEE, 
            data=[0, 25, 0, 1, 3, 1, 4, 1], 
            is_extended_id=True
        )

        try:
            bus.send(msg)
            print(f"Message sent on {bus.channel_info}")
        except can.CanError:
            print("Message NOT sent")

    with can.Bus() as bus:
        
        bus = can.Bus(interface='socketcan', channel='ADSCAN1', bitrate=250000)


if __name__ == "__main__":
    send_one()