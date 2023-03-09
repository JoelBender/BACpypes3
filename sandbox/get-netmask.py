"""
Get the network mask of the interface.
"""
import sys
import socket
import fcntl
import struct

SIOCGIFNETMASK = 0x891B


def get_netmask(ifname):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    return socket.inet_ntoa(
        fcntl.ioctl(s.fileno(), SIOCGIFNETMASK, struct.pack("256s", ifname.encode()))[
            20:24
        ]
    )


print(get_netmask(sys.argv[1]))
