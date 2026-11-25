import contextlib
import http.client
from pathlib import Path
import sys
import threading
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "simulator"))
from phase1 import MAX_BODY, make_server
from virtual_adapter import post, sample


class BridgeTest(unittest.TestCase):
    token = "Phase1TestToken0123456789"
    world = "phase1"

    @contextlib.contextmanager
    def listener(self, port=0, traces=()):
        server = make_server(self.world, self.token, port, traces)
        worker = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
        worker.start()
        self.port = server.server_port
        try:
            yield server
        finally:
            server.shutdown()
            worker.join()
            server.server_close()

    def request(self, path, body, token=None):
        return post(self.port, token or self.token, path, body)

    def hello(self, envelope):
        status, reply = self.request("/v1/hello", envelope)
        self.assertEqual(200, status)
        return reply

    def setUp(self):
        self.envelope = {"protocol": 1, "world_id": self.world, "boot_id": str(uuid.uuid4())}

    def test_exchange_duplicate_and_gap(self):
        with self.listener() as server:
            hello = self.hello(self.envelope)
            self.assertEqual(0, hello["ack"])
            self.assertEqual("observe_server", hello["command"]["kind"])
            exchange = {**self.envelope, "seq": 1, "snapshot": sample(1),
                        "command_id": hello["command"]["command_id"]}
            for _ in range(2):
                status, reply = self.request("/v1/exchange", exchange)
                self.assertEqual((200, 1), (status, reply["ack"]))
            status, _ = self.request("/v1/exchange", {**exchange, "snapshot": sample(99)})
            self.assertEqual(409, status)
            status, reply = self.request("/v1/exchange", {**exchange, "seq": 3})
            self.assertEqual((409, 2), (status, reply["expected_seq"]))
            self.assertEqual(sample(1), server.bridge.session.last_snapshot)
            self.assertEqual(1, self.hello(self.envelope)["ack"])
            status, reply = self.request("/v1/exchange", {**exchange, "seq": 2})
            self.assertEqual((200, 2), (status, reply["ack"]))
            status, reply = self.request("/v1/exchange", exchange)
            self.assertEqual((409, 3), (status, reply["expected_seq"]))

    def test_reconnect_to_restarted_bridge_and_reject_old_boot(self):
        with self.listener():
            hello = self.hello(self.envelope)
            exchange = {**self.envelope, "seq": 1, "snapshot": sample(),
                        "command_id": hello["command"]["command_id"]}
            self.assertEqual(200, self.request("/v1/exchange", exchange)[0])
            port = self.port
        with self.assertRaises(OSError):
            self.request("/v1/exchange", exchange)
        with self.listener(port):
            self.assertEqual(409, self.request("/v1/exchange", exchange)[0])
            reply = self.hello(self.envelope)
            self.assertEqual(0, reply["ack"])
            self.assertNotEqual(hello["command"], reply["command"])
            exchange["command_id"] = reply["command"]["command_id"]
            self.assertEqual(200, self.request("/v1/exchange", exchange)[0])
            self.hello({**self.envelope, "boot_id": str(uuid.uuid4())})
            self.assertEqual(409, self.request("/v1/exchange", exchange)[0])

    def test_reject_invalid_messages(self):
        with self.listener() as server:
            for extra in ({"protocol": 2}, {"protocol": True}, {"world_id": "other"}):
                self.assertEqual(409, self.request("/v1/hello", {**self.envelope, **extra})[0])
            self.assertEqual(401, self.request("/v1/hello", self.envelope, "wrong")[0])
            conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=2)
            try:
                conn.request("POST", "/v1/hello", headers={"Content-Length": str(MAX_BODY + 1)})
                self.assertEqual(413, conn.getresponse().status)
                conn.close()
                conn.request("POST", "/v1/hello", b"{invalid}", {
                    "Authorization": f"Bearer {self.token}", "Content-Type": "application/json",
                })
                self.assertEqual(400, conn.getresponse().status)
            finally:
                conn.close()
            self.assertIsNone(server.bridge.session)
            hello = self.hello(self.envelope)
            invalid = {**self.envelope, "seq": 1, "snapshot": sample(-1),
                       "command_id": hello["command"]["command_id"]}
            self.assertEqual(400, self.request("/v1/exchange", invalid)[0])
            self.assertEqual(0, server.bridge.session.ack)

    def test_terrain_requests_and_results_are_bound_to_columns(self):
        column = [100, -200, 300, -400]
        with self.assertRaises(ValueError):
            make_server(self.world, self.token, 0, [[0, 0, -1, 1]])
        with self.listener(traces=[column]) as server:
            hello = self.hello(self.envelope)
            self.assertEqual([column], hello["command"]["terrain_traces_cm"])
            result = {"trace_cm": column, "status": "unobserved"}
            exchange = {**self.envelope, "seq": 1, "command_id": hello["command"]["command_id"]}
            invalid = {"trace_cm": [0, 0, 300, -400], "status": "unobserved"}
            for value in ([], [invalid]):
                self.assertEqual(400, self.request(
                    "/v1/exchange", {**exchange, "snapshot": {**sample(), "terrain": value}})[0])
            self.assertEqual(0, server.bridge.session.ack)
            valid = {**exchange, "snapshot": {**sample(), "terrain": [result]}}
            self.assertEqual(200, self.request("/v1/exchange", valid)[0])
            self.assertEqual(1, server.bridge.session.ack)


if __name__ == "__main__":
    unittest.main()
