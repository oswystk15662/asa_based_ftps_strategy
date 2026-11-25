"""Loopback-only ASA bridge for server observations and optional terrain traces."""
import argparse
from dataclasses import dataclass
import hmac
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import logging
import math
import os
import time
import uuid

MAX_BODY = 16_384
PROTOCOL = 1
MAX_TRACES = 8


def valid_trace(trace):
    return (isinstance(trace, (list, tuple)) and len(trace) == 4
            and all(type(value) in (int, float) and abs(value) <= 2_000_000 for value in trace)
            and 0 < trace[2] - trace[3] <= 200_000)


@dataclass
class Exchange:
    boot_id: str
    command_id: str
    ack: int = 0
    last_snapshot: dict | None = None


class Bridge:
    def __init__(self, world_id, traces=()):
        if len(traces) > MAX_TRACES or not all(map(valid_trace, traces)):
            raise ValueError("Use up to eight traces in UE cm, each with z_high > z_low")
        self.world_id = world_id
        self.traces = [list(trace) for trace in traces]
        self.session = None

    def handle(self, path, body):
        if not isinstance(body, dict):
            return 400, {"error": "invalid_body"}
        if type(body.get("protocol")) is not int or body["protocol"] != PROTOCOL:
            return 409, {"error": "protocol_mismatch"}
        if body.get("world_id") != self.world_id:
            return 409, {"error": "world_mismatch"}
        boot_id = body.get("boot_id")
        try:
            if str(uuid.UUID(boot_id)) != boot_id:
                return 400, {"error": "invalid_boot_id"}
        except (AttributeError, TypeError, ValueError):
            return 400, {"error": "invalid_boot_id"}

        if path == "/v1/hello":
            if self.session is None or self.session.boot_id != boot_id:
                self.session = Exchange(boot_id, str(uuid.uuid4()))
                logging.info("hello boot=%s server_build=%r api_version=%r", boot_id,
                             str(body.get("server_build", ""))[:80],
                             str(body.get("api_version", ""))[:32])
        elif path != "/v1/exchange":
            return 404, {"error": "unknown_endpoint"}

        session = self.session
        if session is None or boot_id != session.boot_id:
            return 409, {"error": "hello_required"}
        if path == "/v1/exchange":
            seq = body.get("seq")
            if type(seq) is not int or not 1 <= seq <= (1 << 53) - 1:
                return 400, {"error": "invalid_seq"}
            if seq > session.ack + 1:
                return 409, {"error": "sequence_gap", "expected_seq": session.ack + 1}
            if seq < session.ack:
                return 409, {"error": "sequence_expired", "expected_seq": session.ack + 1}
            snapshot = body.get("snapshot")
            if body.get("command_id") != session.command_id or not valid_snapshot(snapshot):
                return 400, {"error": "invalid_snapshot"}
            terrain = snapshot.get("terrain")
            if terrain is not None and (
                not isinstance(terrain, list) or len(terrain) != len(self.traces)
                or any(not isinstance(result, dict) or result.get("trace_cm") != trace
                       for result, trace in zip(terrain, self.traces, strict=True))
            ):
                return 400, {"error": "invalid_terrain"}
            if seq == session.ack and snapshot != session.last_snapshot:
                return 409, {"error": "sequence_payload_mismatch"}
            if seq == session.ack + 1:
                session.ack = seq
                session.last_snapshot = snapshot
                logging.info("observation boot=%s seq=%d map=%r players=%d game_seconds=%.3f",
                             boot_id, seq, snapshot["map"], snapshot["players"],
                             snapshot["game_seconds"])
                if terrain is not None:
                    logging.info("terrain %s", json.dumps(terrain, separators=(",", ":")))

        # shortcut: one read-only command and an in-memory cursor per active boot, replace
        # with a durable journal before introducing game mutations or concurrent adapters.
        command = {"kind": "observe_server", "command_id": session.command_id}
        if self.traces:
            command["terrain_traces_cm"] = self.traces
        return 200, {"protocol": PROTOCOL, "world_id": self.world_id, "boot_id": boot_id,
                     "ack": session.ack, "command": command}


def valid_snapshot(snapshot):
    if not isinstance(snapshot, dict):
        return False
    map_name = snapshot.get("map")
    players = snapshot.get("players")
    seconds = snapshot.get("game_seconds")
    return (isinstance(map_name, str) and 0 < len(map_name) <= 128
            and type(players) is int and 0 <= players <= 100_000
            and type(seconds) in (int, float) and 0 <= seconds <= 1e12
            and math.isfinite(seconds))


class Handler(BaseHTTPRequestHandler):
    def setup(self):
        self.request.settimeout(2)
        super().setup()

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            length = 0
        if not 0 < length <= MAX_BODY or self.headers.get("Transfer-Encoding"):
            self.respond(413, {"error": "invalid_length"})
            return
        # Closing a Windows socket with unread request data can reset even a sent reply.
        raw = self.rfile.read(length)
        incoming = self.headers.get("Authorization", "").encode("utf-8")
        if not hmac.compare_digest(incoming, self.server.authorization):
            self.respond(401, {"error": "unauthorized"})
            return
        if self.headers.get_content_type() != "application/json":
            self.respond(415, {"error": "invalid_content_type"})
            return
        try:
            if len(raw) != length:
                raise ValueError("incomplete message")
            body = json.loads(raw.decode("utf-8"))
        except (ValueError, RecursionError):
            self.respond(400, {"error": "invalid_json"})
            return
        status, response = self.server.bridge.handle(self.path, body)
        self.respond(status, response)

    def respond(self, status, response):
        data = json.dumps(response, separators=(",", ":"), allow_nan=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        try:
            self.wfile.write(data)
        except (ConnectionError, TimeoutError):
            logging.info("peer disconnected before receiving HTTP %d", status)

    def log_message(self, *_args):
        # Request paths/headers can contain untrusted data.
        pass


def make_server(world_id, token, port, traces=()):
    if not token or not token.isascii() or not token.isalnum() or not 16 <= len(token) <= 128:
        raise ValueError("ASA_PHASE1_TOKEN must be 16–128 ASCII letters/digits")
    bridge = Bridge(world_id, traces)
    server = HTTPServer(("127.0.0.1", port), Handler)
    server.authorization = f"Bearer {token}".encode("ascii")
    server.bridge = bridge
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--world", default="phase1")
    parser.add_argument("--port", default=8765, type=int)
    parser.add_argument("--trace", nargs=4, type=float, action="append", default=[],
                        metavar=("X", "Y", "Z_HIGH", "Z_LOW"))
    args = parser.parse_args()
    logging.Formatter.converter = time.gmtime
    logging.basicConfig(level=logging.INFO, format="%(asctime)sZ %(message)s")
    try:
        server = make_server(args.world, os.environ.get("ASA_PHASE1_TOKEN", ""), args.port, args.trace)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    with server:
        logging.info("listening on %s:%d world=%r", *server.server_address, args.world)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
