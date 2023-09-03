# Cassini

[ELEGOO](https://www.elegoo.com/) has a number of printers, such as the
[Saturn 3 Ultra](https://www.elegoo.com/products/elegoo-saturn-3-ultra-resin-3d-printer-12k)
that support file transfer and printing over WiFi. As far as I could find, only Chitubox and
Voxeldance Tango support this, but there was no way to print from Lychee or [UVTools](https://github.com/sn4k3/UVtools).

*Cassini* is a command-line tool to allow getting the status of your printer(s),
transferring files to them, and starting a print. It has only been tested with a Saturn 3 Ultra,
but may work with other ChiTu-mainboard printers with WiFi.

Note: This is still a work in progress.

License: MIT
Copyright (C) 2023 Vladimir Vukicevic

## Usage

Python 3 is required. There are no other prerequisites.

### Printer status

```
$ ./cassini.py status
0: Saturn3Ultra (ELEGOO Saturn 3 Ultra) -- 192.168.x.x
  Status: 4 Layers: 27/1002
```

### File transfer

```
$ ./cassini.py [--target printer_id] put-file [--start-print] MyFile.goo
```

### Start a print (of an existing file)

```
$ ./cassini.py [--target printer_id] start-print Myfile.goo
```

## Protocol Description

The protocol is pretty simple. (There is no encryption or anything that I could find.)

There is a UDP discovery, status, and MQTT connection protocol. When the UDP command to
connect to a MQTT server is given, the printer connects to a MQTT server, and can be
controlled via MQTT messages. A HTTP server is also needed for file downloads.

Note: this seems nicely set up to be able to control multiple printers from one central
system. Cassini doesn't implement this, though it does allow you to choose which printer
to send commands to.

(SDCP might be a standard protocol on top of MQTT, but I didn't investigate too deeply.)

### UDP Status and Discovery

A UDP broadcast to port 3000 with `M99999` will cause all printers to send back a JSON status
blob via UDP to the sending port. This response looks like this. `LASTHOST` below refers
to the last MQTT/SDCP server this printer was connected to.

```
{
  "Id": "0a69ee780fbd40d7bfb95b312250bf46",
  "Data": {
    "Attributes": {
      "Name": "Saturn3Ultra",
      "MachineName": "ELEGOO Saturn 3 Ultra",
      "ProtocolVersion": "V1.0.0",
      "FirmwareVersion": "V1.4.2",
      "Resolution": "11520x5120",
      "MainboardIP": "192.168.7.128",
      "MainboardID": "ABCD1234ABCD1234",
      "SDCPStatus": 0,
      "LocalSDCPAddress": "tcp://LASTHOST:33288",
      "SDCPAddress": "",
      "Capabilities": [
        "FILE_TRANSFER",
        "PRINT_CONTROL"
      ]
    },
    "Status": {
      "CurrentStatus": 0,
      "PreviousStatus": 1,
      "PrintInfo": {
        "Status": 16,
        "CurrentLayer": 310,
        "TotalLayer": 310,
        "CurrentTicks": 3222039,
        "TotalTicks": 3218949,
        "ErrorNumber": 0,
        "Filename": "ResinXP2-ValidationMatrix.goo"
      },
      "FileTransferInfo": {
        "Status": 0,
        "DownloadOffset": 0,
        "CheckOffset": 0,
        "FileTotalSize": 0,
        "Filename": ""
      }
    }
  }
}
```

Sending a UDP message to port 3000 of a specific printer with the content `M66666 12345` causes the
printer to make a MQTT client connection to the server that sent the message on port 12345.

The `Id` from this message is repeated in every MQTT message below, published by either the client
or the server.

### MQTT/SDCP Control

When connected via MQTT, the printer subscribes to a request topic for the printer: `/sdcp/request/ABCD1234ABCD1234`.
The id is the `MainboardID` from the original discovery.  Each payload 

The printer publishes messages to three topics:

`/sdcp/status/ABCD1234ABCD1234`: Status messages, same format as the `"Status"` content of the broadcast message:  `{"Id":"f25273b12b094c5a8b9513a30ca60049","Data":{"Status":{"CurrentStatus":0,"PreviousStatus":0,"PrintInfo":{"Status":0,"CurrentLayer":0,"TotalLayer":0,"CurrentTicks":0,"TotalTicks":0,"ErrorNumber":0,"Filename":""},"FileTransferInfo":{"Status":0,"DownloadOffset":0,"CheckOffset":0,"FileTotalSize":0,"Filename":""}},"MainboardID":"ABCD1234ABCD1234","TimeStamp":8629636}}`

`/sdcp/attributes/ABCD1234ABCD1234`: Unclear what this is used for, as it seems to repeat the Status information: `{"Id":"f25273b12b094c5a8b9513a30ca60049","Data":{"Attributes":{"CurrentStatus":0,"PreviousStatus":0,"PrintInfo":{"Status":0,"CurrentLayer":0,"TotalLayer":0,"CurrentTicks":0,"TotalTicks":0,"ErrorNumber":0,"Filename":""},"FileTransferInfo":{"Status":0,"DownloadOffset":0,"CheckOffset":0,"FileTotalSize":0,"Filename":""}},"MainboardID":"ABCD1234ABCD1234","TimeStamp":8629737}}`

`/sdcp/response/ABCD1234ABCD1234`: Responses to `/sdcp/request/XXX` messages. The `Cmd` inside Data (if present) and `RequestID` values will match what was sent in the request.  Example: `{"Id":"f25273b12b094c5a8b9513a30ca60049","Data":{"Cmd":1,"Data":{"Ack":0},"RequestID":"130fdded918e4276a47e504f554bed54","MainboardID":"ABCD1234ABCD1234","TimeStamp":8567213}}`

The printer subscribes to a request topic specific to its mainboard ID `/sdcp/request/ABCD1234ABCD1234`, with payloads looking like:

```
{
    "Data": {
        "Cmd": 1,
        "Data": null,
        "From": 0,
        "MainboardID": "ABCD1234ABCD1234",
        "RequestID": "3676747651dd44b0bdbd630f38b61754",
        "TimeStamp": 1693671336726
    },
    "Id": "0a69ee780fbd40d7bfb95b312250bf46"
}
```

Commands discovered:

| ID  | Description | Data |
===========================
| 0   | Unknown. Sent by CHITUBOX first. | None |
| 1   | Unknown. Sent by CHITUBOX after 0. | None |
| 64  | Maybe a disconnect? | None |
| 128 | Start printing. | See below. |
| 256 | Upload file. | See below. |
| 512 | Set some kind of time period. | `{ "TimePeriod": 5000 }` |

#### 128: Start Printing

```
{
    "Data": {
        "Cmd": 128,
        "Data": {
            "Filename": "_ResinXP2-ValidationMatrix_v2.goo",
            "StartLayer": 0
        },
        "From": 0,
        "MainboardID": "ABCD1234ABCD1234",
        "RequestID": "b353f511680d40278c48602821a9e6ec",
        "TimeStamp": 1693671341990
    },
    "Id": "0a69ee780fbd40d7bfb95b312250bf46"
}
```

#### 256: Upload file

Note: in the URL, `${ipaddr}` seems to be replaced by the IP address that the printer
is connected to. The file needs to be accessible at the specified URL.

```
{
    "Data": {
        "Cmd": 256,
        "Data": {
            "Check": 0,
            "CleanCache": 1,
            "Compress": 0,
            "FileSize": 3541068,
            "Filename": "_ResinXP2-ValidationMatrix_v2.goo",
            "MD5": "205abc8fab0762ad2b0ee1f6b63b1750",
            "URL": "http://${ipaddr}:58883/f60c0718c8144b0db48b7149d4d85390.goo"
        },
        "From": 0,
        "MainboardID": "ABCD1234ABCD1234",
        "RequestID": "5b72361a76774a96b73f091bf5f79590",
        "TimeStamp": 1693671336846
    },
    "Id": "0a69ee780fbd40d7bfb95b312250bf46"
}```
