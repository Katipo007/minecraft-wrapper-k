# -*- coding: utf-8 -*-

# region Modules
# ------------------------------------------------

# standard
import socket
import threading
import time
import json
import traceback

# third party
# (none)

# local
from proxy.packet import Packet
from proxy import mcpackets
from api.entity import Entity

# Py3-2
import sys
PY3 = sys.version_info > (3,)

if PY3:
    # noinspection PyShadowingBuiltins
    xrange = range

# endregion

# region Constants
# ------------------------------------------------

HANDSHAKE = 0  # actually unused here because, as a fake "client", we are not listening for connections
# So we don't have to listen for a handshake.  We simply send a handshake to the server
# followed by a login start packet and go straight to LOGIN mode.  HANDSHAKE in this
# context might mean a server that is not started?? (proposed idea).

# MOTD = 1  # not used. clientconnection.py handles PING/MOTD functions

LOGIN = 2  # login state
PLAY = 3  # play state

_STRING = 0
_JSON = 1
_UBYTE = 2
_BYTE = 3
_INT = 4
_SHORT = 5
_USHORT = 6
_LONG = 7
_DOUBLE = 8
_FLOAT = 9
_BOOL = 10
_VARINT = 11
_BYTEARRAY = 12
_BYTEARRAY_SHORT = 13
_POSITION = 14
_SLOT = 15
_UUID = 16
_METADATA = 17
_SLOT_NO_NBT = 18
_REST = 90
_RAW = 90
_NULL = 100
# endregion


