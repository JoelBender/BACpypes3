"""
Get the IPv4 address of an interface.

https://gist.github.com/socketz/fc9bbbba7be561852ae8905e277402b8
"""
import sys
import socket
import fcntl
import struct

SIOCGIFADDR = 0x8915


def get_ip_address(ifname):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    fdsock = s.fileno()

    ifreq = struct.pack("16sH14s", ifname.encode(), socket.AF_INET, b"\x00" * 14)
    try:
        res = fcntl.ioctl(fdsock, SIOCGIFADDR, ifreq)
    except:
        return None
    return socket.inet_ntoa(struct.unpack("16sH2x4s8x", res)[2])


print(get_ip_address(sys.argv[1]))
