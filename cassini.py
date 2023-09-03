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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s,%(msecs)d %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)

SATURN_BROADCAST_PORT = 3000

SATURN_STATUS_COMPLETE = 16 # ??

SATURN_CMD_0 = 0 # null data
SATURN_CMD_1 = 1 # null data
SATURN_CMD_SET_REPORT_TIME_PERIOD = 512
SATURN_CMD_START_PRINTING = 128 # "Filename": "X", "StartLayer": 0
SATURN_CMD_UPLOAD_FILE = 256 # "Check": 0, "CleanCache": 1, "Compress": 0, "FileSize": 3541068, "Filename": "_ResinXP2-ValidationMatrix_v2.goo", "MD5": "205abc8fab0762ad2b0ee1f6b63b1750", "URL": "http://${ipaddr}:58883/f60c0718c8144b0db48b7149d4d85390.goo" },
SATURN_CMD_DISCONNECT = 64 # Maybe disconnect?

PRINTERS = []

PRINTER_SEARCH_TIMEOUT = 1

def handle_exception(loop, context):
    msg = context.get("exception", context["message"])
    name = context.get("future").get_coro().__name__
    logging.error(f"Caught exception from {name}: {msg}")

def find_printers_on(iface):
    #netaddr = netifaces.ifaddresses(iface)
    #if not netaddr.has_key(netifaces.AF_INET):
    #    print('No IPv4 address found for interface {}'.format(iface))
    #    sys.exit(1)
    #broadcast = netaddr[netifaces.AF_INET][0]['broadcast']

    # create UDP socket and send broadcast
    printers = []
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    with sock:
        sock.settimeout(PRINTER_SEARCH_TIMEOUT)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.sendto(b'M99999', ('<broadcast>', SATURN_BROADCAST_PORT))

        now = time.time()
        while True:
            if time.time() - now > PRINTER_SEARCH_TIMEOUT:
                break
            try:
                data, addr = sock.recvfrom(1024)
            except socket.timeout:
                continue
            else:
                print(f'Found printer at {addr}')
                pdata = json.loads(data.decode('utf-8'))
                pdata['addr'] = addr
                printers.append(pdata)
    return printers

def connect_printer(printer, srvport):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    with sock:
        sock.sendto(b'M66666 ' + str(srvport).encode('utf-8'), printer['addr'])

async def create_server():
    mqtt = SimpleMQTTServer('0.0.0.0', 0)
    await mqtt.start()
    logging.info(f"Server created, port {mqtt.port}")
    return mqtt

async def serve_forever(mqtt):
    loop = asyncio.get_running_loop()
    loop.set_exception_handler(handle_exception)
    await mqtt.serve_forever()

async def find_printers():
    printers = find_printers_on('en0')
    if len(printers) == 0:
        print('No printers found')
        sys.exit(1)
    for i, p in enumerate(printers):
        attrs = p['Data']['Attributes']
        #print('{}: {} ({})'.format(i, attrs['Name'], attrs['MachineName']))
    return printers

async def printer_setup(mqtt_port):
    PRINTERS = await find_printers()
    printer = PRINTERS[0]
    connect_printer(printer, mqtt_port)
    return printer

def print_printer_status(printers):
    for i, p in enumerate(printers):
        attrs = p['Data']['Attributes']
        status = p['Data']['Status']
        printInfo = status['PrintInfo']
        print(f"{i}: {attrs['Name']} ({attrs['MachineName']})")
        print(f"  Status: {printInfo['Status']} Layers: {printInfo['CurrentLayer']}/{printInfo['TotalLayer']}")

def send_printer_command(mqtt, printer, cmdid, data=None):
    # generate 16-byte random identifier as a hex string
    hexstr = '%032x' % random.getrandbits(128)
    timestamp = int(time.time() * 1000)
    mainboard = printer['Data']['Attributes']['MainboardID']
    cmd_data = {
        "Data": {
            "Cmd": cmdid,
            "Data": json.dumps(data) if data is not None else "null",
            "From": 0,
            "MainboardID": mainboard,
            "RequestID": hexstr,
            "TimeStamp": timestamp
        },
        "Id": printer['Id']
    }
    print(json.dumps(cmd_data))
    mqtt.outgoing_messages.put_nowait({'topic': '/sdcp/request/' + mainboard, 'payload': json.dumps(cmd_data)})

async def main():
    cmd = None
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
    if cmd == 'status':
        printers = await find_printers()
        print_printer_status(printers)
    else:
        mqtt = await create_server()
        server_task = asyncio.create_task(serve_forever(mqtt))
        printer = await printer_setup(mqtt.port)
        await asyncio.sleep(3)
        send_printer_command(mqtt, printer, 0)
        await asyncio.sleep(1)
        send_printer_command(mqtt, printer, 1)
        await asyncio.sleep(1)
        send_printer_command(mqtt, printer, 512, { "TimePeriod": 5000 })

        #printer_task = asyncio.create_task(printer_setup(mqtt.port))
        await asyncio.sleep(1000)
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