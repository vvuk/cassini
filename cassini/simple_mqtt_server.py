#
# Cassini
#
# Copyright (C) 2023 Vladimir Vukicevic
# License: MIT
#

import logging
import asyncio
import struct

MQTT_CONNECT = 1
MQTT_CONNACK = 2
MQTT_PUBLISH = 3
MQTT_PUBACK = 4
MQTT_SUBSCRIBE = 8
MQTT_SUBACK = 9
MQTT_DISCONNECT = 14

class SimpleMQTTServer:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.server = None
        self.incoming_messages = asyncio.Queue()
        self.outgoing_messages = asyncio.Queue()
        self.connected_clients = {}
        self.next_pack_id_value = 1

    async def start(self):
        self.server = await asyncio.start_server(self.handle_client, self.host, self.port)
        self.port = self.server.sockets[0].getsockname()[1]
        logging.debug(f'MQTT Listening on {self.server.sockets[0].getsockname()}')

    async def serve_forever(self):
        loop = asyncio.get_event_loop()
        self.client_connection = loop.create_future()
        self.client_subscribed = loop.create_future()
        await self.server.serve_forever()

    def publish(self, topic, payload):
        self.outgoing_messages.put_nowait({'topic': topic, 'payload': payload})

    async def next_published_message(self):
        return await self.incoming_messages.get()

    async def handle_client(self, reader, writer):
        try:
            await self.handle_client_inner(reader, writer)
        except Exception as e:
            logging.error(f"MQTT Exception handling client: {e}")

    async def handle_client_inner(self, reader, writer):
        addr = writer.get_extra_info('peername')
        logging.debug(f'Socket connected from {addr}')
        data = b''

        subscribed_topics = dict()
        client_id = None

        read_future = asyncio.ensure_future(reader.read(1024))
        outgoing_messages_future = asyncio.ensure_future(self.outgoing_messages.get())

        while True:
            completed, pending = await asyncio.wait([read_future, outgoing_messages_future], return_when=asyncio.FIRST_COMPLETED)

            if outgoing_messages_future in completed:
                outmsg = outgoing_messages_future.result()
                topic = outmsg['topic']
                payload = outmsg['payload']

                if topic in subscribed_topics:
                    qos = subscribed_topics[topic]
                    await self.send_msg(writer, MQTT_PUBLISH, payload=self.encode_publish(topic, payload, self.next_pack_id()))
                else:
                    logging.debug(f'SEND: NOT SUBSCRIBED {topic}: {payload}')
                #msg = (MQTT_PUBLISH, 0, topic.encode('utf-8') + payload.encode('utf-8'))
                #await self.send_msg(writer, *msg)
                outgoing_messages_future = asyncio.ensure_future(self.outgoing_messages.get())

            if read_future in completed:
                d = read_future.result()
                data += d
                read_future = asyncio.ensure_future(reader.read(1024))
            else:
                continue

            # Process any messages
            while True:
                # must have at least 2 bytes
                if len(data) < 2:
                    break

                msg_type = data[0] >> 4
                msg_flags = data[0] & 0xf
                #print(f" msg_type: {msg_type} msg_flags: {msg_flags}")
                # TODO -- we could maybe not have enough bytes to decode the length, but assume
                # that won't happen
                msg_length, len_bytes_consumed = self.decode_length(data[1:])
                #logging.debug(f"mqtt in msg_type: {msg_type} flags: {msg_flags} msg_length {msg_length} bytes_consumed for msg_length {len_bytes_consumed}")

                # is there enough to process the message?
                head_len = len_bytes_consumed + 1
                if msg_length + head_len > len(data):
                    logging.debug("Not enough")
                    break

                # pull the message payload out, and move data to next packet
                message = data[head_len                 :head_len+msg_length]
                data =    data[head_len+msg_length:]

                if msg_type == MQTT_CONNECT:
                    if message[0:6] != b'\x00\x04MQTT':
                        logging.error(f"MQTT client {addr}: bad CONNECT")
                        writer.close()
                        return
                    
                    client_id_len = struct.unpack("!H", message[10:12])[0]
                    client_id = message[12:12+client_id_len].decode("utf-8")

                    logging.debug(f"MQTT client {client_id} at {addr} connected")
                    self.connected_clients[client_id] = addr
                    await self.send_msg(writer, MQTT_CONNACK, payload=b'\x00\x00')

                    self.client_connection.set_result(client_id)
                    self.client_connection = asyncio.get_event_loop().create_future()

                elif msg_type == MQTT_PUBLISH:
                    qos = (msg_flags >> 1) & 0x3
                    topic, packid, content = self.parse_publish(message)

                    #logging.debug(f"Got DATA on: {topic}")
                    self.incoming_messages.put_nowait({ 'topic': topic, 'payload': content})
                    if qos > 0:
                        await self.send_msg(writer, MQTT_PUBACK, packet_ident=packid)
                elif msg_type == MQTT_SUBSCRIBE:
                    qos = (msg_flags >> 1) & 0x3
                    packid = message[0] << 8 | message[1]
                    message = message[2:]
                    topic = self.parse_subscribe(message)
                    logging.debug(f"Client {addr} subscribed to topic '{topic}', QoS {qos}")
                    subscribed_topics[topic] = qos
                    await self.send_msg(writer, MQTT_SUBACK, packet_ident=packid, payload=bytes([qos]))

                    self.client_subscribed.set_result(topic)
                    self.client_subscribed = asyncio.get_event_loop().create_future()
                elif msg_type == MQTT_DISCONNECT:
                    logging.info(f"Client {addr} disconnected")
                    writer.close()
                    await writer.wait_closed()

                    if client_id is not None:
                        del self.connected_clients[client_id]
                    return

    async def send_msg(self, writer, msg_type, flags=0, packet_ident=0, payload=b''):
        head = bytes([msg_type << 4 | flags])
        payload_length = len(payload)
        if packet_ident > 0:
            payload_length += 2
        head += self.encode_length(payload_length)
        if packet_ident > 0:
            head += bytes([packet_ident >> 8, packet_ident & 0xff])
        data = head + payload
        #logging.debug(f"    writing {len(data)} bytes: {data}")
        writer.write(data)
        await writer.drain()

    def encode_length(self, length):
        encoded = bytearray()
        while True:
            digit = length % 128
            length //= 128
            if length > 0:
                digit |= 0x80
            encoded.append(digit)
            if length == 0:
                break
        return encoded

    def decode_length(self, data):
        multiplier = 1
        value = 0
        bytes_read = 0

        for byte in data:
            bytes_read += 1
            value += (byte & 0x7f) * multiplier
            if byte & 0x80 == 0:
                break
            multiplier *= 128
            if multiplier > 2097152:
                raise ValueError("Malformed Remaining Length")

        return value, bytes_read

    def parse_publish(self, data):
        topic_len = struct.unpack("!H", data[0:2])[0]
        topic = data[2:2 + topic_len].decode("utf-8")
        packid = struct.unpack("!H", data[2 + topic_len:4 + topic_len])[0]
        message_start = 4 + topic_len
        message = data[message_start:].decode("utf-8")
        return topic, packid, message

    def parse_subscribe(self, data):
        topic_len = struct.unpack("!H", data[0:2])[0]
        topic = data[2:2 + topic_len].decode("utf-8")
        return topic

    def encode_publish(self, topic, message, packid=0):
        topic_len = len(topic)
        topic = topic.encode("utf-8")
        packid = struct.pack("!H", packid)
        message = message.encode("utf-8")
        return struct.pack("!H", topic_len) + topic + packid + message
    
    def next_pack_id(self):
        pack_id = self.next_pack_id_value
        self.next_pack_id_value += 1
        return pack_id

