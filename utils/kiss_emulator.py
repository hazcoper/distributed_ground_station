import socket
from deconding_info import structure_dict, possible_fields, subsystem_dict, obc_dict, ttc_dict, eps_dict, com_dict, pl_dict, variable_types
from deconding_info import format_seconds, variable_parsing_functions
import binascii
import argparse

def print_byte_array(byte_array):
    hex_data = binascii.hexlify(byte_array).decode()  # Convert to hex string
    # Add \x prefix to each byte
    formatted_hex_data = ''.join(f'0x{hex_data[i:i+2]} ' for i in range(0, len(hex_data), 2))
    # print(formatted_hex_data)
    return formatted_hex_data

def count_different_bits(byte_array1, byte_array2):
    # Ensure both arrays are of the same length
    if len(byte_array1) != len(byte_array2):
        raise ValueError("Byte arrays must have the same length.")

    # XOR each pair of bytes and count the different bits
    diff_bits = 0
    for b1, b2 in zip(byte_array1, byte_array2):
        diff_bits += bin(b1 ^ b2).count('1')  # XOR and count '1's in the binary representation

    return diff_bits

# KISS special characters
KISS_FEND = 0xC0  # Frame End
KISS_FESC = 0xDB  # Frame Escape
KISS_TFEND = 0xDC # Transposed Frame End
KISS_TFESC = 0xDD # Transposed Frame Escape


def decode_kiss(data):
    """Decode KISS-encoded data."""
    decoded = bytearray()
    i = 0
    while i < len(data):
        if data[i] == KISS_FESC:
            i += 1
            if i < len(data):
                if data[i] == KISS_TFEND:
                    decoded.append(KISS_FEND)
                elif data[i] == KISS_TFESC:
                    decoded.append(KISS_FESC)
                else:
                    decoded.append(data[i])
        else:
            decoded.append(data[i])
        i += 1
    return decoded


def separate_data(byte_data):
    """
    This will receive the bytes of the messages and create the Dictionary with each of the fields
    it will not separate the variable fields yet

    it will separate the message to the inital fields
    try and determine the message type
        will be determine by the size of the message, report num and ss
    seperate the rest of the message into the variable fields
    """
    
    # seperate the message into the initial fields
    
    
    decoded_dict = {}
    for field, field_info in structure_dict.items():
        decoded_dict[field] = byte_data[field_info['start']:field_info['end']]
        # print(f"{field}: {print_byte_array(byte_data[field_info['start']:field_info['end']])}")
    
    # try and determine the message type
    closest_ss = None
    min_diff_ss = None
    closest_report_num = None
    min_diff_report = None
    
    for ss in possible_fields["ss"]:
        different_bits = count_different_bits(decoded_dict["ss"], ss)
        if min_diff_ss is None or different_bits < min_diff_ss:
            min_diff_ss = different_bits
            closest_ss = ss
            
    for report_num in possible_fields["report_num"]:
        different_bits = count_different_bits(decoded_dict["report_num"], report_num)
        if min_diff_report is None or different_bits < min_diff_report:
            min_diff_report = different_bits
            closest_report_num = report_num

    # convert the ss to subsystem
    ss_index = possible_fields["ss"].index(closest_ss)
    report_num_index = possible_fields["report_num"].index(closest_report_num)

    
    if report_num_index != ss_index:
        print("Error in the message: The report number and the subsystem do not match")
        print("  Unable to fully classify message")
        return decoded_dict
    
    # get the correct dict with the variables for the subsystem
    variable_dict = None
    if ss_index == 0:
        variable_dict = obc_dict
    elif ss_index == 1:
        variable_dict = ttc_dict
    elif ss_index == 2:
        variable_dict = com_dict
    elif ss_index == 3:
        variable_dict = eps_dict
    elif ss_index == 4:
        variable_dict = pl_dict
    
    
    for field, field_info in variable_dict.items():
        decoded_dict[field] = byte_data[field_info['start']:field_info['end']]
        # print(f"{field}: {print_byte_array(byte_data[field_info['start']:field_info['end']])}")
        
        
    return decoded_dict

