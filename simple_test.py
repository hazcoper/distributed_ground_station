"""
fake kiss tnc client and send a message to master
"""

import xmlrpc.client
import datetime

proxy = xmlrpc.client.ServerProxy("http://localhost:1711")

# send a message to the master
kiss_frame = "hello world"
tnc_client_ip = "localhost"
tnc_client_port = 4533
timestamp = datetime.datetime.now().timestamp()
proxy.remoteReceiveKiss(kiss_frame, tnc_client_ip, tnc_client_port, timestamp)
