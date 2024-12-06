import logging
import os

class ConfigParser:
    def __init__(self, config_file_path="config.ini"):
        """
        Receives the path to the configuration file
        default path is a file called config.ini in the current dir
        """

        # set up logger
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.setLevel(logging.DEBUG)

        # Create file handler
        file_path = os.path.join("logs", f"{self.__class__.__name__}.log")
        file_handler = logging.FileHandler(file_path)
        file_handler.setLevel(logging.DEBUG)

        # Define a common formatter
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

        # Attach the formatter to handlers
        file_handler.setFormatter(formatter)

        # Add handlers to the logger
        self.logger.addHandler(file_handler)

        self.config_file_path = config_file_path
        self.config_dict = {}

    def set_logging_level(self, level):
        """
        Sets the logging level. Level can be logging.DEBUG, logging.INFO, etc.
        """
        logging.basicConfig(
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        self.logger.setLevel(level)
        self.logger.info(f"Logging level set to {logging.getLevelName(level)}")
        
    
    def loadDefaultValues(self):
        """
        Hardcoded default values that will be used in case a certain key is not found in the configuration file.
        just add a variable with a certain value and it will automatically add that variable to the dictionary
        """
        gqrx_ip = "localhost"
        gqrx_port = 7356
        gqrx_rpc_host = "localhost"
        gqrx_rpc_port = 1712
        
        rotctl_ip = "localhost"
        rotctl_port = 4533
        rotctl_rpc_host = "localhost"
        rotctl_rpc_port = 1713
        
        manager_rpc_host = "localhost"
        manager_rpc_port = 1710
        
        modules = ["gqrx_control", "rotctl_control", "manager", "new_ui"]
        
    
        # load all the variables defined in this functions to the dict
        variable_dict = locals()
        for variable in variable_dict:
            
            if variable.startswith("__") or variable == "self":
                continue

            self.config_dict[variable] = variable_dict[variable]
            self.logger.debug(f"Loaded default key: {variable}, value: {variable_dict[variable]}")

    def parseValue(self, value):
        """
        The idea is to try and extract the type of the value and save it accordingly
        """
        
        # check if it is a boolean
        if value.lower() == "true" or value.lower() == "false":
            self.logger.debug(f"   Value is a boolean: {value}")
            return value.lower() == "true"

        # check if it is a number
        try:
            value = int(value)
            self.logger.debug(f"   Value is a number: {value}")
            return value
        except ValueError:
            pass
        
        # check if it is a float
        try:
            value = float(value)
            self.logger.debug(f"   Value is a float: {value}")
            return value
        except ValueError:
            pass
        
        # check if its a list
        try:
            if value.startswith("[") and value.endswith("]"):
                value = value[1:-1]  # remove the brackets
                value = value.split(",")  # split the values
                
                # check to see if any of teh values has extra spaces
                for i in range(len(value)):
                    value[i] = value[i].strip()
                    
                
                self.logger.debug(f"   Value is a list: {value}")
                self.logger.debug(f"     result: {value}")
                return value
        except Exception as e:
            self.logger.error(f"Error parsing value: {e}")
              
        # if it is none of the above, return the string
        self.logger.debug(f"   Value is a string: {value}")
        return value
      

    def loadConfig(self):
        """
        Opens and parses the configuration file.
        """
        # load the default value for the variables
        self.loadDefaultValues()
        
        try:
            with open(self.config_file_path, 'r') as file:
                self.logger.info(f"Opening configuration file: {self.config_file_path}")
                
                for line_number, line in enumerate(file, start=1):
                    self.logger.debug("Reading line: " + line.strip())
                    # Ignore comments and empty lines
                    if line.startswith("#") or line.strip() == "":
                        self.logger.debug(f"  Ignoring line {line_number}")
                        continue
                    
                    # Splitting the line into key-value pairs
                    if ":" not in line:
                        self.logger.warning(f"  Invalid format on line {line_number}")
                        continue
                    
                    # if there is a # in the line, ignore everything after it
                    if "#" in line:
                        line = line.split("#")[0]
                    
                    key, value = line.split(":", 1)  # Split only at the first colon
                    key = key.strip()
                    value = self.parseValue(value.strip())  # try to check the value type
                                        
                    self.config_dict[key] = value
                    self.logger.info(f"Loaded key: {key}, value: {value}")
                    
        except FileNotFoundError:
            self.logger.error(f"Configuration file '{self.config_file_path}' not found.")
        except Exception as e:
            self.logger.exception(f"An error occurred while loading the configuration file: {e}")
    
    def get(self, parameter):
        """
        Returns the value of the key if it exists, otherwise returns None
        """
        self.logger.debug(f"Getting parameter: {parameter}")
        value = self.config_dict.get(parameter)
        self.logger.debug("  Value: " + str(value))
        
        if value is None:
            self.logger.warning(f"Parameter '{parameter}' not found in configuration file.")
        
        return value        
    
if __name__ == "__main__":
    my_conf = ConfigParser()
    my_conf.set_logging_level(logging.DEBUG)  # Change logging level here if needed
    my_conf.loadConfig()
    print("Config dict:", my_conf.config_dict)
