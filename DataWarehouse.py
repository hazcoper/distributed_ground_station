"""
This is the program that will be responsible for handling all of the data
it will organize the data in the correct way
deal with saving and loading data...

all the other modules refer to time as float values. but here we will receive that time and convert it to a human readable format

Passage Dictionary:
    int:                     Reference to the passage  (potentially could be a hash, or just a number)
    list[[float,float]]      List of azimuth and elevation values for the passage
    str                      TLE_line1
    str                      TLE_line2
    list[[str, port]]        List of active GS clients that were receiving data in this passage
    int                      Number of frames received in this passage
    float                    AOS for the passage (epoch)
    float                    LOS for the passage (epoch)
    float                    start azimuth (degrees) for the passage
    float                    end azimuth (degrees) for the passage
    float                    max elevation (degrees) for the passage
    dict                     Dictionary of frames received in this passage


Frame Dictionary:
    float                    Timestamp of the frame (clarify exactly what this time refers to)
    float                    Elevation of the satellite when the frame was received
    float                    Azimuth of the satellite when the frame was received
    float                    Distance of the satellite when the frame was received
    list(str, port)          GS that decoded the message
    int                      Passage number  ([check] - not sure if it makes sense to have this here )
    str                      KISS frame
"""


from xmlrpc.server import SimpleXMLRPCServer
import xmlrpc.client
from ConfigParser import ConfigParser
import logging
import json
import os

from datetime import datetime, timezone





