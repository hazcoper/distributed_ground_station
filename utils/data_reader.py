import pickle
import os
import binascii


def print_byte_array(byte_array):
    hex_data = binascii.hexlify(byte_array).decode()  # Convert to hex string
    # Add \x prefix to each byte
    formatted_hex_data = ''.join(f'0x{hex_data[i:i+2]} ' for i in range(0, len(hex_data), 2))
    # print(formatted_hex_data)
    return formatted_hex_data

file_list = [x for x in os.listdir() if x.endswith(".pkl")]


test_byte_array = bytearray([0x86, 0xa2, 0x86, 0xa2, 0x86, 0xa2])


# load pickle file
for file in file_list:
    with open(file, "rb") as f:
        data = pickle.load(f)



    for entry in data:
        print(f"Data from {entry['host']}:{entry['port']} at {entry['timestamp']}")
        
        # if entry["host"] == "178.166.52.139":
        #     continue

        bt = bytearray(entry['data'])

        
        bt_string = print_byte_array(bt)
        
        if "0x86 0xa2 0x86 0xa2 0x86" not in bt_string:
            continue
        
        # print data as by array
        print(f"  time: {entry['timestamp']} host: {entry['host']} data: ", end="")
        print(print_byte_array(bt))
        print("  Size: ", len(bt))
        try:
            print(f"   Elevation: {entry['elevation']:.2f}°, Azimuth: {entry['azimuth']:.2f}°\n")
        except Exception as e:
            print(f"   Error: {e}\n")