#!env python3
# -*- coding: utf-8 -*-
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
from simple_mqtt_server import SimpleMQTTServer
from simple_http_server import SimpleHTTPServer
from saturn_printer import SaturnPrinter

logging.basicConfig(
    level=logging.DEBUG, # .INFO
    format="%(asctime)s,%(msecs)d %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)

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

    if len(printers) > 1:
        print("More than 1 printer found.")
        print("Usage --printer argument to specify the ID. [TODO]")
        return

    if len(sys.argv) > 1:
        cmd = sys.argv[1]

    if cmd == 'status':
        print_printer_status(printers)
        return

    # Spin up our private servers
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