class DataWarehouse:
    
    
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
    
        
        
        # Setup the remote funcitons
        self.server_host = self.Config.get("data_warehouse_rpc_host")
        self.server_port = self.Config.get("data_warehouse_rpc_port")
        self.logger.debug(f"Datawarehouse server endpoint: {self.server_host}:{self.server_port}")
        self.server = SimpleXMLRPCServer((self.server_host, self.server_port))
        self.registerFunctoins()
        
        
        # this will contain all of the passages from the satelite, independent if that was received or not
        # self.passageDict = {          # this has been removed, it does not really make sense to save the trash
        #     -1: {'frame_list': []}   # add initial slot for messages out of aos
        # }
        self.passageDict = {}
        
        self.EX_FRAME_KEYS = ["timestamp", "elevation", "azimuth", "distance", "tnc_client", "passage_number", "kiss"]
        self.EX_FRAME_TYPES = [float, float, float, float, list, int, str]
        
        self.EX_PASSAGE_KEYS = ["passage_number", "azimuth_elevation", "tle_line1", "tle_line2", "gs_clients", "frame_count", 
                                "aos", "los", "start_azimuth", "end_azimuth", "max_elevation", "time_interval", "frame_list"]
        self.EX_PASSAGE_TYPES = [int, list, str, str, list, int, float, float, float, float, float, list, list]
    
    def registerFunctoins(self):
        """
        Will register the functions that will be available to the cliets
        """
        self.server.register_function(self.remoteUpdateTle)
        self.server.register_function(self.remoteSaveKiss)
        self.server.register_function(self.remoteCreatePassage)
        self.server.register_function(self.remoteSavePassage)
        
    
    ######################################################################################
    #
    # Auxiliary functions
    #
    #
    ######################################################################################
    
    def typeChecking(self, data_dict, expected_keys, expected_types):
        """
        Receives a dictionary and checks if the keys are the same as the expected keys
        """
        
        # check the inputs
        if not isinstance(data_dict, dict):
            self.logger.error("Data is not a dictionary")
            return False
        
        if not type(expected_keys) == list:
            self.logger.error("Expected keys is not a list")
            return False
        
        if not type(expected_types) == list:
            self.logger.error("Expected types is not a list")
            return False
        
        if len(expected_keys) != len(expected_types):
            self.logger.error("Expected keys and types have different lengths")
            return False
        
        # check if the keys are the same
        if set(data_dict.keys()) != set(expected_keys):
            self.logger.error("Keys are different")
            return False
        
        # check if the types are the same
        for key, value in data_dict.items():
            if not isinstance(value, expected_types[expected_keys.index(key)]):
                self.logger.error(f"Key {key} has the wrong type")
                return False
        
        return True
    
    def savePreviousPassage(self):
        """
        When creating a new passage, this will be called
        We will get the data for the old passage and save it

        i will only have at max two passages loaded in memory at any single time
        one is the next passage that is about to start and the other is to capture passages out of aos
        """
        
        if len(self.passageDict) < 1:
            self.logger.debug("No previous passage to save")
            return False
        
        self.logger.debug("Saving previous passage")
        
        # get the passage number
        passage_number = list(self.passageDict.keys())[0]
        
        
        # filename will contain the time of the aos_maxElevation_frameCount
        filename = f"{self.passageDict[passage_number]['aos']}_{int(self.passageDict[passage_number]['max_elevation'])}_{self.passageDict[passage_number]['frame_count']}.json"
        
        self.logger.debug(f"  Filename: {filename}")
        
        self.dumpData(filename)
        
        # reset the passageDict
        # self.passageDict = { -1: {'frame_list': []}}    # this has been removed, it does not make sense to save all the trash
        self.passageDict = {}
        
        return True    
    
    def utcString(self, timestamp: float | None) -> str:
        if not timestamp:
            time = datetime.now(timezone.utc)
        else:
            time = datetime.fromtimestamp(timestamp, timezone.utc)
        return time.strftime('%Y-%m-%d_%H:%M:%S')

    def dumpData(self, filename = None, folder="data"):
        """
        Will dump all of the data to a json file
        """
        
        self.logger.debug("Dumping data to json file")
        
        # filename is the current date and time
        filename = self.utcString(None) + ".json" if filename is None else filename
        
        # check to see if folder exits if not create it
        if not os.path.exists(folder):
            self.logger.debug(f"Creating folder {folder}")
            os.makedirs(folder)
        
        # dump the data
        with open(os.path.join(folder, filename), "w") as f:
            json.dump(self.passageDict, f, indent=4)
        
        return True
    

    ######################################################################################
    #
    # Remote functions that will be called by the different modules
    #
    #
    ######################################################################################
    
    def remoteUpdateTle(self, tle):
        """
        Will update the TLE values
        """
        self.logger.debug(f"Received TLE update: {tle}")
        self.logger.warning("[TODO] - Please implement the logic to store new TLE VALUES")
        return True
    
    def remoteCreatePassage(self, data_dict):
        """
        Called by master when a new passage is about to start
        It will send the necessary values to create that passage in the data warehouse
        """
        
        self.logger.debug(f"Creating new passage:")
        for key in data_dict:
            self.logger.debug(f"  {key}: {data_dict[key]}")
        
        # type checking
        if self.typeChecking(data_dict, self.EX_PASSAGE_KEYS, self.EX_PASSAGE_TYPES) == False:
            self.logger.error("CreatePassage: Data is not in the correct format")
            return False
        self.logger.debug("Data is in the correct format")
        
        # check if passage already exists
        if data_dict["passage_number"] in self.passageDict:
            self.logger.error(f"Passage {data_dict['passage_number']} already exists")
            return False
        self.logger.debug("Passage does not exist")

        # the data already comes in the format that I am expecting, just need to convert the timestamp to human readable
        data_dict["aos"] = self.utcString(data_dict["aos"])
        data_dict["los"] = self.utcString(data_dict["los"])
        
        # add the passage to the dictionary
        self.passageDict[data_dict["passage_number"]] = data_dict
        
        self.logger.debug(f"  Passage has been created")

        return True
    
    def remoteSaveKiss(self, data_dict):
        """
        Receives the data in the format of a dictionary from the master
        Part of the data comes from the kiss client another part comes from sat predict
        """
        
        self.logger.debug(f"Received KISS frame:")
        for key in data_dict:
            self.logger.debug(f"  {key}: {data_dict[key]}")

        # type checking
        if self.typeChecking(data_dict, self.EX_FRAME_KEYS, self.EX_FRAME_TYPES) == False:
            self.logger.error("ReceiveKiss: Data is not in the correct format")
            return False
        
        # the data already comes in the format that i am expecting, just need to convert the timestamp to human readable
        data_dict["timestamp"] = self.utcString(data_dict["timestamp"])[:-3]
        self.logger.debug(f"  Timestamp: {data_dict['timestamp']}")
        
        # check if the passage is already in the dictionary
        if data_dict["passage_number"] not in self.passageDict:
            self.logger.error(f"Passage {data_dict['passage_number']} not found")
            # cant proceed to accept frame if passage does not exits
            return False


        # add the data to the passage
        self.passageDict[data_dict["passage_number"]]["frame_list"].append(data_dict)
        
        # increment the frame_count
        self.passageDict[data_dict["passage_number"]]["frame_count"] += 1
        
        self.logger.debug(f"  Data added to passage {data_dict['passage_number']}")

        return True

    def remoteSavePassage(self):
        """
        The aim of this function is to provide the user with an endpoint that it will allow to 
        to trigger DataWarehouse to save the current data in memory to storage
        this will be triggered when LOS is reached after a passage
        """
        self.logger.debug("Received request to save passage")
        response = self.savePreviousPassage()
        return response
    
