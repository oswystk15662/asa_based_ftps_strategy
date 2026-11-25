"""Replay the Phase 1 read-only exchange without an ASA server."""
import argparse
import http.client
import json
import os
import time
import uuid


def post(port, token, path, body):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
    try:
        connection.request("POST", path, json.dumps(body), {
            "Authorization": f"Bearer {token}", "Content-Type": "application/json",
        })
        response = connection.getresponse()
        return response.status, json.loads(response.read(16_385))
    finally:
        connection.close()


def sample(seconds=0):
    return {"map": "VirtualMap", "players": 0, "game_seconds": seconds}


def run(port, token, world_id, count):
    envelope = {"protocol": 1, "world_id": world_id, "boot_id": str(uuid.uuid4())}
    status, hello = post(port, token, "/v1/hello", {
        **envelope, "server_build": "virtual", "api_version": "virtual",
    })
    if status != 200 or hello["command"]["kind"] != "observe_server":
        raise RuntimeError(f"hello failed: {status}")
    for seq in range(1, count + 1):
        status, reply = post(port, token, "/v1/exchange", {
            **envelope, "seq": seq, "command_id": hello["command"]["command_id"],
            "snapshot": sample(seq),
        })
        if status != 200 or reply["ack"] != seq:
            raise RuntimeError(f"exchange {seq} failed: {status}")
        print(f"observation {seq} acknowledged")
        time.sleep(0.25)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--world", default="phase1")
    parser.add_argument("--port", default=8765, type=int)
    parser.add_argument("--count", default=3, type=int)
    args = parser.parse_args()
    run(args.port, os.environ["ASA_PHASE1_TOKEN"], args.world, args.count)
