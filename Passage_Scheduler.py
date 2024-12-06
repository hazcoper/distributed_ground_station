"""
The goal of this file is to implement the passage scheduler
    it is responsbile for getting the information about the passages and scheduling them 
    
every hour need to get the information about the passages
    will check if there is passage happening in less than a hour
    if there is then schedule it
    
Scheduling the passage is equivalent to creating the passage in the master
"""


import xmlrpc.client
from ConfigParser import ConfigParser
import logging
import os
import datetime
import schedule
import time

class Passage_Scheduler:
    
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
        self.master_host = self.Config.get("master_rpc_host")
        self.master_port = self.Config.get("master_rpc_port")
        self.master_proxy = xmlrpc.client.ServerProxy(f"http://{self.master_host}:{self.master_port}")
        self.logger.debug(f"Master endpoint: {self.master_host}:{self.master_port}")

        # endpooints for the sat predictor
        self.sat_predictor_host = self.Config.get("sat_predictor_rpc_host")
        self.sat_predictor_port = self.Config.get("sat_predictor_rpc_port")
        self.sat_predictor_proxy = xmlrpc.client.ServerProxy(f"http://{self.sat_predictor_host}:{self.sat_predictor_port}")
        self.logger.debug(f"SatPredictor endpoint: {self.sat_predictor_host}:{self.sat_predictor_port}")
        
        self.EX_PASSAGE_KEYS = ["azimuth_elevation", "tle_line1", "tle_line2","time_interval", 
                                "aos", "los", "start_azimuth", "end_azimuth", "max_elevation"]
        self.EX_PASSAGE_TYPES = [list, str, str, list, float, float, float, float, float]
    
        
        
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
    
    
    def checkPassages(self):
        """
        This function will be called every hour
        
        Ask SatPredictor for the next x passages
            It will receive a list of dictionaries
                each dict will contain the data for a passage
        
        check if any of the passages are happening in less than an hour
            if they are then schedule them
            scheduling them is equivalent to calling the master to create the passage
        """
        
        
        # get the list with the next passages
        try:
            next_passages = self.sat_predictor_proxy.remoteGetNextPasses()
        except Exception as E:
            self.logger.error(f"Error while trying to get next passages: {E}")
            # schedule to run again in 10 seconds
            schedule.every(10).seconds.do(self.checkPassages)
            return False

        # check if the data is correct
        for passage in next_passages:
            if not self.typeChecking(passage, self.EX_PASSAGE_KEYS, self.EX_PASSAGE_TYPES):
                self.logger.error("Check Passage data is not correct")
                self.logger.error(f"  {passage}")
                return False
        
        # print the list of the next passages in human readable format
        self.logger.debug("Next passages:")
        counter = 0
        for passage in next_passages:
            # convert aos to huamn readable format
            self.logger.debug(f"Counter {counter}")
            self.logger.debug(f"   Aos: {datetime.datetime.fromtimestamp(passage['aos'])}")
            self.logger.debug(f"   Los: {datetime.datetime.fromtimestamp(passage['los'])}")
            self.logger.debug(f"   Max Elevation: {passage['max_elevation']}")
            self.logger.debug(f"   Start Azimuth: {passage['start_azimuth']}, End Azimuth: {passage['end_azimuth']}")
            counter += 1

            
        # get the current time
        current_time = datetime.datetime.now().timestamp()
        
        # get the closest passage to current time
        closest_passage = None
        closest_passage_time = None
        
        # technically I do not   need to do this because the passages are already sorted
        for passage in next_passages:
            # check if it is the closest passage
            if closest_passage_time is None or passage["aos"] < closest_passage_time:
                closest_passage_time = passage["aos"]
                closest_passage = passage
                
        
        
        seconds_until_next_passage = closest_passage["aos"] - current_time
        self.logger.debug(f"Closest passage: {closest_passage}")
        self.logger.debug(f"Seconds until next passage: {seconds_until_next_passage}")
        self.logger.debug(f"minutes until next passage: {seconds_until_next_passage/60}")
        self.logger.debug(f"hours until next passage: {seconds_until_next_passage/3600}")
        
        # check if need to warn master
        if seconds_until_next_passage < 3600:
            self.logger.debug("Need to schedule the next passage")
            self.master_proxy.remotePreparePass(closest_passage)
            
            # schedule function to trigger at los
            los_time = closest_passage["los"]
            scheduled_los_time = datetime.datetime.fromtimestamp(los_time) + datetime.timedelta(minutes=1)
            formatted_los_time = scheduled_los_time.strftime("%H:%M")
            self.logger.debug(f"Scheduled los time: {formatted_los_time}")
            schedule.every().day.at(formatted_los_time).do(self.finishPassage)
            
        
        # schedule the next run
        # i want to check every hour. But if there is a passage happening in less than an hour
        #  especially if its happening in 60 min - 12 min (give or take the lenght of the passage)
        # It means that the next time i run this function the satelite will still be in line of sight
        # So i want it to schedule max(60, time_until_next_passage + 20)            
        next_run_time = max(60, seconds_until_next_passage / 60 + 20) if seconds_until_next_passage < 3600 else 60
        self.logger.debug(f"Next run time: {next_run_time}")
        initial_run_time = datetime.datetime.now() + datetime.timedelta(minutes=next_run_time)
        formatted_time = initial_run_time.strftime("%H:%M")
        self.logger.debug(f"Scheduled next run time to: {formatted_time}")
        
        schedule.every().day.at(formatted_time).do(self.checkPassages)
        
        return schedule.CancelJob
    
    def finishPassage(self):
        """
        Function that will be triggered when the current pass reaches los
        it will tell the master that the pass has finish
            the master will tell the Datawarehour to save the data
        """
        
        self.logger.debug("Passage has finished")
        
        try:
            self.master_proxy.remoteEndPass()
            self.logger.debug(" Passage finished")
        except Exception as E:
            self.logger.error(f"Error while trying to finish the passage: {E}")
            return schedule.CancelJob
    
        return schedule.CancelJob

        
if __name__ == "__main__":
    PS = Passage_Scheduler()
    PS.checkPassages()
    
    # get a list of all shcedule
    all_jobs = schedule.get_jobs()
    print(all_jobs)
    
    counter = 0
    while True:
        schedule.run_pending()
        if counter > 30:
            all_jobs = schedule.get_jobs()
            print(all_jobs)
            counter = 0
        time.sleep(1)
        counter += 1
    