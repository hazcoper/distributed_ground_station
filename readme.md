# Distributed_Ground_Station
With the launch of ISTSAT-1 we quickly noticed that the tranmission power was far below what was expected. To a point that you could barely hear the signal, let alone decode. We quickly started planning on how we could improve the communication chain with the satellite.

The first thing we did was to mount and phased array with two huge Yagi antennas to increase the gain of the system. It made a world of difference, but unfortunately as we are located in an urban enviroment we have a lot of noise, and that increase as well. The SNR did improve, under ideal conditions we have been able to decode the messages from the satellite without any errors. But we still had a lot of work to do as it was only on the most ideal conditions, and it was not realiable enough to opperate the satellite as intended. 

After experiment with a variety of setupts we came to the conclusion that de decoding software was far from ideal. Most available tools were not designed to work with such low SNR. So we focused our efforts on creating those tools. Our main objective was to have something that could decode messages even if they had some errors, and pontentially show what were the problematic bits so that they could be fixed.

Unfortunately we realized that the number of errors was too high, which made the whole error correction idea unfeasible. So we decided to construct extra ground stations in different locations. The idea is that the erros in the signal would be different in each location because the noise would be different at each location. So we wanted to use the information from all the ground stations to correct the errors in the signal.

This is the first approach to achieve such a system. For this first iteration we decided to work with the already decoded messages (but did not pass crc) from a software TNC (we are using soundmodem). Using the knowledge of the structure of the message, some heuristics, the pieces of the message from the different ground stations and some luck, we hope to be able to quickly decode the messages from the satellite.

Eventually if this proves to not be enough, we will use this system but go one step before up in the chain. We will run with our own AFSK decoding software to provide extra information for the decoding process. 

As of right now the system does not yet support merging the messages, this will be the next step

Another big part of decoding weak signals is to have tracebility of the received data. This tool was also made with that in mind. It will log all the received messages adding information about the position of the satellite at the time of reception. It will also group the messages by passages. We can later use this data to better understand the conditions required to achieve a successful decoding.

## How it works
The system is composed of multiple modules. They will be explained bellow:

- TncClient:
    - Connects to soundmodem or other TNC software over ip and receives the decoded messages
    - it will take note of the received time and it will forward that message to the Master
    
- SatellitePredictor:
    - Responsible for keeping the TLE updated
    - It will generate a list of the next passes for the satellite. Passage_Scheduler will use this information to schedule the passages (used for grouping the passages together)
    - It will also provide Master with the current altitude and azimuth of the satellite

- Passage_Scheduler:
    - Every hour it will get the list of the next 10 passes of the satellite. If any of those passes happen in the next hour, it will prepare everything to receive the message
        - Tell the master the information about the new pass
    - Every day it will update the TLE

- Master:
    - The brain of the operation, what joins all the individual modules together
    - It will receive information about a new passage (in that information is the current TLE)
        - Forward that information to be saved by the DataWarehouse
    - It will receive information about a new message
        - Ask SatellitePredictor for the current position of the satellite
        - Forward that information to be saved by the DataWarehouse
    
- DataWarehouse:
    - Responsible for keeping track and savind all of the data
    - As soon as a new passage enters AOS, it will save the previous passage to disk as a json
        - it will include all of the messages that it received out of passage as well
    
All of the different modules are implemented as class. And they all communicate with one another using xmlrpc. There is a configuration file where all the ips and ports for the different modules are stored. It will also store in the future information about other configurations

