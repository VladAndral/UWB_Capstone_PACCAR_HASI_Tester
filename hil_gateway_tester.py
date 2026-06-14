"""
Standalone PACCAR Hardware-in-the-Loop (HIL) Gateway Tester.
Provides manual execution and 2-channel override capabilities for CAN/CAN-FD routing.
"""

import os
import random
import time
import traceback
import argparse

import can
from can.interfaces import vector
from can.interfaces.vector import exceptions as vector_exceptions

import dbc_parser

# ==============================================================================
# ENVIRONMENT & HARDWARE CONFIGURATION
# ==============================================================================

# Set to True if All 8 CAN Ports are Connected to a Vector Hardware Device
# Set to False if Using VN1610 + CANcable 2Y Setup
PACCAR_HIL_ENVIRONMENT = False

# Channels for VN1610A + CANcable 2Y Setup
SENDER_CHANNEL = 1
RECEIVER_CHANNEL = 0

CAN_CLASSIC = ["VCAN1", "VCAN10", "PCAN1", "PCAN2", "VCAN2", "VCAN20"]
CAN_FD = ["ADSCAN1", "ADSCAN2"]

# Shared J1939 CAN-FD timing profile
j1939_fd_timing = can.BitTimingFd.from_bitrate_and_segments(
    f_clock=80_000_000,
    nom_bitrate=500_000,
    data_bitrate=2_000_000,
    nom_tseg1=63,
    nom_tseg2=16,
    nom_sjw=4,
    data_tseg1=15,
    data_tseg2=4,
    data_sjw=1,
)

VECTOR_APPLICATION_NAME = "CANoe"

STD_PROFILE = {
    "fd": False,
    "bitrate": 500000,
    "app_name": VECTOR_APPLICATION_NAME,
    "serial": 535823,
}
FD_PROFILE = {
    "fd": True,
    "timing": j1939_fd_timing,
    "app_name": VECTOR_APPLICATION_NAME,
    "serial": 535823,
}

# The Master Channel Dictionary
NETWORK_CONFIGS = {
    "VCAN1": {"channel": 0, **STD_PROFILE},
    "VCAN10": {"channel": 1, **STD_PROFILE},
    "PCAN1": {"channel": 2, **STD_PROFILE},
    "PCAN2": {"channel": 3, **STD_PROFILE},
    "VCAN2": {"channel": 4, **STD_PROFILE},
    "VCAN20": {"channel": 5, **STD_PROFILE},
    "ADSCAN1": {"channel": 6, **FD_PROFILE},
    "ADSCAN2": {"channel": 7, **FD_PROFILE},
}

# Array to hold active physical connections
ACTIVE_BUSES = {}

# ==============================================================================
# PACCAR GATEWAY TEST SCRIPT
# ==============================================================================


