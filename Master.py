"""
This is the master that will be responbile for the interactions between the different modules
"""


from xmlrpc.server import SimpleXMLRPCServer
import xmlrpc.client
from ConfigParser import ConfigParser
import logging
import os
import datetime



class Master:
    
    def __init__(self):
        self.Config = ConfigParser()
        self.Config.loadDefaultValues()
        self.Config.loadConfig()
        
                # set up logger
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.setLevel(logging.DEBUG)

        # Create console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)

        # Create file handler
        log_path = os.path.join(self.Config.get("log_folder"), f"{self.__class__.__name__}.log")
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
    
        
        # get the endpoints of the different modules
        self.data_warehouse_host = self.Config.get("data_warehouse_rpc_host")
        self.data_warehouse_port = self.Config.get("data_warehouse_rpc_port")
        self.data_warehouse_proxy = xmlrpc.client.ServerProxy(f"http://{self.data_warehouse_host}:{self.data_warehouse_port}")
        self.logger.debug(f"Data warehouse endpoint: {self.data_warehouse_host}:{self.data_warehouse_port}")
        
        # endpooints for the sat predictor
        self.sat_predict_host = self.Config.get("sat_predictor_rpc_host")
        self.sat_predict_port = self.Config.get("sat_predictor_rpc_port")
        self.sat_predict_proxy = xmlrpc.client.ServerProxy(f"http://{self.sat_predict_host}:{self.sat_predict_port}")
        self.logger.debug(f"SatPredictor endpoint: {self.sat_predict_host}:{self.sat_predict_port}")
        
        
        # Setup the remote funcitons
        self.server_host = self.Config.get("master_rpc_host")
        self.server_port = self.Config.get("master_rpc_port")
        self.logger.debug(f"Master server endpoint: {self.server_host}:{self.server_port}")
        self.server = SimpleXMLRPCServer((self.server_host, self.server_port))
        self.registerFunctoins()
        
        # init TLE values to avoid problems
        self.current_tle_line1 = ""
        self.current_tle_line2 = ""
        
        self.passage_number = -1  # number that will keep track of the orbits. used to help index them
        # maybe in  the future i could change this to somehting more cleaver
    
    def registerFunctoins(self):
        """
        Will register the functions that will be available to the cliets
        """

        self.server.register_function(self.remoteUpdateTle)
        self.server.register_function(self.remoteReceiveKiss)
        self.server.register_function(self.remotePreparePass)
        self.server.register_function(self.remoteEndPass)
        
        
    ######################################################################################
    #
    # Auxiliary functions
    #
    #
    ######################################################################################
    
    def getCurrentPassageNumber(self):
        """
        Gets the current passage number
        
        -1 means that there are satellites in line of sight
        here I will implement the logic that will see if the satellite is in line of sight or not
        if its not, it will return -1
        """
        
        try:
            elevation, azimuth, distance = self.sat_predict_proxy.remoteGetSatellitePosition()
        except Exception as e:
            self.logger.error(f"Error while trying to get satellite position in getCurrentPassage: {e}")
            return -1
        
        return_number = -1
        
        if elevation >= 0:
            return_number = self.passage_number
        
        self.logger.debug(f"Getting the current passage number: {return_number}")
                    
        return return_number
    
        
        
    ######################################################################################
    #
    # Remote functions that will be called by the different modules
    #
    #
    ######################################################################################
    
    def remotePreparePass(self, data_dict):
        """
        Called by passage scheduler when it finds a passage that is less than a hour away
        Locally I will update the passage number. I am updating before the passage has started
        But that is not a problem. Because when I receive a message I check if the elevation is bigger than 0 or not
        
        in a way this is just a function that will increment the local passage number
            but it will also trigger master to acquire information about the next passage to store in on the database
        """
        
        self.passage_number += 1
        self.logger.debug(f"New passage number: {self.passage_number}")
        
        # add the passage number to the data_dict
        data_dict["passage_number"] = self.passage_number
        # add the frame list
        data_dict["frame_list"] = []
        data_dict["frame_count"] = 0
        # add gs clients
        data_dict["gs_clients"] = []
        self.logger.warning("[TODO] - Implement logic to get the active ground stations")
        
        
        for key in data_dict:
            self.logger.debug(f"  {key}: {type(data_dict[key])}")
        
        # forward the data to the data warehouse
        try:
            self.data_warehouse_proxy.remoteCreatePassage(data_dict)
        except Exception as e:
            self.logger.error(f"Error while forwarding passage to the data warehouse: {e}")
            return False
        
        return True
    
    def remoteEndPass(self):
        """
        Function that is triggered when current pass reaches LOS
        it will tirgger the datawarehoues to save the passage
        it will also trigger satellite predictor to update the tle
        """
        
        self.logger.debug(f"Ending passage number: {self.passage_number}")
        
        # forward the data to the data warehouse
        try:
            self.data_warehouse_proxy.remoteSavePassage()
        except Exception as e:
            self.logger.error(f"Error while ending passage to the data warehouse: {e}")
            return False
        
        # trigger the sat predictor to update the TLE
        self.logger.debug(f"Triggering sat predictor to update TLE")
        try:
            self.sat_predict_proxy.remoteUpdateTle()
        except Exception as e:
            self.logger.error(f"Error while triggering sat predictor to update TLE: {e}")
            return False
        
        return True
        
    def remoteReceiveKiss(self, kiss: str, tnc_client_ip: str, tnc_client_port: int, timestamp: float):
        """
        Called by kiss client when it receives a new kiss packet
        kiss -> the frame represented in a string "0x86 0xa2 0x86 0xa2 0x86 0xa2 ..."
            [check] - maybe it would be better to send the bytes directly
        host -> the host that sent the packet
        port -> the port that sent the packet
        timestamp -> the time the packet was received
            represented as a float
            
        Recevies the frame
        Gets the current information about the satellite position
        Gets the passage number
        Packages the data on a dictionary
        Sends to the datawarehouse

        It will aquire some infromation about the satellite position and send it all to the data warehouse            
        """
        
        self.logger.info(f"Received new KISS data: {kiss}")
        self.logger.info(f"  Host: {tnc_client_ip}, Port: {tnc_client_port}, Timestamp: {timestamp}")
        human_readable_time = datetime.datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
        
        # get the information about the satellite location
        try:
            elevation, azimuth, distance = self.sat_predict_proxy.remoteGetSatellitePosition()
        except Exception as e:
            self.logger.error(f"Error while trying to get satellite position: {e}")
            return False
        
        self.logger.debug(f"  Satellite position: Elevation: {elevation:.2f}°, Azimuth: {azimuth:.2f}°")
        
        passage_number = self.getCurrentPassageNumber()
        
        # if passage_number == -1:
        #     self.logger.debug(f"  Satellite not in line of sight, not saving data")
        #     return False
        
        output_dict = {
            "timestamp": timestamp,                          # float timestamp when the frame was received
            "elevation": elevation,                          # float elevation of the satellite
            "azimuth": azimuth,                              # float azimuth of the satellite
            "distance": distance,                            # float distance of the satellite
            "tnc_client": (tnc_client_ip, tnc_client_port),    # [str,int] tnc_client that decoded the message
            "passage_number": passage_number,                # int passage number
            "kiss": kiss,                                    # str representaiton of the frame (0x86 0xa2 0x86 0xa2 0x86 0xa2 ...)
        }
        
        # who is going to group the frames into passges? the frame should be inserted in a dictionary of passages
        # when it is out of a passage, should be in a key of its own
        # maybe i should do the matching here, send the data to the data warehouse and the data warehouse will add them to the respective passage
        
        # forward the data to the data warehouse
        try:
            self.data_warehouse_proxy.remoteSaveKiss(output_dict)
            self.logger.debug(f"Data forwarded to the data warehouse")  
        except Exception as e:
            self.logger.error(f"Error while forwarding KISS to the data warehouse: {e}")
            return False
        
        return True
    
    
    def remoteUpdateTle(self, new_tle: str, timestamp: float):
        """
        Called by sat predict when it updates a new TLE
        The goal of this function os to forward the TLE to the data warehouse
        """
        
        self.logger.debug(f"Received new TLE data: {new_tle}")
        
        # eventually should apply some checks here, but not sure what checks to implement yet
        
        self.current_tle_line1 = new_tle.split("\n")[0]
        self.current_tle_line2 = new_tle.split("\n")[1]
        
        # forward the data to the data warehouse
        try:
            self.data_warehouse_proxy.remoteSaveTle(new_tle, timestamp)
        except Exception as e:
            self.logger.error(f"Error while forwarding TLE to the data warehouse: {e}")
            return False
        
        return True



if __name__ == "__main__":

    my_master = Master()

    my_master.logger.info(f"Master server started at {my_master.server_host}:{my_master.server_port}")

    my_master.server.serve_forever()