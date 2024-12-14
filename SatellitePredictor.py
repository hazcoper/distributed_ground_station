from datetime import datetime, timedelta
from skyfield.api import Topos, load, EarthSatellite, utc
from scipy.interpolate import CubicSpline
import matplotlib.pyplot as plt
import numpy as np
import requests
import os

from xmlrpc.server import SimpleXMLRPCServer
from ConfigParser import ConfigParser
import logging



def plot_gpredict_like(azimuths, altitudes):
    """
    Creates a Gpredict-like polar plot with azimuth and inverted elevation.
    Args:
        azimuths (list): Azimuth angles in degrees.
        altitudes (list): Elevation angles in degrees.
    """
    # Convert azimuths to radians for the polar plot
    azimuths_rad = np.radians(azimuths)

    # Create the polar plot
    fig, ax = plt.subplots(subplot_kw={'projection': 'polar'}, figsize=(8, 8))
    ax.plot(azimuths_rad, altitudes, label='Satellite Pass', color='blue', lw=2)

    # Set up azimuth gridlines (circular)
    ax.set_theta_zero_location('N')  # North at the top
    ax.set_theta_direction(-1)       # Clockwise direction
    ax.set_thetagrids(range(0, 360, 30), labels=[f"{i}°" for i in range(0, 360, 30)])

    # Invert the elevation scale
    ax.set_rlim(90, 0)  # Radial axis limits (90° at center, 0° at outer edge)
    elevation_ticks = [0, 15, 30, 45, 60, 75, 90]
    ax.set_rgrids(elevation_ticks, labels=[f"{i}°" for i in elevation_ticks], angle=22.5)

    # Add title and legend
    ax.set_title("Satellite Pass (Gpredict Style - Inverted Elevation)", va='bottom', fontsize=14)
    ax.legend(loc='upper right', bbox_to_anchor=(1.3, 1.2))

    # Show the plot
    plt.show()
    
    