# noinspection PyBroadException,PyUnusedLocal
class ServerConnection:
    def __init__(self, client, wrapper, ip=None, port=None):
        """
        Server receives "CLIENT BOUND" packets from server.  These are what get parsed (CLIENT BOUND format).
        'client.packet.sendpkt' - sends a packet to the client (use CLIENT BOUND packet format)
        'self.packet.sendpkt' - sends a packet back to the server (use SERVER BOUND packet format)
        This part of proxy 'pretends' to be the client interacting with the server.


        Args:
            client: The client to connect to the server
            wrapper:
            ip:
            port:

        Returns:

        """
        self.client = client
        self.wrapper = wrapper
        self.proxy = wrapper.proxy
        self.log = wrapper.log
        self.ip = ip
        self.port = port

        self.abort = False
        self.isServer = True
        self.server_socket = socket.socket()

        self.state = HANDSHAKE
        self.packet = None
        # self.lastPacketIDs = []

        self.version = self.wrapper.javaserver.protocolVersion
        self._refresh_server_version()
        self.username = self.client.username

        # we are going to centralize this to client.servereid
        # self.eid = None  # WHAT IS THIS - code seemed to use it in entity and player id code sections !?
        # self.playereid = None

        self.headlooks = 0
        self.currentwindowid = -1
        self.noninventoryslotcount = 0

    def _refresh_server_version(self):
        # Get serverversion for mcpackets use
        try:
            self.version = self.wrapper.javaserver.protocolVersion
        except AttributeError:
            # -1 to signal no server is running
            self.version = -1
        self.pktSB = mcpackets.ServerBound(self.version)
        self.pktCB = mcpackets.ClientBound(self.version)
        if self.version > mcpackets.PROTOCOL_1_7:
            # used by ban code to enable wrapper group help display for ban items.
            self.wrapper.api.registerPermission("mc1.7.6", value=True)

    def send(self, packetid, xpr, payload):
        """ not supported. For old code compatability purposes only."""
        self.log.debug("deprecated server.send() called.  Use server.packet.sendpkt for best performance.")
        self.packet.send(packetid, xpr, payload)
        pass

    def connect(self):
        if self.ip is None:
            self.server_socket.connect(("localhost", self.wrapper.config["Proxy"]["server-port"]))
        else:
            self.server_socket.connect((self.ip, self.port))
            self.client.isLocal = False

        self.packet = Packet(self.server_socket, self)
        self.packet.version = self.client.clientversion

        t = threading.Thread(target=self.flush_loop, args=())
        t.daemon = True
        t.start()

    def close(self, reason="Disconnected", kill_client=True):
        self.abort = True
        self.packet = None
        self.log.debug("Disconnected proxy server connection. (%s)", self.username)
        try:
            self.server_socket.close()
        except OSError:
            pass

        if not self.client.isLocal and kill_client:  # Ben's cross-server hack
            self.client.isLocal = True
            message = {
                "text": "Disconnected from server.",
                "color": "red"
            }
            self.client.packet.sendpkt(self.pktCB.CHANGE_GAME_STATE, [_UBYTE, _FLOAT], (1, 0))  # "end raining"
            self.client.packet.sendpkt(self.pktCB.CHAT_MESSAGE, [_STRING, _BYTE], (json.dumps(message), 0))
            self.client.connect()
            return

        # I may remove this later so the client can remain connected upon server disconnection
        #  - - -- - if re-activating code ;;;; update arguments!!   --- -- --
        # self.client.packet.send(0x02, "string|byte",
        #                         (json.dumps({"text": "Disconnected from server. Reason: %s" % reason,
        #                                       "color": "red"}),0))
        # self.abort = True
        # self.client.connect()
        if kill_client:
            self.client.abort = True
            self.client.server = None
            self.proxy.removestaleclients()

    def getPlayerByEID(self, eid):
        for client in self.wrapper.proxy.clients:
            if client.servereid == eid:
                return self.getPlayerContext(client.username, calledby="getPlayerByEID")
        self.log.debug("Failed to get any player by client Eid: %s", eid)
        return False

    def getPlayerContext(self, username, calledby=None):
        try:
            return self.wrapper.javaserver.players[username]
        except Exception as e:  # This could be masking an issue and would result in "False" player objects
            self.log.error("getPlayerContext (called by: %s) failed to get player %s: \n%s", calledby, username, e)
            return False

    def flush_loop(self):
        while not self.abort:
            try:
                self.packet.flush()
            except socket.error:
                self.log.debug("Server socket closed (socket_error).")
                break
            time.sleep(0.01)
        self.log.debug("server connection flush_loop thread ended")

    def parse(self, pkid):  # client - bound parse ("Server" class connection)
        if self.state == PLAY:
            # handle keep alive packets from server... nothing special here; we will just keep the server connected.
            if pkid == self.pktCB.KEEP_ALIVE:
                if self.version < mcpackets.PROTOCOL_1_8START:
                    # readpkt returns this as [123..] (a list with a single integer)
                    data = self.packet.readpkt([_INT])
                    self.packet.sendpkt(self.pktSB.KEEP_ALIVE, [_INT], data)  # which is why no need to [data] as a list
                else:  # self.version >= mcpackets.PROTOCOL_1_8START: - future elif in case protocol changes again.
                    data = self.packet.readpkt([_VARINT])
                    self.packet.sendpkt(self.pktSB.KEEP_ALIVE, [_VARINT], data)
                # self.log.trace("(PROXY SERVER) -> Parsed KEEP_ALIVE packet with server state 3 (PLAY)")
                return False

            elif pkid == self.pktCB.CHAT_MESSAGE:
                if self.version < mcpackets.PROTOCOL_1_8START:
                    parsing = [_STRING, _NULL]
                else:
                    parsing = [_STRING, _BYTE]

                rawstring, position = self.packet.readpkt(parsing)
                try:
                    data = json.loads(rawstring.decode('utf-8'))  # py3
                    # self.log.trace("(PROXY SERVER) -> Parsed CHAT_MESSAGE pckt with server state 3 (PLAY):\n%s", data)
                except Exception as e:
                    return

                payload = self.wrapper.events.callevent("player.chatbox", {"player": self.client.getPlayerObject(),
                                                                           "json": data})

                if payload is False:  # reject the packet .. no chat gets sent to the client
                    return False
                #
                # - this packet is headed to a client.  The plugin's modification could be just a simple "Hello There"
                #   or the more complex minecraft json dictionary - or just a dictionary written as text:
                # """{"text":"hello there"}"""
                #   the minecraft protocol is just json-formatted string, but python users find dealing with a
                # dictionary easier
                #   when creating complex items like the minecraft chat object.

                elif type(payload) == dict:  # if payload returns a "chat" protocol dictionary http://wiki.vg/Chat
                    chatmsg = json.dumps(payload)
                    # send fake packet with modded payload
                    self.client.packet.sendpkt(self.pktCB.CHAT_MESSAGE, parsing, (chatmsg, position))
                    return False  # reject the orginal packet (it will not reach the client)
                elif type(payload) == str:  # if payload (plugin dev) returns a string-only object...
                    self.log.warning("player.Chatbox return payload sent as string")
                    self.client.packet.sendpkt(self.pktCB.CHAT_MESSAGE, parsing, (payload, position))
                    return False
                else:  # no payload, nor was the packet rejected.. packet passes to the client (and his chat)
                    return True  # just gathering info with these parses.

            elif pkid == self.pktCB.JOIN_GAME:
                if self.version < mcpackets.PROTOCOL_1_9_1PRE:
                    data = self.packet.readpkt([_INT, _UBYTE, _BYTE, _UBYTE, _UBYTE, _STRING])
                    #    "int:eid|ubyte:gm|byte:dim|ubyte:diff|ubyte:max_players|string:level_type")
                else:
                    data = self.packet.readpkt([_INT, _UBYTE, _INT, _UBYTE, _UBYTE, _STRING])
                    #    "int:eid|ubyte:gm|int:dim|ubyte:diff|ubyte:max_players|string:level_type")
                # self.log.trace("(PROXY SERVER) -> Parsed JOIN_GAME packet with server state 3 (PLAY):\n%s", data)
                self.client.gamemode = data[1]
                self.client.dimension = data[2]
                self.client.servereid = data[0]
                # self.client.eid = data[0]  # This is the EID of the player on this particular server -
                # not always the EID that the client is aware of.  $$ ST00 note: Why would the eid be different!!??

                # this is an attempt to clear the gm3 noclip issue on relogging.
                # self.client.packet.sendpkt(self.pktCB.CHANGE_GAME_STATE, [_UBYTE, _FLOAT], (3, self.client.gamemode))

            elif pkid == self.pktCB.TIME_UPDATE:
                data = self.packet.readpkt([_LONG, _LONG])
                # "long:worldage|long:timeofday")
                self.wrapper.javaserver.timeofday = data[1]
                # self.log.trace("(PROXY SERVER) -> Parsed TIME_UPDATE packet:\n%s", data)

            elif pkid == self.pktCB.SPAWN_POSITION:
                data = self.packet.readpkt([_POSITION])
                #  javaserver.spawnPoint doesn't exist.. this is player spawnpoint anyway... ?
                # self.wrapper.javaserver.spawnPoint = data[0]
                self.client.position = data[0]
                self.wrapper.events.callevent("player.spawned", {"player": self.client.getPlayerObject()})
                # self.log.trace("(PROXY SERVER) -> Parsed SPAWN_POSITION packet:\n%s", data[0])

            elif pkid == self.pktCB.RESPAWN:
                data = self.packet.readpkt([_INT, _UBYTE, _UBYTE, _STRING])
                # "int:dimension|ubyte:difficulty|ubyte:gamemode|level_type:string")
                self.client.gamemode = data[2]
                self.client.dimension = data[0]
                # self.log.trace("(PROXY SERVER) -> Parsed RESPAWN packet:\n%s", data)

            elif pkid == self.pktCB.PLAYER_POSLOOK:
                # CAVEAT - The client and server bound packet formats are different!
                if self.version < mcpackets.PROTOCOL_1_8START:
                    data = self.packet.readpkt([_DOUBLE, _DOUBLE, _DOUBLE, _FLOAT, _FLOAT, _BOOL])
                elif mcpackets.PROTOCOL_1_7_9 < self.version < mcpackets.PROTOCOL_1_9START:
                    data = self.packet.readpkt([_DOUBLE, _DOUBLE, _DOUBLE, _FLOAT, _FLOAT, _BYTE])
                elif self.version > mcpackets.PROTOCOL_1_8END:
                    data = self.packet.readpkt([_DOUBLE, _DOUBLE, _DOUBLE, _FLOAT, _FLOAT, _BYTE, _VARINT])
                else:
                    data = self.packet.readpkt([_DOUBLE, _DOUBLE, _DOUBLE, _REST])
                self.client.position = (data[0], data[1], data[2])  # not a bad idea to fill player position
                # self.log.trace("(PROXY SERVER) -> Parsed PLAYER_POSLOOK packet:\n%s", data)

            elif pkid == self.pktCB.USE_BED:
                data = self.packet.readpkt([_VARINT, _POSITION])
                # "varint:eid|position:location")
                # self.log.trace("(PROXY SERVER) -> Parsed USE_BED packet:\n%s", data)
                if data[0] == self.client.servereid:
                    self.client.bedposition = data[0]  # get the players beddy-bye location!
                    self.wrapper.events.callevent("player.usebed", {"player": self.getPlayerByEID(data[0])})
                    # There is no reason to be fabricating a new packet from a non-existent client.eid
                    # self.client.packet.sendpkt(self.pktCB.USE_BED, [_VARINT, _POSITION],
                    #                            (self.client.eid, data[1]))

            elif pkid == self.pktCB.SPAWN_PLAYER:
                # This packet  is used to spawn other players into a player client's world.
                # is this packet does not arrive, the other player(s) will not be visible to the client
                if self.version < mcpackets.PROTOCOL_1_8START:
                    dt = self.packet.readpkt([_VARINT, _STRING, _REST])
                else:
                    dt = self.packet.readpkt([_VARINT, _UUID, _REST])
                # 1.7.6 "varint:eid|string:uuid|rest:metadt")
                # 1.8 "varint:eid|uuid:uuid|int:x|int:y|int:z|byte:yaw|byte:pitch|short:item|rest:metadt")
                # 1.9 "varint:eid|uuid:uuid|int:x|int:y|int:z|byte:yaw|byte:pitch|rest:metadt")

                # We dont need to read the whole thing.
                clientserverid = self.proxy.getclientbyofflineserveruuid(dt[1])
                if clientserverid.uuid:
                    if self.version < mcpackets.PROTOCOL_1_8START:
                        self.client.packet.sendpkt(
                            self.pktCB.SPAWN_PLAYER, [_VARINT, _STRING, _RAW], (dt[0], str(clientserverid.uuid), dt[2]))
                    else:
                        self.client.packet.sendpkt(
                            self.pktCB.SPAWN_PLAYER, [_VARINT, _UUID, _RAW], (dt[0], clientserverid.uuid, dt[2]))
                    return False
                # self.log.trace("(PROXY SERVER) -> Converted SPAWN_PLAYER packet:\n%s", dt)

            elif pkid == self.pktCB.SPAWN_OBJECT:
                # We really do not want to start parsing this unless we have a way to eliminate entities
                # that get destroyed
                if not self.wrapper.javaserver.world:  # that is what this prevents...
                    # self.log.trace("(PROXY SERVER) -> did not parse SPAWN_OBJECT packet.")
                    return True  # return now.. why parse something we are no going to use?
                if self.version < mcpackets.PROTOCOL_1_9START:
                    dt = self.packet.readpkt([_VARINT, _NULL, _BYTE, _INT, _INT, _INT, _BYTE, _BYTE])
                    dt[3], dt[4], dt[5] = dt[3] / 32, dt[4] / 32, dt[5] / 32
                    # "varint:eid|byte:type_|int:x|int:y|int:z|byte:pitch|byte:yaw")
                else:
                    dt = self.packet.readpkt([_VARINT, _UUID, _BYTE, _DOUBLE, _DOUBLE, _DOUBLE, _BYTE, _BYTE])
                    # "varint:eid|uuid:objectUUID|byte:type_|int:x|int:y|int:z|byte:pitch|byte:yaw|int:info|
                    # short:velocityX|short:velocityY|short:velocityZ")
                entityuuid = dt[1]
                objectname = self.wrapper.javaserver.world.objecttypes[dt[2]]
                newobject = {dt[0]: Entity(dt[0], entityuuid, dt[2], objectname,
                                           (dt[3], dt[4], dt[5],), (dt[6], dt[7]), True, self.username)}

                self.wrapper.javaserver.world.entities.update(newobject)
                # self.log.trace("(PROXY SERVER) -> Parsed SPAWN_OBJECT packet:\n%s", dt)

            elif pkid == self.pktCB.SPAWN_MOB:
                # we are not going to do all the parsing work unless we are storing the entity data
                # Storing this entity data has other issues; like removing stale items or "dead" items.
                if not self.wrapper.javaserver.world:
                    # self.log.trace("(PROXY SERVER) -> did not parse SPAWN_MOB packet.")
                    return True
                if self.version < mcpackets.PROTOCOL_1_9START:
                    dt = self.packet.readpkt([_VARINT, _NULL, _UBYTE, _INT, _INT, _INT, _BYTE, _BYTE, _BYTE, _REST])
                    dt[3], dt[4], dt[5] = dt[3] / 32, dt[4] / 32, dt[5] / 32
                    # "varint:eid|ubyte:type_|int:x|int:y|int:z|byte:pitch|byte:yaw|"
                    # "byte:head_pitch|...
                    # STOP PARSING HERE: short:velocityX|short:velocityY|short:velocityZ|rest:metadata")
                else:
                    dt = self.packet.readpkt(
                        [_VARINT, _UUID, _UBYTE, _DOUBLE, _DOUBLE, _DOUBLE, _BYTE, _BYTE, _BYTE, _REST])
                    # ("varint:eid|uuid:entityUUID|ubyte:type_|int:x|int:y|int:z|"
                    # "byte:pitch|byte:yaw|byte:head_pitch|
                    # STOP PARSING HERE: short:velocityX|short:velocityY|short:velocityZ|rest:metadata")
                entityuuid = dt[1]

                # eid, type_, x, y, z, pitch, yaw, head_pitch = \
                #     dt["eid"], dt["type_"], dt["x"], dt["y"], dt["z"], dt["pitch"], dt["yaw"], \
                #     dt["head_pitch"]
                # self.log.trace("(PROXY SERVER) -> Parsed SPAWN_MOB packet:\n%s", dt)

                mobname = self.wrapper.javaserver.world.entitytypes[dt[2]]["name"]
                newmob = {dt[0]: Entity(dt[0], entityuuid, dt[2], mobname,
                                        (dt[3], dt[4], dt[5],), (dt[6], dt[7], dt[8]), False, self.username)}

                self.wrapper.javaserver.world.entities.update(newmob)
                # self.wrapper.javaserver.world.entities[dt[0]] = Entity(dt[0], entityuuid, dt[2],
                #                                                        (dt[3], dt[4], dt[5], ),
                #                                                        (dt[6], dt[7], dt[8]),
                #                                                        False)

            elif pkid == self.pktCB.ENTITY_RELATIVE_MOVE:
                if not self.wrapper.javaserver.world:  # hereout, no further explanation.. See prior packet.
                    # self.log.trace("(PROXY SERVER) -> did not parse ENTITY_RELATIVE_MOVE packet.")
                    return True
                if self.version < mcpackets.PROTOCOL_1_8START:  # 1.7.10 - 1.7.2
                    data = self.packet.readpkt([_INT, _BYTE, _BYTE, _BYTE])
                else:  # FutureVersion > elif self.version > mcpacket.PROTOCOL_1_7_9:  1.8 ++
                    data = self.packet.readpkt([_VARINT, _BYTE, _BYTE, _BYTE])
                # ("varint:eid|byte:dx|byte:dy|byte:dz")
                # self.log.trace("(PROXY SERVER) -> Parsed ENTITY_RELATIVE_MOVE packet:\n%s", data)

                entityupdate = self.wrapper.javaserver.world.getEntityByEID(data[0])
                if entityupdate:
                    entityupdate.moveRelative((data[1], data[2], data[3]))

            elif pkid == self.pktCB.ENTITY_TELEPORT:
                if not self.wrapper.javaserver.world:
                    # self.log.trace("(PROXY SERVER) -> did not parse ENTITY_TELEPORT packet.")
                    return True
                if self.version < mcpackets.PROTOCOL_1_8START:  # 1.7.10 and prior
                    data = self.packet.readpkt([_INT, _INT, _INT, _INT, _REST])
                elif mcpackets.PROTOCOL_1_8START <= self.version < mcpackets.PROTOCOL_1_9START:
                    data = self.packet.readpkt([_VARINT, _INT, _INT, _INT, _REST])
                else:
                    data = self.packet.readpkt([_VARINT, _DOUBLE, _DOUBLE, _DOUBLE, _REST])
                    data[1], data[2], data[3] = data[1] * 32, data[2] * 32, data[3] * 32
                # ("varint:eid|int:x|int:y|int:z|byte:yaw|byte:pitch")

                # self.log.trace("(PROXY SERVER) -> Parsed ENTITY_TELEPORT packet:\n%s", data)
                entityupdate = self.wrapper.javaserver.world.getEntityByEID(data[0])
                if entityupdate:
                    entityupdate.teleport((data[1], data[2], data[3]))

            elif pkid == self.pktCB.ATTACH_ENTITY:
                data = []
                leash = True  # False to detach
                if self.version < mcpackets.PROTOCOL_1_8START:
                    data = self.packet.readpkt([_INT, _INT, _BOOL])
                    leash = data[2]
                if mcpackets.PROTOCOL_1_8START <= self.version < mcpackets.PROTOCOL_1_9START:
                    data = self.packet.readpkt([_VARINT, _VARINT, _BOOL])
                    leash = data[2]
                if self.version >= mcpackets.PROTOCOL_1_9START:
                    data = self.packet.readpkt([_VARINT, _VARINT])
                    if data[1] == -1:
                        leash = False
                entityeid = data[0]  # rider, leash holder, etc
                vehormobeid = data[1]  # vehicle, leashed entity, etc
                player = self.getPlayerByEID(entityeid)
                # self.log.trace("(PROXY SERVER) -> Parsed ATTACH_ENTITY packet:\n%s", data)

                if player is None:
                    return True

                if entityeid == self.client.servereid:
                    if not leash:
                        self.wrapper.events.callevent("player.unmount", {"player": player})
                        self.log.debug("player unmount called for %s", player.username)
                        self.client.riding = None
                    else:
                        self.wrapper.events.callevent("player.mount", {"player": player, "vehicle_id": vehormobeid,
                                                                       "leash": leash})
                        self.client.riding = vehormobeid
                        self.log.debug("player mount called for %s on eid %s", player.username, vehormobeid)
                        if not self.wrapper.javaserver.world:
                            return
                        entityupdate = self.wrapper.javaserver.world.getEntityByEID(vehormobeid)
                        if entityupdate:
                            self.client.riding = entityupdate
                            entityupdate.rodeBy = self.client

            elif pkid == self.pktCB.DESTROY_ENTITIES:
                # Get rid of dead entities so that python can GC them.
                if not self.wrapper.javaserver.world:
                    # self.log.trace("(PROXY SERVER) -> did not parse DESTROY_ENTITIES packet.")
                    return True
                eids = []
                if self.version < mcpackets.PROTOCOL_1_8START:
                    entitycount = bytearray(self.packet.readpkt([_BYTE])[0])[0]  # make sure we get interable integer
                    parser = [_INT]
                else:
                    entitycount = bytearray(self.packet.readpkt([_VARINT]))[0]
                    parser = [_VARINT]

                for _ in range(entitycount):
                    eid = self.packet.readpkt(parser)[0]
                    try:
                        self.wrapper.javaserver.world.entities.pop(eid, None)
                    except:
                        pass

                # self.log.trace("(PROXY SERVER) -> Parsed DESTROY_ENTITIES pckt:\n%s entities destroyed", entitycount)

            # elif pkid == self.pktCB.MAP_CHUNK_BULK:  # (packet no longer exists in 1.9)
                #  no idea why this is parsed.. we are not doing anything with the data...
                # if mcpackets.PROTOCOL_1_9START > self.version > mcpackets.PROTOCOL_1_8START:
                #     data = self.packet.readpkt([_BOOL, _VARINT])
                #     chunks = data[1]
                #     skylightbool = data[0]
                #     # ("bool:skylight|varint:chunks")
                #     for chunk in xxrange(chunks):
                #         meta = self.packet.readpkt([_INT, _INT, _USHORT])
                #         # ("int:x|int:z|ushort:primary")
                #         primary = meta[2]
                #         bitmask = bin(primary)[2:].zfill(16)
                #         chunkcolumn = bytearray()
                #         for bit in bitmask:
                #             if bit == "1":
                #                 # packetanisc
                #                 chunkcolumn += bytearray(self.packet.read_data(16 * 16 * 16 * 2))
                #                 if self.client.dimension == 0:
                #                     metalight = bytearray(self.packet.read_data(16 * 16 * 16))
                #                 if skylightbool:
                #                     skylight = bytearray(self.packet.read_data(16 * 16 * 16))
                #             else:
                #                 # Null Chunk
                #                 chunkcolumn += bytearray(16 * 16 * 16 * 2)
                #     # self.log.trace("(PROXY SERVER) -> Parsed MAP_CHUNK_BULK packet:\n%s", data)

            elif pkid == self.pktCB.CHANGE_GAME_STATE:
                data = self.packet.readpkt([_UBYTE, _FLOAT])
                # ("ubyte:reason|float:value")
                if data[0] == 3:
                    self.client.gamemode = data[1]
                # self.log.trace("(PROXY SERVER) -> Parsed CHANGE_GAME_STATE packet:\n%s", data)

            elif pkid == self.pktCB.OPEN_WINDOW:
                # This works together with SET_SLOT to maintain accurate inventory in wrapper
                if self.version < mcpackets.PROTOCOL_1_8START:
                    parsing = [_UBYTE, _UBYTE, _STRING, _UBYTE]
                else:
                    parsing = [_UBYTE, _STRING, _JSON, _UBYTE]
                data = self.packet.readpkt(parsing)
                self.currentwindowid = data[0]
                self.noninventoryslotcount = data[3]
                # self.log.trace("(PROXY SERVER) -> Parsed OPEN_WINDOW packet:\n%s", data)

            elif pkid == self.pktCB.SET_SLOT:
                # ("byte:wid|short:slot|slot:data")
                if self.version < mcpackets.PROTOCOL_1_8START:
                    data = self.packet.readpkt([_BYTE, _SHORT, _SLOT_NO_NBT])
                    inventoryslots = 35
                elif self.version < mcpackets.PROTOCOL_1_9START:
                    data = self.packet.readpkt([_BYTE, _SHORT, _SLOT])
                    inventoryslots = 35
                elif self.version > mcpackets.PROTOCOL_1_8END:
                    data = self.packet.readpkt([_BYTE, _SHORT, _SLOT])
                    inventoryslots = 36  # 1.9 minecraft with shield / other hand
                else:
                    data = [-12, -12, None]
                    inventoryslots = 35

                # this only works on startup when server sends WID = 0 with 45/46 items and when an item is moved into
                # players inventory from outside (like a chest or picking something up)
                # after this, these are sent on chest opens and so forth, each WID incrementing by +1 per object opened.
                # the slot numbers that correspond to player hotbar will depend on what window is opened...
                # the last 10 (for 1.9) or last 9 (for 1.8 and earlier) will be the player hotbar ALWAYS.
                # to know how many packets and slots total to expect, we have to parse server-bound pktCB.OPEN_WINDOW.
                if data[0] == 0:
                    self.client.inventory[data[1]] = data[2]

                # Sure.. as though we are done ;)
                # self.log.trace("(PROXY SERVER) -> Parsed SET_SLOT packet:\n%s", data)

                if data[0] < 0:
                    return True

                # This part updates our inventory from additional windows the player may open
                if data[0] == self.currentwindowid:
                    currentslot = data[1]
                    slotdata = data[2]
                    if currentslot >= self.noninventoryslotcount:  # any number of slot above the
                        # pktCB.OPEN_WINDOW declared self.(..)slotcount is an inventory slot for up to update.
                        self.client.inventory[currentslot - self.noninventoryslotcount + 9] = data[2]

            elif pkid == self.pktCB.WINDOW_ITEMS:  # Window Items
                # I am interested to see when this is used and in what versions.  It appears to be superfluous, as
                # SET_SLOT seems to do the purported job nicely.
                data = self.packet.readpkt([_UBYTE, _SHORT])
                windowid = data[0]
                elementcount = data[1]
                # data = self.packet.read("byte:wid|short:count")
                # if data["wid"] == 0:
                #     for slot in range(1, data["count"]):
                #         data = self.packet.readpkt("slot:data")
                #         self.client.inventory[slot] = data["data"]
                elements = []
                if self.version > mcpackets.PROTOCOL_1_7_9:  # just parsing for now; not acting on, so OK to skip 1.7.9
                    for _ in xrange(elementcount):
                        elements.append(self.packet.read_slot())
                jsondata = {
                    "windowid": windowid,
                    "elementcount": elementcount,
                    "elements": elements
                }
                # self.log.trace("(PROXY SERVER) -> Parsed 0x30 packet:\n%s", jsondata)

            elif pkid == "self.pktCB.ENTITY_PROPERTIES":
                ''' Not sure why I added this.  Based on the wiki, it looked like this might
                contain a player uuid buried in the lowdata (wiki - "Modifier Data") area
                that might need to be parsed and reset to the server local uuid.  Thus far,
                I have not seen it used.
                '''
                parser_three = [_UUID, _DOUBLE, _BYTE]
                if self.version < mcpackets.PROTOCOL_1_8START:
                    parser_one = [_INT, _INT]
                    parser_two = [_STRING, _DOUBLE, _SHORT]
                    writer_one = self.packet.send_int
                    writer_two = self.packet.send_short
                else:
                    parser_one = [_VARINT, _INT]
                    parser_two = [_STRING, _DOUBLE, _VARINT]
                    writer_one = self.packet.send_varInt
                    writer_two = self.packet.send_varInt
                raw = b""  # use bytes

                # read first level and repack
                pass1 = self.packet.readpkt(parser_one)
                isplayer = self.getPlayerByEID(pass1[0])
                if not isplayer:
                    return True
                raw += writer_one(pass1[0])
                print(pass1[0], pass1[1])
                raw += self.packet.send_int(pass1[1])

                # start level 2
                for _x in range(pass1[1]):
                    pass2 = self.packet.readpkt(parser_two)
                    print(pass2[0], pass2[1], pass2[2])
                    raw += self.packet.send_string(pass2[0])
                    raw += self.packet.send_double(pass2[1])
                    raw += writer_two(pass2[2])
                    print(pass2[2])
                    for _y in range(pass2[2]):
                        lowdata = self.packet.readpkt(parser_three)
                        print(lowdata)
                        packetuuid = lowdata[0]
                        playerclient = self.client.proxy.getclientbyofflineserveruuid(packetuuid)
                        if playerclient:
                            raw += self.packet.send_uuid(playerclient.uuid.hex)
                        else:
                            raw += self.packet.send_uuid(lowdata[0])
                        raw += self.packet.send_double(lowdata[1])
                        raw += self.packet.send_byte(lowdata[2])
                        print("Low data: ", lowdata)
                # self.packet.sendpkt(self.pktCB.ENTITY_PROPERTIES, [_RAW], (raw,))
                return True

            elif pkid == self.pktCB.PLAYER_LIST_ITEM:
                if self.version >= mcpackets.PROTOCOL_1_8START:
                    head = self.packet.readpkt([_VARINT, _VARINT])
                    # ("varint:action|varint:length")
                    lenhead = head[1]
                    action = head[0]
                    z = 0
                    while z < lenhead:
                        serveruuid = self.packet.readpkt([_UUID])[0]
                        playerclient = self.client.proxy.getclientbyofflineserveruuid(serveruuid)
                        if not playerclient:
                            z += 1
                            continue
                        try:
                            # This is an MCUUID object, how could this fail? All clients have a uuid attribute
                            uuid = playerclient.uuid
                        except Exception as e:
                            # uuid = playerclient
                            self.log.exception("playerclient.uuid failed in playerlist item (%s)", e)
                            z += 1
                            continue
                        z += 1
                        if action == 0:
                            properties = playerclient.properties
                            raw = b""
                            for prop in properties:
                                raw += self.client.packet.send_string(prop["name"])
                                raw += self.client.packet.send_string(prop["value"])
                                if "signature" in prop:
                                    raw += self.client.packet.send_bool(True)
                                    raw += self.client.packet.send_string(prop["signature"])
                                else:
                                    raw += self.client.packet.send_bool(False)
                            raw += self.client.packet.send_varInt(0)
                            raw += self.client.packet.send_varInt(0)
                            raw += self.client.packet.send_bool(False)
                            self.client.packet.sendpkt(self.pktCB.PLAYER_LIST_ITEM,
                                                       [_VARINT, _VARINT, _UUID, _STRING, _VARINT, _RAW],
                                                       (0, 1, playerclient.uuid, playerclient.username,
                                                        len(properties), raw))
                        elif action == 1:
                            data = self.packet.readpkt([_VARINT])
                            gamemode = data[0]
                            # ("varint:gamemode")
                            # self.log.trace("(PROXY SERVER) -> Parsed PLAYER_LIST_ITEM packet:\n%s", data)
                            self.client.packet.sendpkt(self.pktCB.PLAYER_LIST_ITEM,
                                                       [_VARINT, _VARINT, _UUID, _VARINT],
                                                       (1, 1, uuid, data[0]))
                            # print(1, 1, uuid, gamemode)
                        elif action == 2:
                            data = self.packet.readpkt([_VARINT])
                            ping = data[0]
                            # ("varint:ping")
                            # self.log.trace("(PROXY SERVER) -> Parsed PLAYER_LIST_ITEM packet:\n%s", data)
                            self.client.packet.sendpkt(self.pktCB.PLAYER_LIST_ITEM, [_VARINT, _VARINT, _UUID, _VARINT],
                                                       (2, 1, uuid, ping))
                        elif action == 3:
                            data = self.packet.readpkt([_BOOL])
                            # ("bool:has_display")
                            hasdisplay = data[0]
                            if hasdisplay:
                                data = self.packet.readpkt([_STRING])
                                displayname = data[0]
                                # ("string:displayname")
                                # self.log.trace("(PROXY SERVER) -> Parsed PLAYER_LIST_ITEM packet:\n%s", data)
                                self.client.packet.sendpkt(self.pktCB.PLAYER_LIST_ITEM,
                                                           [_VARINT, _VARINT, _UUID, _BOOL, _STRING],
                                                           (3, 1, uuid, True, displayname))
                            else:
                                self.client.packet.sendpkt(self.pktCB.PLAYER_LIST_ITEM,
                                                           [_VARINT, _VARINT, _UUID, _VARINT],
                                                           (3, 1, uuid, False))
                        elif action == 4:
                            self.client.packet.sendpkt(self.pktCB.PLAYER_LIST_ITEM,
                                                       [_VARINT, _VARINT, _UUID], (4, 1, uuid))
                        return False
                else:  # version < 1.7.9 needs no processing
                    return True

            elif pkid == self.pktCB.DISCONNECT:
                message = self.packet.readpkt([_JSON])  # [0]["json"]
                self.log.info("Disconnected from server: %s", message)
                if not self.client.isLocal:  # TODO - multi server code
                    self.close("Disconnected", kill_client=False)
                else:
                    self.client.disconnect(message, fromserver=True)
                # self.log.trace("(PROXY SERVER) -> Parsed DISCONNECT packet")
                return False

            else:
                return True  # no packets parsed - passing to client
            return True  # parsed packet passed on to client

        if self.state == LOGIN:
            if pkid == 0x00:
                message = self.packet.readpkt([_STRING])
                self.log.info("Disconnected from server: %s", message)
                self.client.disconnect(message)
                # self.log.trace("(PROXY SERVER) -> Parsed 0x00 disconnect packet (LOGIN)")
                return False

            if pkid == 0x01:
                self.client.disconnect("Server is in online mode. Please turn it off in server.properties and "
                                       "allow wrapper to handle the authetication.", color="red")
                # self.log.trace("(PROXY SERVER) -> Parsed 0x01 packet with server state 2 (LOGIN)")
                return False

            if pkid == 0x02:  # Login Success - UUID & Username are sent in this packet as strings
                self.state = PLAY
                data = self.packet.readpkt([_STRING, _STRING])
                # self.log.trace("(PROXY SERVER) -> Parsed 0x02 LOGIN SUCCESS - server state 2 (LOGIN): %s", data)
                return False

            if pkid == 0x03:  # Set Compression
                data = self.packet.readpkt([_VARINT])
                # ("varint:threshold")
                if data[0] != -1:
                    self.packet.compression = True
                    self.packet.compressThreshold = data[0]
                else:
                    self.packet.compression = False
                    self.packet.compressThreshold = -1
                # self.log.trace("(PROXY SERVER) -> Parsed 0x03 packet with server state 2 (LOGIN):\n%s", data)
                time.sleep(10)
                return  # False

    def handle(self):
        while not self.abort:
            if self.abort:
                break
            try:
                pkid, original = self.packet.grabPacket()
                self.log.trace("Server.grabPacket: %s %s", (hex(pkid), len(original)))
                # self.lastPacketIDs.append((hex(pkid), len(original)))
                # if len(self.lastPacketIDs) > 10:
                #     for i, v in enumerate(self.lastPacketIDs):
                #         del self.lastPacketIDs[i]
                #         break
            except EOFError as eof:
                # This error is often erroneous, see https://github.com/suresttexas00/minecraft-wrapper/issues/30
                self.log.debug("Packet EOF (%s)", eof)
                break
            except socket.error:  # Bad file descriptor occurs anytime a socket is closed.
                self.log.debug("Failed to grab packet [SERVER] socket closed; bad file descriptor")
                break
            except Exception as e:
                # anything that gets here is a bona-fide error we need to become aware of
                self.log.debug("Failed to grab packet [SERVER] (%s):", e)
                break
            if self.parse(pkid) and self.client:
                try:
                    self.client.packet.sendRaw(original)
                except Exception as e:
                    self.log.debug("[SERVER] Could not send packet (%s): (%s): \n%s", pkid, e, traceback)
                    break
        self.close("Disconnected", kill_client=False)