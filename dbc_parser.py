"""
CAN network tools and helpers.
Provides utilities for DBC parsing, ID formatting, and J1939-22 encapsulation.
"""
import re
import sys

def format_arbitration_id(arbitration_id: str, output_type: str):
    """Converts a string arbitration ID into a bit-masked integer or byte array.

    Args:
        arbitration_id (str): arbitration ID directly from the unedited .dbc file
        output_type (str): Specifying whether the output should be `int` or `byte`

    Returns:
        int | bytes: arbitration ID in requested form.
    """
    # Convert the raw string directly into an integer
    raw_id = int(arbitration_id)

    # Apply Bitwise Masks
    # - 0x0FFFFFFF uses AND to zero out the top 28-31 bits.
    # - 0x10000000 uses OR to forcefully set Bit 28 to 1.
    masked_id = (raw_id & 0x0FFFFFFF) | 0x10000000

    # Format Output
    if output_type == "byte":
        # to_bytes() converts the int to a 4-byte array
        # 'big' endian is standard for CAN network transmission
        return masked_id.to_bytes(4, byteorder="big")
    if output_type == "int":
        return masked_id

    return None


def scrape_dbc_for_gateways(file_path: str):
    """Scrapes a provided `.dbc` file for all gateways and message names.

    Note that arbitration IDs will be displayed as integers, but hex numbers
    are ultimately int types under the hood in Python.

    Args:
        file_path (str): The filepath (absolute or local) of the `.dbc` file

    Returns:
        tuple: (gateway_dict, message_name_dict)
    """
    try:
        # Explicitly declaring encoding satisfies the linter (W1514)
        dbc_file = open(file_path, "r", encoding="utf-8")
    except OSError:
        print("Error: could not open/read file ", file_path)
        sys.exit()

    with dbc_file:
        # Map 1: ID -> List of Routes
        gateway_dict: dict[str, list[str]] = {}
        # Map 2: ID -> Message Name
        message_name_dict: dict[str, str] = {}

        cur_line_unparsed = dbc_file.readline()
        while cur_line_unparsed:
            # Look for Message Names (BO_ lines)
            if cur_line_unparsed.startswith("BO_ "):
                parts = cur_line_unparsed.split()
                # Ensure it has enough parts (BO_ <ID> <Name>: <DLC> <Sender>)
                if len(parts) >= 3:
                    msg_id = parts[1].strip()
                    # Strip trailing colon (e.g., "AC_ADS1_9E:" -> "AC_ADS1_9E")
                    msg_name = parts[2].strip().rstrip(":")
                    message_name_dict[msg_id] = msg_name

            # Look for Gateway Routes (BA_ "Network" lines)
            cur_line_parsed = cur_line_unparsed.split('"')
            # Line break applied to satisfy 88-character length limit
            if (
                len(cur_line_parsed) > 2
                and cur_line_parsed[0].strip() == "BA_"
                and cur_line_parsed[1].strip() == "Network"
            ):
                if re.match(r".+:", cur_line_parsed[3]):
                    found_id = re.search(r"\d+", cur_line_parsed[2])
                    if found_id:
                        # Extract the exact string match using .group()
                        str_id = found_id.group()

                        all_gateways = cur_line_parsed[3].split(",")
                        all_gateways = [g.strip() for g in all_gateways]

                        gateway_dict[str_id] = all_gateways

            cur_line_unparsed = dbc_file.readline()

    # Return both dictionaries
    return gateway_dict, message_name_dict

def generate_j1939_22_envelope(int_arbitration_id: int, dummy_data: list):
    """Dynamically packs an 8-byte J1939 payload into a 12-byte CAN-FD envelope.

    Uses bitwise operations for high-performance execution.

    Args:
        int_arbitration_id (int): The original Standard CAN arbitration ID
        dummy_data (list): The 8-byte payload data array

    Returns:
        tuple: (envelope_id as int, envelope_payload as list)
    """
    pdu_format = (int_arbitration_id >> 16) & 0xFF
    pdu_specific = (int_arbitration_id >> 8) & 0xFF

    if pdu_format < 240:
        byte_2 = 0x00
        container_ps = pdu_specific
    else:
        byte_2 = pdu_specific
        container_ps = 0xFF

    header = [0x40, pdu_format, byte_2, 0x08]
    priority_edp_dp_sa = int_arbitration_id & 0x1F0000FF

    envelope_id = priority_edp_dp_sa | (0x25 << 16) | (container_ps << 8)
    envelope_payload = header + dummy_data
    return envelope_id, envelope_payload
