import sys, re

# retired in favor of directly specifying file path in command line argument
def loadFilePath(fileToLoad:str):
    """Loads the file path specified in `filepath.txt`

    Args:
        fileToLoad (str): Args are either `primaryDBC`, `secondaryDBC`, or `cfg`

    Returns:
        str|None: Returns the filepath based on the spec. If none of the three specific args are entered, returns None
    """
    try:
        dbcFile = open("filepath.txt", 'r')
        dbcFile.readable()
        # If we could not open the file
    except OSError:
        print("Error: could not open/read file:", "filepath.txt\nDoes ""filepath.txt"" exist?")
        sys.exit()
        
    with dbcFile:
        dbcFile.readline()
        primaryDBC = dbcFile.readline().strip().strip("\"")
        dbcFile.readline()
        secondaryDBC = dbcFile.readline().strip().strip("\"")
        dbcFile.readline()
        cfg = dbcFile.readline().strip().strip("\"")
        
        if fileToLoad == "primaryDBC": return primaryDBC
        if fileToLoad == "secondaryDBC": return secondaryDBC
        if fileToLoad == "config": return cfg
        
        return None

def format_arbitrationID(arbitrationID: str, outputType: str):
    """Converts a string arbitration ID into a bit-masked integer or byte array.

    Args:
        arbitrationID (str): arbitration ID directly from the unedited .dbc file
        outputType (str): Specifying whether the output should be `int` or `byte`

    Returns:
        int | bytes: arbitration ID in requested form.
    """
    # Convert the raw string directly into an integer
    raw_id = int(arbitrationID)
    
    # Apply Bitwise Masks
    # - 0x0FFFFFFF uses AND to zero out the top 28-31 bits while preserving the lower 28 bits.
    # - 0x10000000 uses OR to forcefully set Bit 28 to 1.
    masked_id = (raw_id & 0x0FFFFFFF) | 0x10000000
    
    # Format Output
    if outputType == "byte":
        # to_bytes() directly converts the int to a 4-byte array 
        # 'big' endian is standard for CAN network transmission
        return masked_id.to_bytes(4, byteorder='big')
    elif outputType == "int":
        return masked_id
        
    return None

def scrape_dbc_for_gateways(filePath:str):
    """This function will scrape a provided `.dbc` file for all gateways, and put them in a new `.dbc` file named `scrapedGateways.dbc`.
    If the `scrapedGateways.dbc` already exists, user will be prompted before running the program to avoid overwriting existing content.
    
    Note that arbitration IDs will be displayed as integers, but hex numbers are ultimately int types under the hood in Python.

    Args:
        filePath (str): The filepath (absolute or local) of the `.dbc` file to be scraped
        
    Returns:
        scrapedName (str): The filepath of the results of the scraped `.dbc`
    """    
    try:
        dbcFile = open(filePath, 'r')
    except OSError:
        print("Error: could not open/read file ", filePath)
        sys.exit()
    
    with dbcFile:
        # Map 1: ID -> List of Routes
        gateway_dict: dict[str, list[str]] = {}
        # Map 2: ID -> Human Readable Message Name
        message_name_dict: dict[str, str] = {}
        
        curLineUnparsed = dbcFile.readline()
        while curLineUnparsed: 
            # 1. Look for Message Names (BO_ lines)
            if curLineUnparsed.startswith("BO_ "):
                parts = curLineUnparsed.split()
                # Ensure it has enough parts (BO_ <ID> <Name>: <DLC> <Sender>)
                if len(parts) >= 3:
                    msg_id = parts[1].strip()
                    # Strip the trailing colon from the name (e.g., "AC_ADS1_9E:" -> "AC_ADS1_9E")
                    msg_name = parts[2].strip().rstrip(':') 
                    message_name_dict[msg_id] = msg_name

            # 2. Look for Gateway Routes (BA_ "Network" lines)
            curLineParsed = curLineUnparsed.split('"')
            if len(curLineParsed) > 2 and curLineParsed[0].strip() == "BA_" and curLineParsed[1].strip() == "Network":
                if re.match(r".+:", curLineParsed[3]):
                    arbitrationID = re.search(r"\d+", curLineParsed[2])
                    if arbitrationID: 
                        arbitrationID = arbitrationID.string.split(" ")[2].strip()
                    
                    allGateways = curLineParsed[3].split(",")
                    allGateways = [g.strip() for g in allGateways]
                    
                    gateway_dict[arbitrationID] = allGateways
                
            curLineUnparsed = dbcFile.readline()
    
    # Return both dictionaries!
    return gateway_dict, message_name_dict

def generate_j1939_22_envelope(int_arbitrationID:int, dummy_data:list):
    """Dynamically packs an 8-byte J1939 payload into a 12-byte J1939-22 CAN-FD envelope (PGN 9472 / 0x25000).
    Uses bitwise operations for high-performance execution.

    Args:
        int_arbitrationID (int): The original Standard CAN arbitration ID
        dummy_data (list): The 8-byte payload data array

    Returns:
        tuple: (envelope_id as int, envelope_payload as list)
    """
    pdu_format = (int_arbitrationID >> 16) & 0xFF
    pdu_specific = (int_arbitrationID >> 8) & 0xFF

    if pdu_format < 240:
        byte_2 = 0x00
        container_ps = pdu_specific
    else:
        byte_2 = pdu_specific
        container_ps = 0xFF
    
    header = [0x40, pdu_format, byte_2, 0x08]
    priority_edp_dp_sa = int_arbitrationID & 0x1F0000FF
    
    envelope_id = priority_edp_dp_sa | (0x25 << 16) | (container_ps << 8)
    envelope_payload = header + dummy_data
    
    return envelope_id, envelope_payload


if __name__ == "__main__":
    if len(sys.argv) > 1:
        if (sys.argv[1] == "gateway.dbc"):
            scrape_dbc_for_gateways(sys.argv[2])
        elif (sys.argv[1] == "hex"):
           format_arbitrationID(sys.argv[2], sys.argv[3])
        elif (sys.argv[1] == "loadFilePath"):
            print(loadFilePath(sys.argv[2]))
    else:
        print("Utils: Pass an argument bro")