def run_paccar_hil_test(primary_dbc_filepath):
    """
    Main execution loop for manual HIL gateway validation.
    """
    
    if not os.path.exists(primary_dbc_filepath):
        raise FileNotFoundError(
            f"\n[FATAL CONFIG ERROR] Could not find DBC file at: '{primary_dbc_filepath}'\n"
            "Please check your DBC_PATH terminal argument or ensure the default file exists."
        )
    # Unpack dictionary from the scraper
    gateway_spec_dict, _ = dbc_parser.scrape_dbc_for_gateways(
        primary_dbc_filepath
    )

    try:
        # --- MASTER DATA GROUPING LOGIC ---
        route_groups = {}
        for arbitration_id_raw, channel_list in gateway_spec_dict.items():
            for gateway_channel_pair in channel_list:

                # Group all arbitration IDs that share the same gateway route
                sender, receiver = gateway_channel_pair.split(":")
                route_pair = (sender, receiver)

                if route_pair not in route_groups:
                    route_groups[route_pair] = []
                route_groups[route_pair].append(arbitration_id_raw)

        # --- GATEWAY ROUTE SANITY CHECK ---
        print("\n" + "=" * 70)
        print("PARSED GATEWAY ROUTES FROM DBC FILE")
        print("=" * 70)
        for route_pair, id_list in route_groups.items():
            print(f" - Mapped Route: {route_pair[0]:<8} -> {route_pair[1]:<8} | {len(id_list)} IDs")
        print("-" * 70)
        print(f" Total Unique Routing Paths: {len(route_groups)}")

        # --- INITIALIZE ALL 8 CHANNELS (IF APPLICABLE) ---
        if PACCAR_HIL_ENVIRONMENT:
            print("\n" + "=" * 70)
            print("INITIALIZING ALL 8 VECTOR CHANNELS...")
            print("=" * 70)
            for bus_name, bus_params in NETWORK_CONFIGS.items():
                try:
                    ACTIVE_BUSES[bus_name] = vector.VectorBus(**bus_params)
                    print(f" - Successfully opened {bus_name}")
                except (
                    can.CanInitializationError,
                    vector_exceptions.VectorInitializationError,
                ) as init_error:
                    raise RuntimeError(
                        f"\n\n{'!' * 70}\n"
                        f"[FATAL HARDWARE ERROR] Failed to connect to Vector channel: {bus_name}\n"
                        f"{'!' * 70}\n\n"
                        "Please check the following:\n"
                        "Is the Vector VN1640A physically plugged into the USB port?\n"
                        f"\nOriginal Vector Error: {init_error}\n"
                    ) from None

        # --- THE TOPOLOGY EXECUTION LOOP ---
        for route_pair, id_list in route_groups.items():
            sender_name = route_pair[0]
            receiver_name = route_pair[1]

            is_sender_fd = sender_name in CAN_FD
            is_receiver_fd = receiver_name in CAN_FD

            # --- DYNAMIC HARDWARE INITIALIZATION ---
            if PACCAR_HIL_ENVIRONMENT:
                sender = ACTIVE_BUSES[sender_name]
                receiver = ACTIVE_BUSES[receiver_name]

                print("\n" + "-" * 70)
                print(f" TESTING Gateway: {sender_name} to {receiver_name} ({len(id_list)} IDs)")
                print("-" * 70)
            else:
                # [2-CHANNEL MANUAL OVERRIDE SETUP]
                for bus in list(ACTIVE_BUSES.values()):
                    if bus is not None:
                        bus.shutdown()
                ACTIVE_BUSES.clear()

                time.sleep(0.5)

                print("\n" + "=" * 70)
                print(" [MANUAL OVERRIDE] 2-Channel Test Bench Detected")
                print(" Please manually reconfigure the physical layer:")
                print(f" -> Plug SENDER (CH {SENDER_CHANNEL}) into {sender_name}")
                print(f" -> Plug RECEIVER (CH {RECEIVER_CHANNEL}) into {receiver_name}")
                print("=" * 70)
                input("Press Enter when physical connections are secure to begin... ")

                tx_params = NETWORK_CONFIGS[sender_name].copy()
                rx_params = NETWORK_CONFIGS[receiver_name].copy()

                tx_params["channel"] = SENDER_CHANNEL
                rx_params["channel"] = RECEIVER_CHANNEL

                try:
                    sender = vector.VectorBus(**tx_params)
                    receiver = vector.VectorBus(**rx_params)
                    ACTIVE_BUSES[sender_name] = sender
                    ACTIVE_BUSES[receiver_name] = receiver
                except (
                    can.CanInitializationError,
                    vector_exceptions.VectorInitializationError,
                ) as init_error:
                    raise RuntimeError(
                        f"Failed to re-establish hardware abstraction layer: {init_error}"
                    ) from None

            # CAN Signal Injection Logic
            for arbitration_id_raw in id_list:
                int_arbitration_id = int(
                    dbc_parser.format_arbitration_id(arbitration_id_raw, "int")
                )

                msg = None
                dummy_data = [random.randint(0, 255) for _ in range(8)]

                # FORMAT SENDER
                if is_sender_fd:
                    send_id, send_payload = dbc_parser.generate_j1939_22_envelope(
                        int_arbitration_id, dummy_data
                    )
                    msg = can.Message(
                        is_rx=False,
                        is_extended_id=True,
                        is_fd=True,
                        bitrate_switch=True,
                        dlc=9,
                        arbitration_id=send_id,
                        data=send_payload,
                    )
                else:
                    msg = can.Message(
                        is_rx=False,
                        is_extended_id=True,
                        arbitration_id=int_arbitration_id,
                        data=dummy_data,
                    )

                if msg is None:
                    raise RuntimeError(
                        f"FATAL SCRIPT LOGIC: Formatting bypassed for ID {arbitration_id_raw}."
                    )

                # FORMAT RECEIVER
                if is_receiver_fd:
                    expected_id, expected_data = dbc_parser.generate_j1939_22_envelope(
                        int_arbitration_id, dummy_data
                    )
                    expected_is_fd = True
                else:
                    expected_id = int_arbitration_id
                    expected_data = dummy_data
                    expected_is_fd = False

                # --- EXECUTION & RETRY LOGIC ---
                max_retries = 1
                test_passed = False

                for attempt in range(max_retries):
                    formatted_send_payload = " ".join(f"{x:02x}" for x in msg.data)
                    print(
                        f" -> Sending to {sender_name}  : 0x{msg.arbitration_id:08X} | "
                        f"{formatted_send_payload} (Attempt {attempt + 1})"
                    )

                    while receiver.recv(0.0) is not None:
                        pass

                    start_time = time.time()
                    sender.send(msg)
                    timeout_end = start_time + 1.0

                    found_routed_frame = False
                    elapsed_ms = 0.0

                    while time.time() < timeout_end:
                        received_message = receiver.recv(0.1)

                        if received_message:
                            if list(received_message.data) == expected_data:
                                elapsed_ms = (time.time() - start_time) * 1000
                                found_routed_frame = True
                                break

                    # --- EVALUATION ---
                    if found_routed_frame:
                        formatted_recv_payload = " ".join(
                            f"{x:02x}" for x in received_message.data
                        )
                        print(
                            f" <- Received on {receiver_name}: "
                            f"0x{received_message.arbitration_id:08X} | {formatted_recv_payload}"
                        )

                        if (
                            received_message.arbitration_id == expected_id
                            and received_message.is_fd == expected_is_fd
                        ):
                            if is_sender_fd and not is_receiver_fd:
                                print(
                                    f"    [PASS] Routing Successful (FD Envelope Unpacked)! "
                                    f"({elapsed_ms:.1f} ms) | Target: 0x{expected_id:08X} == "
                                    f"Received: 0x{received_message.arbitration_id:08X}\n"
                                )
                            elif not is_sender_fd and is_receiver_fd:
                                print(
                                    f"    [PASS] Routing Successful (FD Envelope Packed)! "
                                    f"({elapsed_ms:.1f} ms) | Expected: 0x{expected_id:08X} == "
                                    f"Received: 0x{received_message.arbitration_id:08X}\n"
                                )
                            else:
                                print(
                                    f"    [PASS] Routing Successful (Logical ID Verified)! "
                                    f"({elapsed_ms:.1f} ms) | Expected: 0x{expected_id:08X} == "
                                    f"Received: 0x{received_message.arbitration_id:08X}\n"
                                )
                            test_passed = True
                            break
                        else:
                            print(
                                f"    [FAIL / MUTATED] Frame routed, but gateway dangerously "
                                f"translated the ID/Protocol ({elapsed_ms:.1f} ms)"
                            )
                            print(
                                f"           Expected   : 0x{expected_id:08X} (FD: {expected_is_fd})"
                            )
                            print(
                                f"           Received   : 0x{received_message.arbitration_id:08X} "
                                f"(FD: {received_message.is_fd})\n"
                            )
                            break

                    else:
                        print("    [FAIL] Gateway dropped the frame (Timeout).\n")

                if not test_passed:
                    print(
                        f"--> FINAL RESULT: Gateway {sender_name} to {receiver_name} "
                        f"FAILED ID {arbitration_id_raw}."
                    )

    except Exception as general_error:  # pylint: disable=broad-exception-caught
        print(f"\n[Script Error] The script crashed due to: {general_error}")
        traceback.print_exc()

    finally:
        print("\n[Hardware Release] Closing all active channels and shutting down...")
        for bus_name, bus in list(ACTIVE_BUSES.items()):
            if bus is not None:
                try:
                    bus.shutdown()
                    print(f" - Closed {bus_name}")
                except can.CanError:
                    # Only catch CAN-related teardown errors
                    pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Standalone PACCAR HIL Gateway Tester"
    )
    
    parser.add_argument(
        "--dbcPath",
        type=str,
        default="HASI_Primary_ALL_CAN.dbc",
        help="Path to the PACCAR .dbc database file"
    )
    
    args = parser.parse_args()
    
    run_paccar_hil_test(args.dbcPath)