class SatellitePredictor:
    def __init__(self, observer_latitude=38.7314, observer_longitude=-9.3024, satcat_id=60238):
        """
        Initializes the SatellitePredictor object with the observer's latitude and longitude
        """
        
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
        self.server_host = self.Config.get("sat_predictor_rpc_host")
        self.server_port = self.Config.get("sat_predictor_rpc_port")
        self.logger.debug(f"SatPredictor server endpoint: {self.server_host}:{self.server_port}")
        self.server = SimpleXMLRPCServer((self.server_host, self.server_port))
        self.registerFunctoins()
        
        
        self.observer = Topos(latitude_degrees=observer_latitude, longitude_degrees=observer_longitude)
        self.ts = load.timescale()
        self.satcat_id = satcat_id
        # self.satcat_id = 22739
        
        self.tle_line1 = None
        self.tle_line2 = None
        self.satellite = None

        # Update the TLE data
        # self.updateTLE()
        self.loadTLE()

        # Create the satellite object
        self.createSatellite()

    def registerFunctoins(self):
        """
        Will register the functions that will be available to the cliets
        """

        self.server.register_function(self.remoteUpdateTle)
        self.server.register_function(self.remoteGetSatellitePosition)
        self.server.register_function(self.remoteGetNextPassage)
        self.server.register_function(self.remoteGetNextPasses)
        
    def remoteUpdateTle(self):
        self.logger.warning("Received a request to update TLE")
        
        try:
            self.updateTLE()
            self.logger.debug("TLE updated successfully")
        except Exception as e:
            self.logger.error(f"Error updating TLE: {e}")
            return False
        return True
    
    def remoteGetSatellitePosition(self):
        """
        Return a list with the elevation, azimuth and distance of the satellite right now
        """
        self.logger.debug("Getting satellite position remote")
        
        elevation, azimuth, distance = self.getSatellitePosition()
        return [float(elevation), float(azimuth), float(distance)]
    
    def remoteGetNextPassage(self):
        self.logger.warning("Please implemenet this next passage")
        return "Next passage"
    
    def remoteGetNextPasses(self):
        """
        Sends a list with many dictionaries inside it
        """
        self.logger.debug("Getting next passage remote")
        
        data_list = self.getNextPasses()
        self.logger.debug(f"  Done getting: {data_list}")
        
        return data_list

    def updateTLE(self):
        """
        Automatically updates the TLE data from CelesTrak using the satcat ID.
        Requires an internet connection.
        """
        try:
            # Fetch TLE data from CelesTrak for the given satcat ID
            url = f"https://celestrak.org/NORAD/elements/gp.php?CATNR={self.satcat_id}"
            response = requests.get(url)
            response.raise_for_status()

            # Parse the TLE lines
            tle_data = response.text.strip().split("\n")
            if len(tle_data) >= 2:
                self.tle_line1 = tle_data[1]
                self.tle_line2 = tle_data[2]
            else:
                raise ValueError(f"TLE data for satellite {self.satcat_id} could not be retrieved.")

            self.logger.debug(f"Updated TLE for satellite {self.satcat_id}")
        except Exception as e:
            self.logger.error(f"Error updating TLE: {e}")

    def loadTLE(self, tle_line1=None, tle_line2=None):
        """
        Given a TLE data, loads them into the class
        """
        default_tle1 = '1 60238U 24128D   24340.58305386  .00011483  00000+0  90379-3 0  9994'
        default_tle2 = '2 60238  61.9939   6.2098 0030061  10.4413 349.7294 15.00873340 22290'

        self.tle_line1 = tle_line1 if tle_line1 is not None else default_tle1
        self.tle_line2 = tle_line2 if tle_line2 is not None else default_tle2

    def createSatellite(self):
        """
        Creates the satellite object based on the TLE data provided
        """
        
        if self.tle_line1 is None or self.tle_line2 is None:
            raise ValueError(f"TLE data not loaded for satellite {self.satcat_id}")

        self.ts = load.timescale()
        self.satellite = EarthSatellite(self.tle_line1, self.tle_line2, str(self.satcat_id), self.ts)

        return self.satellite

    def getSatellitePosition(self):
        """
        Calculate the satellite's position relative to the observer
        Returns the elevation (degrees), azimuth (degrees), and distance (km)
        """
        # Check if the satellite object is created
        if self.satellite is None:
            raise ValueError(f"Satellite object not created for {self.satcat_id}")

        # [TODO] - Findf a better method to determine if the TLE data is outdated
        # # Check if the satellite has up-to-date TLE data
        # if self.satellite.epoch.utc_datetime() < self.ts.now().utc_datetime():
        #     raise ValueError(f"Satellite TLE data outdated for {self.satcat_id}")

        difference = self.satellite - self.observer
        topocentric = difference.at(self.ts.now())

        alt, az, distance = topocentric.altaz()

        # print(f"Elevation: {alt.degrees:.2f}°")  # Elevation above the horizon
        # print(f"Azimuth: {az.degrees:.2f}°")    # Direction from north
        # print(f"Distance: {distance.km:.2f} km")

        return alt.degrees, az.degrees, distance.km

    
    
    def getNextPassage(self):
        """
        Calculates the next passage of the satellite over the observer.
        Returns:
            aos (datetime): Acquisition of Signal (rise time)
            los (datetime): Loss of Signal (set time)
            peak_elevation (float): Maximum elevation (degrees) during the pass
            start_azimuth (float): Azimuth (degrees) at AOS
            end_azimuth (float): Azimuth (degrees) at LOS
        """
        # Check if the satellite object is created
        if self.satellite is None:
            raise ValueError(f"Satellite object not created for {self.satcat_id}")

        # Get the current time
        now = self.ts.now()
        

        # Define a window of time to search for the next passage
        t0 = now
        t1 = self.ts.utc(now.utc_datetime() + timedelta(days=1))  # Search for the next 24 hours

        # Calculate events (rise, culmination, set)
        try:
            times, events = self.satellite.find_events(self.observer, t0, t1, altitude_degrees=0.0)
        except ValueError as e:
            self.logger.error(f"Error finding events: {e}")
            return None, None, None, None, None

        aos, los, peak_elevation = None, None, 0
        start_azimuth, end_azimuth = None, None

        for i, event in enumerate(events):
            time = times[i].utc_datetime()

            if event == 0:  # Rise (AOS)
                aos = time
                topocentric = (self.satellite - self.observer).at(times[i])
                start_azimuth = topocentric.altaz()[1].degrees
            elif event == 1:  # Culmination (Peak)
                topocentric = (self.satellite - self.observer).at(times[i])
                peak_elevation = max(peak_elevation, topocentric.altaz()[0].degrees)
            elif event == 2:  # Set (LOS)
                los = time
                topocentric = (self.satellite - self.observer).at(times[i])
                end_azimuth = topocentric.altaz()[1].degrees
                break

        if aos and los:
            return aos, los, peak_elevation, start_azimuth, end_azimuth
        else:
            self.logger.error("No pass found in the specified time window.")
            return None, None, None, None, None

            
    def getNextPasses(self, num_passes=10):
        """
        Calculates the next `num_passes` passages of the satellite over the observer.
        Args:
            num_passes (int): Number of satellite passes to calculate.
        Returns:
            List of dictionaries containing:
                - aos (datetime): Acquisition of Signal (rise time)
                - los (datetime): Loss of Signal (set time)
                - peak_elevation (float): Maximum elevation (degrees) during the pass
                - start_azimuth (float): Azimuth (degrees) at AOS
                - end_azimuth (float): Azimuth (degrees) at LOS
        """
        if self.satellite is None:
            raise ValueError(f"Satellite object not created for {self.satcat_id}")

        # List to hold the passes
        passes = []
        now = self.ts.now()
        
        # # now should be 4h and 10 min ahead of current time
        # now = self.ts.utc(now.utc_datetime() + timedelta(hours=3, minutes=32))
        # self.logger.debug(f"This is the current time: {now.utc_datetime()}")
        
        search_start = now

        # Keep finding passes until we have the desired number
        while len(passes) < num_passes:
            search_end = self.ts.utc(search_start.utc_datetime() + timedelta(days=1))

            try:
                times, events = self.satellite.find_events(self.observer, search_start, search_end, altitude_degrees=0.0)
            except ValueError as e:
                self.logger.error(f"Error finding events: {e}")
                break

            aos, los, peak_elevation = None, None, 0
            start_azimuth, end_azimuth = None, None

            for i, event in enumerate(events):
                time = times[i].utc_datetime()

                if event == 0:  # Rise (AOS)
                    aos = time
                    topocentric = (self.satellite - self.observer).at(times[i])
                    start_azimuth = float(topocentric.altaz()[1].degrees)
                elif event == 1:  # Culmination (Peak)
                    topocentric = (self.satellite - self.observer).at(times[i])
                    peak_elevation = float(max(peak_elevation, topocentric.altaz()[0].degrees))
                elif event == 2:  # Set (LOS)
                    los = time
                    topocentric = (self.satellite - self.observer).at(times[i])
                    end_azimuth = float(topocentric.altaz()[1].degrees)
                    
                    # filter passes lower than 10 degress
                    if peak_elevation < 10:
                        aos, los, peak_elevation = None, None, 0
                        start_azimuth, end_azimuth = None, None
                        continue
                    
                    # calculate and store the orbit parametric formulas
                    number_of_points = 20
                    self.logger.debug(f"los: {los} and aos: {aos}")
                    interval = (los - aos).total_seconds() / number_of_points
                    time_interval = [aos + timedelta(seconds=i * interval) for i in range(number_of_points)]
                    
                    azimuth_elevation = []

                    for t in time_interval:
                        topocentric = (self.satellite - self.observer).at(self.ts.utc(t))
                        alt, az, _ = topocentric.altaz()
                        azimuth_elevation.append([float(az.degrees), float(alt.degrees)])
                        # human_time = t.strftime("%Y-%m-%d %H:%M:%S")  # display the time in human time
                    
                    # convert time_interval to float
                    time_interval = [t.timestamp() for t in time_interval]
                    # Add the pass data if valid
                    if aos and los:
                        # convert aos to float
                        passes.append({
                            "aos": aos.timestamp(),
                            "los": los.timestamp(),
                            "max_elevation": peak_elevation,
                            "start_azimuth": start_azimuth,
                            "end_azimuth": end_azimuth,
                            "tle_line1": self.tle_line1,
                            "tle_line2": self.tle_line2,
                            "azimuth_elevation": azimuth_elevation,
                            "time_interval": time_interval
                        })
                        
                        for key in passes[-1]:
                            self.logger.debug(f"  {key}: {type(passes[-1][key])}")


                        # Reset variables for the next pass
                        aos, los, peak_elevation = None, None, 0
                        start_azimuth, end_azimuth = None, None

                    # Break early if we have enough passes
                    if len(passes) >= num_passes:
                        break

            # Move search start to just after the current search end
            search_start = search_end

        return passes