def convert_human_readable(separated_data):
    """
    Given a data that is already separated into the different fields
    it will convert the data from bytes to human readable data
    """
    
    # deal with the wanted text data (source and destination)
    text_data = ["ax25_dest", "ax25_src"]
    for field in text_data:
        temp_string = ""
        for letter in separated_data[field]:
            temp_string += chr(int(letter/2))
        separated_data[field] = temp_string
        
    # deal with the ss name
    separated_data["ss"] = subsystem_dict.get(int(separated_data["ss"][0]), "Unknown")
    
    # deal with the variables
    for field, field_info in separated_data.items():
        if field not in variable_types:
            continue
        separated_data[field] = int.from_bytes(field_info, byteorder='little', signed=variable_types[field])
        
    # deal with the sat timestamp of the message
    separated_data["ts"] = int.from_bytes(separated_data["ts"], byteorder='little', signed=False)
    
    return separated_data
        
def print_data(human_readable):
    """
    Given the separated data in human readable format. it will print the data to the terminal
    """
    
    # print the header
    print("MESSAGE: ")
    print(f"  Destination: {repr(human_readable['ax25_dest'])}")
    print(f"  Source: {repr(human_readable['ax25_src'])}")
    print(f"  SS: {human_readable['ss']}")
    print(f"  MSG sat timestamp: {format_seconds(human_readable['ts'])}")
    
    # print the variables
    print("  Variables: ")
    
    for field, field_info in human_readable.items():
        if field not in variable_parsing_functions:
            continue
        # print(f"    {field}: {variable_parsing_functions[field](field_info)}")
        print(f"    {field}: ",end="")
        print(variable_parsing_functions[field](field_info))
    print()
    
def start_tnc_client(host, port):
    """Start a simple TNC client that receives and prints KISS data as bytes."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
        client.connect((host, port))
        print(f"Connected to server at {host}:{port}")

        buffer = bytearray()
        while True:
            data = client.recv(1024)
            if not data:
                print("Disconnected from server.")
                break
            print("Received raw data:", data)

            for byte in data:
                if byte == KISS_FEND:
                    if buffer:
                        decoded_kiss = decode_kiss(buffer[1:])
                        print("Decoded Data:", ' '.join(f"0x{b:02X}" for b in decoded_kiss))
                        print("\n")
                        separated_data = separate_data(decoded_kiss)
                        human_readable = convert_human_readable(separated_data)
                        print_data(human_readable)
                        buffer.clear()
                else:
                    buffer.append(byte)
            
            

def hand_decode():
    """
    This will allow to test hex arrays to see what the output would be
    this would before the kiss decoding
    """            
    
    hex_string = "0x86 0xA6 0x6A 0x86 0x8A 0xA0 0x62 0x86 0xA8 0x6C 0x92 0xA6 0xA8 0x63 0x03 0x01 0x00 0x00 0x03 0x87 0x00 0x04 0x32 0x23 0x28 0x76 0x00 0x27 0xE2 0x8D 0x03 0x00 0x04 0x4E 0x0D 0x72 0x0D 0x68 0x0D 0x6D 0x0D 0xA7 0x1F 0x4E 0x0D 0xFC 0x1F 0x4A 0x00 0x31 0x00 0x0F 0x03 0x36 0x00 0x5A 0x00 0x09 0xC0 0x1D 0x00 0x00 0x00 0x64 0x86 0x65 0x00"
    
    
    # convert hex string to byte array
    byte_array = bytearray(int(byte, 16) for byte in hex_string.split())

    print("Received raw data:", byte_array)

    # separate the data
    decoded_kiss = decode_kiss(byte_array)
    print("Decoded Data:", ' '.join(f"0x{b:02X}" for b in decoded_kiss))
    print("\n")
    separated_data = separate_data(decoded_kiss)
    
    human_readable = convert_human_readable(separated_data)
    print_data(human_readable)
    exit(0)

if __name__ == "__main__":
    
    parser = argparse.ArgumentParser(
        description="TNC Client to receive and decode KISS frames over TCP from ISTSAT-1."
    )
    parser.add_argument(
        "--host",
        type=str,
        required=True,
        help="The IP address or hostname of the server.",
    )
    parser.add_argument(
        "--port",
        type=int,
        required=True,
        help="The port number to connect to on the server.",
    )

    args = parser.parse_args()
    start_tnc_client(args.host, args.port)
    