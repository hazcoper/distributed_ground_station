import socket

#con0192

# TCP server settings
HOST = "172.20.38.211"  # Change to the server's address
PORT = 3000         # Port to connect to

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

def start_tnc_client():
    """Start a simple TNC client that receives and prints KISS data as bytes."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
        client.connect((HOST, PORT))
        print(f"Connected to server at {HOST}:{PORT}")

        buffer = bytearray()
        while True:
            data = client.recv(1024)
            if not data:
                print("Disconnected from server.")
                break
            print("Received this: ", data)
            # Process data
            for byte in data:
                if byte == KISS_FEND:
                    if buffer:
                        # Decode KISS frame
                        decoded_data = decode_kiss(buffer[1:])
                        # Print the decoded data as a list of bytes in hex format
                        print("Received data:", ' '.join(f"0x{b:02X}" for b in decoded_data))
                        print("\n")
                        buffer.clear()
                else:
                    buffer.append(byte)

if __name__ == "__main__":
    start_tnc_client()