def simpleTest():
    # Example usage of the class before remote capabilites were added

    # Create an instance of SatellitePredictor
    predictor = SatellitePredictor()

    # Get the satellite position
    elevation, azimuth, distance = predictor.getSatellitePosition()
    
    # Get the next passage
    aos, los, peak_elevation, start_azimuth, end_azimuth = predictor.getNextPassage()

    # Print the next passage details
    if aos and los:
        print(f"Next Passage:")
        print(f"AOS (Rise Time, UTC): {aos}")
        print(f"LOS (Set Time, UTC): {los}")
        print(f"Peak Elevation: {peak_elevation:.2f}°")
        print(f"Start Azimuth: {start_azimuth:.2f}°")
        print(f"End Azimuth: {end_azimuth:.2f}°")
    else:
        print("No passage found.")

    next_passages = predictor.getNextPasses(num_passes=10)
    print(f"Next {len(next_passages)} Passages:")
    for i, sat_pass in enumerate(next_passages):
        print(f"Pass {i+1}:")
        print(f"  AOS (UTC): {sat_pass['aos']}")
        print(f"  LOS (UTC): {sat_pass['los']}")
        print(f"  Peak Elevation: {sat_pass['peak_elevation']:.2f}°")
        print()

    # Print results
    print(f"Observation Time (UTC): {datetime.utcnow()}")
    print(f"Elevation: {elevation:.2f}°")
    print(f"Azimuth: {azimuth:.2f}°")
    print(f"Distance: {distance:.2f} km")
    
    # print information about the next passage number


if __name__ == "__main__":

    
    sat_predictor = SatellitePredictor()
    
    # sat_predictor.getNextPasses()
    sat_predictor.server.serve_forever()