if __name__ == "__main__":

    dw = DataWarehouse()
    dw.server.serve_forever()
    
def simpleTest():
    dw = DataWarehouse()
    
    # create fake passage
    # str:                     Reference to the passage  (potentially could be a hash, or just a number)
    # list[[float,float]]      List of azimuth and elevation values for the passage
    # str                      TLE_line1
    # str                      TLE_line2
    # list[[str, port]]        List of active GS clients that were receiving data in this passage
    # int                      Number of frames received in this passage
    # float                    AOS for the passage (epoch)
    # float                    LOS for the passage (epoch)
    # float                    start azimuth (degrees) for the passage
    # float                    end azimuth (degrees) for the passage
    # float                    max elevation (degrees) for the passage
    # dict                     Dictionary of frames received in this passage
    # self.EX_PASSAGE_KEYS = ["passage", "azimuth_elevation", "tle_line1", "tle_line2", "gs_clients", "frame_count", 
    #                             "aos", "los", "start_azimuth", "end_azimuth", "max_elevation", "frame_list"]
    
    passage = {
        "passage": 1,
        "azimuth_elevation": [[0.0, 0.0], [1.0, 1.0], [2.0, 2.0]],
        "tle_line1": "TLE_LINE1",
        "tle_line2": "TLE_LINE2",
        "gs_clients": [["localhost", 1234], ["localhost", 1235]],
        "frame_count": 3,
        "aos": 1618128000.0,
        "los": 1618128100.0,
        "start_azimuth": 0.0,
        "end_azimuth": 2.0,
        "max_elevation": 2.0,
        "frame_list": []
    }
    
    dw.remoteCreatePassage(passage)
    print(dw.passageDict)
    
    
    # create a fake frame
    # Frame Dictionary:
    # float                    Timestamp of the frame (clarify exactly what this time refers to)
    # float                    Elevation of the satellite when the frame was received
    # float                    Azimuth of the satellite when the frame was received
    # float                    Distance of the satellite when the frame was received
    # list(str, port)          GS that decoded the message
    # int                      Passage number  ([check] - not sure if it makes sense to have this here )
    # str                      KISS frame
    # self.EX_PASSAGE_TYPES = [int, list, str, str, list, int, float, float, float, float, float, list]
    
    frame = {
        "timestamp": 1618128000.0,
        "elevation": 0.0,
        "azimuth": 0.0,
        "distance": 0.0,
        "tnc_client": ["localhost", 1234],
        "passage_number": 1,
        "kiss": "KISS_FRAME"
    }
    
    dw.remoteReceiveKiss(frame)
    
    print(dw.passageDict)
