#
# Cassini
#
# Copyright (C) 2023 Vladimir Vukicevic
# License: MIT
#

import logging
import asyncio
import os
import hashlib

class SimpleHTTPServer:
    BufferSize = 1024768

    def __init__(self, host="0.0.0.0", port=0):
        self.host = host
        self.port = port
        self.server = None
        self.routes = {}

    def register_file_route(self, path, filename):
        size = os.path.getsize(filename)
        md5 = hashlib.md5()
        with open(filename, 'rb') as f:
            while True:
                data = f.read(1024)
                if not data:
                    break
                md5.update(data)
        route = { 'file': filename, 'size': size, 'md5': md5.hexdigest() }
        self.routes[path] = route
        return route

    def unregister_file_route(self, path):
        del self.routes[path]

    async def start(self):
        self.server = await asyncio.start_server(self.handle_client, self.host, self.port)
        self.port = self.server.sockets[0].getsockname()[1]
        logging.debug(f'HTTP Listening on {self.server.sockets[0].getsockname()}')

    async def serve_forever(self):
        await self.server.serve_forever()

    async def handle_client(self, reader, writer):
        try:
            await self.handle_client_inner(reader, writer)
        except Exception as e:
            logging.error(f"HTTP Exception handling client: {e}")

    async def handle_client_inner(self, reader, writer):
        logging.debug(f"HTTP connection from {writer.get_extra_info('peername')}")
        data = b''
        while True:
            data += await reader.read(1024)
            if b'\r\n\r\n' in data:
                break

        logging.debug(f"HTTP request: {data}")
        request_line = data.decode().splitlines()[0]
        method, path, _ = request_line.split()

        if path not in self.routes:
            logging.debug(f"HTTP path {path} not found in routes")
            logging.debug(self.routes)
            writer.write("HTTP/1.1 404 Not Found\r\n".encode())
            writer.close()
            return

        route = self.routes[path]
        logging.debug(f"HTTP method {method} path {path} route: {route}")

        header = f"HTTP/1.1 200 OK\r\n"
        #header += f"Content-Type: application/octet-stream\r\n"
        header += f"Content-Type: text/plain; charset=utf-8\r\n"
        header += f"Etag: {route['md5']}\r\n"
        header += f"Content-Length: {route['size']}\r\n"
        header += "\r\n"

        logging.debug(f"Writing header:\n{header}")
        writer.write(header.encode())

        if method == "GET":
            total = 0
            with open(route['file'], 'rb') as f:
                while True:
                    data = f.read(self.BufferSize)
                    if not data:
                        break
                    writer.write(data)
                    logging.debug(f"HTTP wrote {len(data)} bytes")
                    #await asyncio.sleep(1)
                    total += len(data)
            logging.debug(f"HTTP wrote total {total} bytes")

        await writer.drain()
        writer.close()
        await writer.wait_closed()
        logging.debug(f"HTTP connection closed")

