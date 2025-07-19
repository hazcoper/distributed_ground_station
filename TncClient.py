"""
This will implement a class that will handle communication over kiss tcp to the TNC
The responsibility of this class is to receive the kiss frames and forward them to the master

The master will then deal with the frames appropriately

Frame Dictionary:
    float                    Timestamp of the frame (clarify exactly what this time refers to)
    float                    Elevation of the satellite when the frame was received
    float                    Azimuth of the satellite when the frame was received
    float                    Distance of the satellite when the frame was received
    list(str, port)          GS that decoded the message
    int                      Passage number  ([check] - not sure if it makes sense to have this here )
    str                      KISS frame
    
but as far is this module knows, this does not matter
    this module will only send the following data to master
        kiss (str) - the kiss frame "0x86 0xa2 0x86 0xa2 0x86 0xa2 ..."
        tnc_client_ip (str) - the ip of the tnc client that decoded the message
        tnc_client_port (int) - the port of the tnc client that decoded the message
        timestamp (float) - the timestamp when the frame was received
"""


import xmlrpc.client
from ConfigParser import ConfigParser
import logging
import socket
import threading
import os


import binascii
import datetime
import time

# KISS special characters
KISS_FEND = 0xC0  # Frame End
KISS_FESC = 0xDB  # Frame Escape
KISS_TFEND = 0xDC # Transposed Frame End
KISS_TFESC = 0xDD # Transposed Frame Escape

def print_byte_array(byte_array):
    hex_data = binascii.hexlify(byte_array).decode()  # Convert to hex string
    # Add \x prefix to each byte
    formatted_hex_data = ''.join(f'0x{hex_data[i:i+2]} ' for i in range(0, len(hex_data), 2))
    # print(formatted_hex_data)
    return formatted_hex_data

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

class TncClient:
    def __init__(self, tncHost, tncPort):
        
        self.Config = ConfigParser()
        self.Config.loadDefaultValues()
        self.Config.loadConfig()
        
        # set up logger
        self.logger = logging.getLogger(f"TC:{tncHost}:{tncPort}")
        self.logger.setLevel(logging.DEBUG)

        # Create console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)

        # Create file handler
        log_path = os.path.join(self.Config.get("log_folder"), f"TC_{tncHost}_{tncPort}.log")
        file_handler = logging.FileHandler(log_path)
        file_handler.setLevel(logging.DEBUG)

        # Define a common formatter
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

        # Attach the formatter to handlers
        console_handler.setFormatter(formatter)
        file_handler.setFormatter(formatter)

        # Add handlers to the logger
        self.logger.addHandler(console_handler)
        self.logger.addHandler(file_handler)
    
        
        # set up the necessary endpoints
        self.master_host = self.Config.get("master_rpc_host")
        self.master_port = self.Config.get("master_rpc_port")
        self.master_proxy = xmlrpc.client.ServerProxy(f"http://{self.master_host}:{self.master_port}")
        self.logger.debug(f"Master endpoint: {self.master_host}:{self.master_port}")
        
        # set up the tnc host and port
        self.tncHost = tncHost
        self.tncPort = tncPort
        self.client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        
        self.buffer = bytearray()
        
        self.last_message_timestamp = 0
        
        
    
    def attemptConnection(self):
        """
        Will remain in loop attempting to connect to TNC
        """
        self.logger.info(f"Attempting to connect to TNC at {self.tncHost}:{self.tncPort}")
        while True:
            try:
                self.client.connect((self.tncHost, self.tncPort))
                self.logger.info(f"Connected to TNC at {self.tncHost}:{self.tncPort}")
                break
            except Exception as e:
                self.logger.error(f"Failed to connect to TNC at {self.tncHost}:{self.tncPort}, retrying in 30 seconds")
                self.logger.error(f"  Error: {e}")
                time.sleep(30)


    def receiveData(self):
        try:
            # set timeout
            self.logger.debug(f"Receiving data from TNC at {self.tncHost}:{self.tncPort}")
            self.data = self.client.recv(1024)
            self.last_message_timestamp = datetime.datetime.now().timestamp()    # not sure if this is okay. Do i get many things that are not a valid message?
            
            # check to see if client has disconnected
            if self.data == b'':
                self.logger.warning(f"Connection closed by TNC at {self.tncHost}:{self.tncPort}")
                self.client.close()
                self.client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  # recreate the socket
                return False  # this will forece to enter attmptConnection

        except Exception as e:
            self.logger.error(f"Error receiving data from TNC: {e}")
            return False
        return True
    
    def processData(self):
        """
        Using the receievd data from TNC. it will process the data
        """
        # Process received data
        self.logger.debug("Processing received data")
        for byte in self.data:
            if byte == KISS_FEND:
                if self.buffer:
                    # Decode KISS frame
                    decoded_data = decode_kiss(self.buffer[1:])
                    self.buffer.clear()
                    self.logger.debug(f"  Decoded data: {decoded_data}")
                    return decoded_data
            else:
                self.buffer.append(byte)

    def forwardData(self, data):
        """
        It will forward the data to the master
        kiss (str) - the kiss frame "0x86 0xa2 0x86 0xa2 0x86 0xa2 ..."
        tnc_client_ip (str) - the ip of the tnc client that decoded the message
        tnc_client_port (int) - the port of the tnc client that decoded the message
        timestamp (float) - the timestamp when the frame was received
        """
        
        if data is None:
            self.logger.warning("Received None data to forward, skipping")
            return False
        
        # conevrt the data to a string
        byte_str = print_byte_array(data)
        self.logger.debug(f"Forwarding data to the master: {byte_str}")
        try:
            self.master_proxy.remoteReceiveKiss(byte_str, self.tncHost, self.tncPort, self.last_message_timestamp)
            self.logger.debug(f"Data forwarded to the master\n")
        except Exception as e:
            self.logger.error(f"Error while forwarding KISS to the master: {e}\n")
            return False
        
        return True

    def tncLoop(self):
        """
        Main loop for the TNC client
        """
        
        while True:
            try:
                if self.receiveData():
                    
                    if len(self.data) < 10:   # make sure that we are not receiving garbage
                        time.sleep(1)    # add a little delay to reduce the load on the system
                        continue
                    
                    self.logger.debug("Received data from TNC")
                    self.logger.debug(f"  Data: {self.data}")
                    
                    decoded_data = self.processData()                    
                    self.forwardData(decoded_data)
                else:
                    self.attemptConnection()
            except Exception as e:
                self.logger.error(f"Error in main loop: {e}")
                self.attemptConnection()

def startSingle(tncHost, tncPort):
    tnc = TncClient(tncHost, tncPort)
    tnc.attemptConnection()
    tnc.tncLoop()
    

                
if __name__ == "__main__":
    
    host_list = ["172.20.38.89", "172.20.38.66"]
    port_list = [8001, 7000]
    
    threading_list = []
    
    for ip, port in zip(host_list, port_list):  
        t = threading.Thread(target=startSingle, args=(ip, port))
        t.start()
        threading_list.append(t)
    
    for t in threading_list:
        t.join()


