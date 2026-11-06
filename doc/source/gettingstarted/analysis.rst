.. BACpypes Getting Started 1

.. _analysis:

Packet Analysis
===============

The **bacpypes3.analysis** module decodes BACnet traffic into frames, with
the link, IP, BVLL, NPDU and APDU layers each decoded.  The traffic can come
from pcap files, for example ones saved by Wireshark, or be captured live
from a network interface.

The module needs the optional ``python-libpcap`` package, which is included
in the ``pylibpcap`` extra::

    $ pip install "bacpypes3[pylibpcap]"

The package is a wrapper around the libpcap C library.  If pip has to build
it from source, the library and its headers have to be installed first
(``libpcap-dev`` on Debian and Ubuntu).

Decoding Files
--------------

Give the module one or more pcap file names and it prints each frame as a
timestamp followed by a JSON object::

    $ python3 -m bacpypes3.analysis capture.pcap

Reading a file only needs permission to read the file.

Capturing From an Interface
---------------------------

The ``-i`` option captures from an interface and decodes the packets as they
arrive.  By default it captures UDP port 47808 in promiscuous mode until it
is stopped with Ctrl-C::

    $ python3 -m bacpypes3.analysis -i eth0

.. list-table::
    :header-rows: 1
    :widths: 30 70

    * - Option
      - Description
    * - ``-i``, ``--interface``
      - the name of the interface to capture from
    * - ``-f``, ``--filter``
      - a libpcap capture filter, the default is ``udp port 47808``
    * - ``-c``, ``--count``
      - stop after this many packets, the default is to keep going
    * - ``-p``, ``--no-promiscous``
      - don't put the interface into promiscuous mode
    * - ``--timeout``
      - the libpcap read timeout in milliseconds, the default is 500
    * - ``--linktype``
      - the link-layer header type: a number or one of ``null``,
        ``ethernet``, ``arcnet-bsd``, ``raw``, ``loop``, ``linux-sll``,
        ``arcnet-linux``, ``ipv4``, ``ipv6`` or ``linux-sll2``.  The default
        comes from the interface type (Linux only), otherwise ``ethernet``
    * - ``--data``
      - include the data of each layer as hex strings

Permission to Capture
---------------------

Capturing from an interface opens a raw packet socket.  On Linux that needs
the ``CAP_NET_RAW`` capability, which ordinary users don't have, so the
capture fails:

.. code-block:: text

    $ python3 -m bacpypes3.analysis -i eth0
    error: eth0: Attempt to create packet socket failed - CAP_NET_RAW may be required (see the bacpypes3.analysis module documentation)

    Capturing from an interface needs the CAP_NET_RAW capability, either:
    ...

The module prints a summary of the options described below and exits with
status 1.  An application calling ``decode_iface()`` gets a
``PermissionError`` with the original ``LibpcapError`` as its cause.  Other
libpcap errors, such as an interface that doesn't exist, are raised
unchanged.

There are three ways to capture, from the least privileged to the most.

Capture with dumpcap or tcpdump, then decode the file
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Use a capture tool that already has permission, then decode the file it
writes::

    $ dumpcap -i eth0 -f "udp port 47808" -a duration:60 -F pcap -w capture.pcap
    $ python3 -m bacpypes3.analysis capture.pcap

``-F pcap`` writes classic pcap rather than pcapng.  ``-a duration:60`` stops
after a minute; ``-c <count>`` stops after that many packets, or stop it with
Ctrl-C.  ``dumpcap`` is the capture program that comes with Wireshark.

When Wireshark is installed on Debian or Ubuntu and "non-superusers may
capture packets" is selected, ``/usr/bin/dumpcap`` is given the
``cap_net_raw`` and ``cap_net_admin`` capabilities, and members of the
``wireshark`` group can run it as themselves.  To check::

    $ getcap /usr/bin/dumpcap
    /usr/bin/dumpcap cap_net_admin,cap_net_raw=eip
    $ id -nG
    ... wireshark

and to set it up, then log out and back in so the group membership takes
effect::

    $ sudo dpkg-reconfigure wireshark-common
    $ sudo usermod -aG wireshark $USER

``tcpdump`` works too, but it normally has to be run as root::

    $ sudo tcpdump -i eth0 -w capture.pcap udp port 47808

This is the best choice for routine use: neither BACpypes3 nor Python runs
with any extra privileges.  The drawback is that the packets are not decoded
as they arrive.

Run as root
~~~~~~~~~~~

::

    $ sudo .venv/bin/python -m bacpypes3.analysis -i eth0

Give the path to the virtual environment's interpreter.  ``sudo`` resets
``PATH``, so a plain ``python3`` would be the system interpreter, which
probably doesn't have ``python-libpcap`` (or BACpypes3) installed.

This is the simplest choice for an occasional live capture, but the whole
program, including any bugs in the packet decoding, runs as root.

Give the interpreter the capability
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

::

    $ sudo setcap cap_net_raw,cap_net_admin=eip "$(readlink -f .venv/bin/python)"
    $ python3 -m bacpypes3.analysis -i eth0

After this, live capture works as an ordinary user.  ``setcap`` doesn't follow
symbolic links and a virtual environment's ``python`` is usually one, hence
the ``readlink -f``.

.. caution::

    The capability belongs to the interpreter binary, not to BACpypes3, so
    **every** script run with that interpreter can open raw sockets.  An
    interpreter managed by uv or pyenv is shared by all of the virtual
    environments created from it.  The safer variant is a separate copy of
    the interpreter used only for capturing.

Also:

* The capability is lost when the binary is replaced, for example when uv
  or the system package manager installs a new Python release, and has to
  be applied again.
* It has no effect on a file system mounted ``nosuid``.
* Remove it with ``sudo setcap -r <path>``.
* ``CAP_NET_RAW`` is what opening the socket needs; ``cap_net_admin`` is
  included to match what Wireshark gives ``dumpcap``.

Other platforms
~~~~~~~~~~~~~~~

* **Containers** -- the container also needs the capability, for example
  ``docker run --cap-add NET_RAW ...``.
* **macOS** -- capturing needs access to the ``/dev/bpf*`` devices.  The
  Wireshark installer's "ChmodBPF" component grants it to members of the
  ``access_bpf`` group.
* **Windows** -- live capture needs `Npcap <https://npcap.com/>`_.

Using the Module in an Application
----------------------------------

``decode_file()`` and ``decode_iface()`` are generators that yield ``Frame``
objects, and ``decode_packet()`` decodes a single packet given its bytes and
the link-layer type::

    from bacpypes3.analysis import decode_file, decode_iface

    for frame in decode_file("capture.pcap"):
        print(frame.dict_contents())

    try:
        for frame in decode_iface("eth0", count=10):
            print(frame.dict_contents())
    except PermissionError as err:
        print(f"cannot capture: {err}")
