import argparse

parser = argparse.ArgumentParser(description='''
Usage:
    -- <program> --ip-address <IP_ADDRESS> --port <PORT>
''')

parser.add_argument(
    "--ip-address",
    type=None,
    required=True,
    help="Server's IP Address."
)

parser.add_argument(
    "--port",
    type=None,
    required=True,
    help="Server's Port Number."
)

parser.add_argument(
    "--time-limit",
    type=None,
    help="Server's Port Number."
)

args = parser.parse_args()