from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from .client import GripperClient
from .transport import SerialTransport, SimulatedTransport, Transport


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="HLS3950 力控夹爪命令行工具")
    parser.add_argument("--port", help="控制器串口，例如 /dev/ttyACM0")
    parser.add_argument("--baudrate", type=int, default=115_200)
    parser.add_argument("--simulate", action="store_true", help="使用内置仿真后端")

    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("initialize", "enable", "disable", "status"):
        subparsers.add_parser(command)

    position = subparsers.add_parser("position")
    position.add_argument("left", type=float)
    position.add_argument("right", type=float)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    transport: Transport
    if args.simulate:
        transport = SimulatedTransport()
    elif args.port:
        transport = SerialTransport(args.port, args.baudrate)
    else:
        raise SystemExit("必须提供 --port 或 --simulate")

    client = GripperClient(transport)
    if args.command == "position":
        client.enable()
        status = client.command_position(args.left, args.right)
    else:
        status = getattr(client, args.command)()
    print(json.dumps(asdict(status), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
