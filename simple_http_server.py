import asyncio
import os
import hashlib

class SimpleHTTPServer:
    def __init__(self, host="127.0.0.1", port=0):
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

    async def start(self):
        self.server = await asyncio.start_server(self.handle_client, self.host, self.port)
        self.port = self.server.sockets[0].getsockname()[1]

    async def serve_forever(self):
        await self.server.serve_forever()

    async def handle_client(self, reader, writer):
        data = b''
        while True:
            data += await reader.read(1024)
            if b'\r\n\r\n' in data:
                break

        request_line = data.decode().splitlines()[0]
        method, path, _ = request_line.split()

        if path not in self.routes:
            writer.write("HTTP/1.1 404 Not Found\r\n".encode())
            writer.close()
            return

        route = self.routes[path]
        header = f"HTTP/1.1 200 OK\r\n"
        header += f"Content-Type: application/octet-stream\r\n"
        header += f"Etag: {route['md5']}\r\n"
        header += f"Content-Length: {path['size']}\r\n"

        writer.write(header.encode())

        if method == "GET":
            writer.write(b'\r\n')
            with open(route['file'], 'rb') as f:
                while True:
                    data = f.read(8192)
                    if not data:
                        break
                    writer.write(data)

        await writer.drain()
        writer.close()
        await writer.wait_closed()

