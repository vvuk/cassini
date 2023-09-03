#
# Cassini
#
# Copyright (C) 2023 Vladimir Vukicevic
# License: MIT
#

import sys
import socket
import struct
import time
import json
import asyncio
import logging
import random

SATURN_BROADCAST_PORT = 3000

SATURN_STATUS_EXPOSURE = 2 # TODO: double check tese
SATURN_STATUS_RETRACTING = 3
SATURN_STATUS_LOWERING = 4
SATURN_STATUS_COMPLETE = 16 # ??

STATUS_NAMES = {
    SATURN_STATUS_EXPOSURE: "Exposure",
    SATURN_STATUS_RETRACTING: "Retracting",
    SATURN_STATUS_LOWERING: "Lowering",
    SATURN_STATUS_COMPLETE: "Complete"
}

SATURN_CMD_0 = 0 # null data
SATURN_CMD_1 = 1 # null data
SATURN_CMD_SET_MYSTERY_TIME_PERIOD = 512 # "TimePeriod": 5000
SATURN_CMD_START_PRINTING = 128 # "Filename": "X", "StartLayer": 0
SATURN_CMD_UPLOAD_FILE = 256 # "Check": 0, "CleanCache": 1, "Compress": 0, "FileSize": 3541068, "Filename": "_ResinXP2-ValidationMatrix_v2.goo", "MD5": "205abc8fab0762ad2b0ee1f6b63b1750", "URL": "http://${ipaddr}:58883/f60c0718c8144b0db48b7149d4d85390.goo" },
SATURN_CMD_DISCONNECT = 64 # Maybe disconnect?

class SaturnPrinter:
    def __init__(self, addr, desc):
        self.addr = addr
        self.desc = desc

    # Class method: UDP broadcast search for all printers
    def find_printers(timeout=1):
        printers = []
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        with sock:
            sock.settimeout(timeout)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, timeout)
            sock.sendto(b'M99999', ('<broadcast>', SATURN_BROADCAST_PORT))

            now = time.time()
            while True:
                if time.time() - now > timeout:
                    break
                try:
                    data, addr = sock.recvfrom(1024)
                except socket.timeout:
                    continue
                else:
                    logging.debug(f'Found printer at {addr}')
                    pdata = json.loads(data.decode('utf-8'))
                    printers.append(SaturnPrinter(addr, pdata))
        return printers
    
    # Tell this printer to connect to the given mqtt server
    def connect(self, mqtt, http):
        self.mqtt = mqtt
        self.http = http

        mainboard = self.desc['Data']['Attributes']['MainboardID']
        mqtt.add_handler("/sdcp/saturn/" + mainboard, self.incoming_data)
        mqtt.add_handler("/sdcp/response/" + mainboard, self.incoming_data)

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        with sock:
            sock.sendto(b'M66666 ' + str(mqtt.port).encode('utf-8'), self.addr)

    def incoming_data(self, topic, payload):
        if topic.startswith("/sdcp/status/"):
            self.incoming_status(payload['Data']['Status'])
        elif topic.startswith("/sdcp/attributes/"):
            # don't think I care about attributes
            pass
        elif topic.startswith("/sdcp/response/"):
            self.incoming_response(payload['Data']['RequestID'], payload['Data']['Cmd'], payload['Data']['Data'])

    def incoming_status(self, status):
        logging.info(f"STATUS: {status}")

    def incoming_response(self, id, cmd, data):
        logging.info(f"RESPONSE: {id} -- {cmd}: {data}")

    def describe(self):
        attrs = self.desc['Data']['Attributes']
        return f"{attrs['Name']} ({attrs['MachineName']})"

    def send_command(self, cmdid, data=None):
        # generate 16-byte random identifier as a hex string
        hexstr = '%032x' % random.getrandbits(128)
        timestamp = int(time.time() * 1000)
        mainboard = self.desc['Data']['Attributes']['MainboardID']
        cmd_data = {
            "Data": {
                "Cmd": cmdid,
                "Data": data,
                "From": 0,
                "MainboardID": mainboard,
                "RequestID": hexstr,
                "TimeStamp": timestamp
            },
            "Id": self.desc['Id']
        }
        print("SENDING REQUEST: " + json.dumps(cmd_data))
        self.mqtt.outgoing_messages.put_nowait({'topic': '/sdcp/request/' + mainboard, 'payload': json.dumps(cmd_data)})
