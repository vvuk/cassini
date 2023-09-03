#!env python3
# -*- coding: utf-8 -*-
import sys
import socket
import struct
import time
import json
import asyncio
import logging
import random
from simple_mqtt_server import SimpleMQTTServer
from simple_http_server import SimpleHTTPServer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s,%(msecs)d %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)

SATURN_BROADCAST_PORT = 3000

SATURN_STATUS_PRINTING = 4
SATURN_STATUS_COMPLETE = 16 # ??

SATURN_CMD_0 = 0 # null data
SATURN_CMD_1 = 1 # null data
SATURN_CMD_SET_MYSTERY_TIME_PERIOD = 512 # "TimePeriod": 5000
SATURN_CMD_START_PRINTING = 128 # "Filename": "X", "StartLayer": 0
SATURN_CMD_UPLOAD_FILE = 256 # "Check": 0, "CleanCache": 1, "Compress": 0, "FileSize": 3541068, "Filename": "_ResinXP2-ValidationMatrix_v2.goo", "MD5": "205abc8fab0762ad2b0ee1f6b63b1750", "URL": "http://${ipaddr}:58883/f60c0718c8144b0db48b7149d4d85390.goo" },
SATURN_CMD_DISCONNECT = 64 # Maybe disconnect?

PRINTERS = []

PRINTER_SEARCH_TIMEOUT = 1

def handle_exception(loop, context):
    msg = context.get("exception", context["message"])
    name = context.get("future").get_coro().__name__
    logging.error(f"Caught exception from {name}: {msg}")

class SaturnPrinter:
    def __init__(self, addr, desc):
        self.addr = addr
        self.desc = desc

    # Class method: UDP broadcast search for all printers
    def find_printers(timeout=1):
        printers = []
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        with sock:
            sock.settimeout(PRINTER_SEARCH_TIMEOUT)
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
                    print(f'Found printer at {addr}')
                    pdata = json.loads(data.decode('utf-8'))
                    printers.append(SaturnPrinter(addr, pdata))
        return printers
    
    # Tell this printer to connect to the given mqtt server
    def connect(self, mqtt, http):
        self.mqtt = mqtt
        self.http = http
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        with sock:
            sock.sendto(b'M66666 ' + str(mqtt.port).encode('utf-8'), self.addr)
    
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

async def create_mqtt_server():
    mqtt = SimpleMQTTServer('0.0.0.0', 0)
    await mqtt.start()
    logging.info(f"MQTT Server created, port {mqtt.port}")
    mqtt_server_task = asyncio.create_task(mqtt.serve_forever())
    return mqtt, mqtt.port, mqtt_server_task

async def create_http_server():
    http = SimpleHTTPServer('0.0.0.0', 0)
    await http.start()
    logging.info(f"HTTP Server created, port {http.port}")
    http_server_task = asyncio.create_task(http.serve_forever())
    return http, http.port, http_server_task

def print_printer_status(printers):
    for i, p in enumerate(printers):
        attrs = p.desc['Data']['Attributes']
        status = p.desc['Data']['Status']
        printInfo = status['PrintInfo']
        print(f"{i}: {attrs['Name']} ({attrs['MachineName']})")
        print(f"  Status: {printInfo['Status']} Layers: {printInfo['CurrentLayer']}/{printInfo['TotalLayer']}")

async def main():
    cmd = None
    printers = SaturnPrinter.find_printers()

    if len(printers) == 0:
        print("No printers found")
        return

    if len(sys.argv) > 1:
        cmd = sys.argv[1]

    if cmd == 'status':
        print_printer_status(printers)
        return

    # Spin up our private mqtt server
    mqtt, mqtt_port, mqtt_task = await create_mqtt_server()
    http, http_port, http_task = await create_http_server()

    printer = printers[0]
    printer.connect(mqtt, http)

    await asyncio.sleep(3)
    printer.send_command(SATURN_CMD_0)
    await asyncio.sleep(1)
    printer.send_command(SATURN_CMD_1)
    await asyncio.sleep(1)
    printer.send_command(SATURN_CMD_SET_MYSTERY_TIME_PERIOD, { 'TimePeriod': 5 })
    await asyncio.sleep(1000)

        #printer_task = asyncio.create_task(printer_setup(mqtt.port))
        #while True:
        #    if server_task is not None and server_task.done():
        #        print("Server task done")
        #        print(server_task.exception())
        #        server_task = None
        #    if printer_task is not None and printer_task.done():
        #        print("Printer task done")
        #        print(printer_task.exception())
        #        printer_task = None

asyncio.run(main())