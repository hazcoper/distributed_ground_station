import socket
import multiprocessing
import threading
from datetime import datetime
from multiprocessing import Lock, Manager
import time
import pickle
import signal
import sys

from SatellitePredictor import SatellitePredictor  # Ensure this is the class you created


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

def tnc_client(HOST, PORT, data_keeper, lock, predictor):
    """Connect to a TNC server and listen for KISS data."""
    while True:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
                print(f"Attempting to connect to server at {HOST}:{PORT}")
                client.connect((HOST, PORT))
                print(f"Connected to server at {HOST}:{PORT}")

                buffer = bytearray()
                while True:
                    try:
                        data = client.recv(1024)
                        if not data:
                            print(f"Disconnected from server at {HOST}:{PORT}")
                            break

                        # Process received data
                        for byte in data:
                            if byte == KISS_FEND:
                                if buffer:
                                    # Decode KISS frame
                                    decoded_data = decode_kiss(buffer[1:])
                                    
                                    # Get current satellite position
                                    try:
                                        elevation, azimuth, distance = predictor.getSatellitePosition()
                                    except ValueError as e:
                                        print(f"Error calculating satellite position: {e}")
                                        elevation, azimuth = None, None

                                    # Store the data with metadata
                                    timestamp = datetime.now().isoformat()
                                    entry = {
                                        "host": HOST,
                                        "port": PORT,
                                        "timestamp": timestamp,
                                        "data": list(decoded_data),
                                        "elevation": elevation,
                                        "azimuth": azimuth,
                                    }
                                    with lock:
                                        data_keeper.append(entry)
                                    print(f"Received data from {HOST}:{PORT} at {timestamp}")
                                    print(f"Satellite Position - Elevation: {elevation}°, Azimuth: {azimuth}°")
                                    buffer.clear()
                            else:
                                buffer.append(byte)
                    except Exception as e:
                        print(f"Error receiving data from {HOST}:{PORT}: {e}")
                        break
        except Exception as e:
            print(f"Unable to connect to {HOST}:{PORT}. Retrying in 5 seconds. Error: {e}")
            time.sleep(5)

def data_manager(data_keeper, lock):
    """Manage shared data and allow other processes to interact with it."""
    while True:
        with lock:
            print(f"Current data count: {len(data_keeper)}")
        threading.Event().wait(5)  # Wait 5 seconds before printing again

def dump_data_to_file(data_keeper, lock):
    """Dump all data to a timestamped pickle file."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_name = f"data_dump_{timestamp}.pkl"
    with lock:
        with open(file_name, "wb") as f:
            pickle.dump(list(data_keeper), f)
        print(f"Data successfully saved to {file_name}")

def handle_exit(signum, frame, data_keeper=None, lock=None):
    """Handle termination signals to clean up and save data."""
    print("\nTermination signal received. Saving data...")
    if data_keeper is not None and lock is not None:
        dump_data_to_file(data_keeper, lock)
    sys.exit(0)

if __name__ == "__main__":
    host_list = ["178.166.52.139", "localhost"]
    port_list = [12000, 7000]

    # Manager for shared data
    manager = Manager()
    data_keeper = manager.list()
    lock = Lock()

    # Initialize SatellitePredictor
    predictor = SatellitePredictor()

    # Register signal handlers
    signal.signal(signal.SIGINT, lambda s, f: handle_exit(s, f, data_keeper, lock))
    signal.signal(signal.SIGTERM, lambda s, f: handle_exit(s, f, data_keeper, lock))

    # Start a process for each server
    processes = []
    for host, port in zip(host_list, port_list):
        p = multiprocessing.Process(target=tnc_client, args=(host, port, data_keeper, lock, predictor))
        processes.append(p)
        p.start()

    # Start the data manager
    data_manager_process = multiprocessing.Process(target=data_manager, args=(data_keeper, lock))
    data_manager_process.start()

    # Wait for all processes to finish
    try:
        for p in processes:
            p.join()
    except KeyboardInterrupt:
        print("Interrupted by user.")

    # Terminate the data manager and dump data before exiting
    data_manager_process.terminate()
    dump_data_to_file(data_keeper, lock)

