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
import traceback


class Passage_Scheduler:

    def __init__(self):
        self.Config = ConfigParser()
        self.Config.loadDefaultValues()
        self.Config.loadConfig()

        # Set up logger
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
        if not self.logger.handlers:
            self.logger.addHandler(console_handler)
            self.logger.addHandler(file_handler)

        # Get the endpoints of the different modules
        self.master_host = self.Config.get("master_rpc_host")
        self.master_port = self.Config.get("master_rpc_port")
        self.master_proxy = xmlrpc.client.ServerProxy(f"http://{self.master_host}:{self.master_port}")
        self.logger.debug(f"[INIT] Master endpoint: {self.master_host}:{self.master_port}")

        self.sat_predictor_host = self.Config.get("sat_predictor_rpc_host")
        self.sat_predictor_port = self.Config.get("sat_predictor_rpc_port")
        self.sat_predictor_proxy = xmlrpc.client.ServerProxy(f"http://{self.sat_predictor_host}:{self.sat_predictor_port}")
        self.logger.debug(f"[INIT] SatPredictor endpoint: {self.sat_predictor_host}:{self.sat_predictor_port}")

        # Define the expected keys and types for the passage data
        self.EX_PASSAGE_KEYS = [
            "azimuth_elevation", "tle_line1", "tle_line2", "time_interval",
            "aos", "los", "start_azimuth", "end_azimuth", "max_elevation"
        ]
        self.EX_PASSAGE_TYPES = [list, str, str, list, float, float, float, float, float]

    def typeChecking(self, data_dict, expected_keys, expected_types):
        """
        Receives a dictionary and checks if the keys are the same as the expected keys.
        """
        self.logger.debug("[TYPE_CHECK] Validating passage data structure.")
        if not isinstance(data_dict, dict):
            self.logger.error("[TYPE_CHECK] Data is not a dictionary.")
            return False

        if len(expected_keys) != len(expected_types):
            self.logger.error("[TYPE_CHECK] Keys and types length mismatch.")
            return False

        if set(data_dict.keys()) != set(expected_keys):
            self.logger.error(f"[TYPE_CHECK] Keys mismatch: {data_dict.keys()} vs {expected_keys}.")
            return False

        for key, value in data_dict.items():
            expected_type = expected_types[expected_keys.index(key)]
            if not isinstance(value, expected_type):
                self.logger.error(f"[TYPE_CHECK] Key '{key}' has incorrect type. Expected: {expected_type}, Got: {type(value)}.")
                return False

        self.logger.debug("[TYPE_CHECK] Passage data validated successfully.")
        return True

    def checkPassages(self):
        """
        This function will be called every hour.
        """
        self.logger.info("[CHECK_PASSAGES] Starting passage check.")

        # check if everything has been cancelled
        all_jobs = schedule.get_jobs()
        self.logger.debug(f"[CHECK_PASSAGES] Active jobs: {all_jobs}")

        try:
            next_passages = self.sat_predictor_proxy.remoteGetNextPasses()
            self.logger.info(f"[CHECK_PASSAGES] Retrieved {len(next_passages)} passages.")
        except Exception as e:
            self.logger.error(f"[CHECK_PASSAGES] Error fetching passages: {e}")
            self.logger.debug(traceback.format_exc())
            schedule.every(10).seconds.do(self.checkPassages)
            return schedule.CancelJob

        for passage in next_passages:
            if not self.typeChecking(passage, self.EX_PASSAGE_KEYS, self.EX_PASSAGE_TYPES):
                self.logger.error("[CHECK_PASSAGES] Invalid passage data format detected.")
                self.logger.debug(f"[CHECK_PASSAGES] Passage data: {passage}")
                return schedule.CancelJob
                

        current_time = datetime.datetime.now().timestamp()
        closest_passage = None
        closest_passage_time = None

        for passage in next_passages:
            if closest_passage_time is None or passage["aos"] < closest_passage_time:
                closest_passage_time = passage["aos"]
                closest_passage = passage

        if not closest_passage:
            self.logger.warning("[CHECK_PASSAGES] No valid passages found.")
            return schedule.CancelJob
            

        seconds_until_next_passage = closest_passage["aos"] - current_time
        self.logger.info(f"[CHECK_PASSAGES] Closest passage in {seconds_until_next_passage / 60:.2f} minutes.")

        if seconds_until_next_passage < 3600:
            self.logger.info("[CHECK_PASSAGES] Scheduling the next passage.")
            try:
                self.master_proxy.remotePreparePass(closest_passage)
                self.logger.debug("[CHECK_PASSAGES] Passage scheduled successfully.")
            except Exception as e:
                self.logger.error(f"[CHECK_PASSAGES] Error preparing passage: {e}")
                self.logger.debug(traceback.format_exc())
                return schedule.CancelJob


            los_time = closest_passage["los"]
            scheduled_los_time = datetime.datetime.fromtimestamp(los_time) + datetime.timedelta(minutes=1)
            formatted_los_time = scheduled_los_time.strftime("%H:%M")
            self.logger.info(f"[SCHEDULE] LOS scheduled for: {formatted_los_time}.")
            schedule.every().day.at(formatted_los_time).do(self.finishPassage)

        next_run_time = max(60, seconds_until_next_passage / 60 + 20) if seconds_until_next_passage < 3600 else 60
        self.logger.info(f"[SCHEDULE] Next passage check scheduled in {next_run_time} minutes.")
        
        # logs the list of jobs
        all_jobs = schedule.get_jobs()
        self.logger.debug(f"[CHECK_PASSAGES] Active jobs: {all_jobs}")
        
        schedule.every(next_run_time).minutes.do(self.checkPassages)
        return schedule.CancelJob
        

    def finishPassage(self):
        """
        Function to end the current pass and notify the master.
        """
        self.logger.info("[FINISH_PASSAGE] Ending the current passage.")
        try:
            self.master_proxy.remoteEndPass()
            self.logger.info("[FINISH_PASSAGE] Passage ended successfully.")
        except Exception as e:
            self.logger.error(f"[FINISH_PASSAGE] Error ending passage: {e}")
            self.logger.debug(traceback.format_exc())
            return schedule.CancelJob

        return schedule.CancelJob


if __name__ == "__main__":
    PS = Passage_Scheduler()
    PS.checkPassages()

    counter = 0
    while True:
        try:
            schedule.run_pending()
            if counter > 30:
                all_jobs = schedule.get_jobs()
                PS.logger.debug(f"[MAIN] Active jobs: {all_jobs}")
                counter = 0
            time.sleep(1)
            counter += 1
        except KeyboardInterrupt:
            PS.logger.info("[MAIN] Scheduler stopped by user.")
            break
        except Exception as e:
            PS.logger.error(f"[MAIN] Unexpected error: {e}")
            PS.logger.debug(traceback.format_exc())
