.. BACpypes Getting Started 1

Setup
=====

This tutorial starts with just enough of the basics of BACnet to get a
workstation communicating with another device.  If you are already familiar
with BACnet, skip to the next section.

Basic Assumptions
-----------------

I will assume you are a software developer and it is your job to communicate
with a device from another company that uses BACnet.  Your employer has
given you a test device and purchased a copy of the BACnet standard.

If you do not have another device, you can run two BACpypes3 applications
or two instances of the same application on one machine but it is slightly
more cumbersome to specify source and destination addresses.

Installation
------------

You should have:

* a development workstation running some flavor of Linux, Windows, or MacOS,
  complete with the latest version of Python (>= 3.8)
  and `setup tools <https://pypi.python.org/pypi/setuptools#unix-based-systems-including-mac-os-x>`_
  and `pip <https://pypi.org/project/pip/>`_.  It is also recommended that
  you use the builtin `venv <https://docs.python.org/3/library/venv.html>`_, or
  `pipenv <https://pypi.org/project/pipenv/>`_ for creating virtual environments.

* a small Ethernet hub into which you can plug both your workstation and your
  mysterious BACnet device, so you won't be distracted by lots of other network traffic.

* a BACnetIP/BACnet-MSTP Router if your mysterious device is an MSTP device
  (BACpypes communicates using BACnet/IPv4 or BACnet/IPv6)

* if you are running on Windows, installing Python may be a challenge. Some
  Python packages make your life easier by including the core Python plus
  many other data processing toolkits, so have a look at Continuum Analytics
  `Anaconda <https://www.continuum.io/downloads>`_ or Enthought
  `Canopy <https://www.enthought.com/products/canopy/>`_.

* if you are running on Windows it might be beneficial to install the
  Windows Subsystem for Linux (`WSL <https://learn.microsoft.com/en-us/windows/wsl/install>`_)
  and proceed inside that virtual environment.


Before getting this test environment set up and while you are still connected
to the internet, create a virtual environment and install the BACpypes library::

    $ python3 -m venv myenv
    $ cd myenv
    $ source bin/activate
    $ pip install bacpypes3
    $ ...
    $ deactivate

or::

    $ pipenv --python `which python3`
    $ pipenv install bacpypes3
    $ pipenv shell
    $ ...
    $ exit

or to install in the local user path without requiring write access to the
system install Python::

    $ pip install bacpypes3 --user

or to install in the system (not recommended)::

    $ sudo pip install bacpypes3

Optional Packages
-----------------

BACpypes3 has no other dependencies but there are other libraries that will
be used if they are available:

* `websockets <https://pypi.org/project/websockets/>`_ is required for
  BACnet/SC communications (still being developed)
* `ifaddr <https://pypi.org/project/ifaddr/>`_ is used to resolve interface
  names with IPv4 and IPv6 addresses.  The `netifaces <https://pypi.org/project/netifaces/>`_
  package can also be used but it is no longer being maintained.
* `pyyaml <https://pypi.org/project/PyYAML/>`_ is used to provide YAML
  configuration files which have some advantages over using JSON or INI formatted
  files.
* `rdflib <https://pypi.org/project/rdflib/>`_ is used for
  `RDF <https://www.w3.org/RDF/>`_ encoding and decoding content for Enterprise
  Knowledge Graphs and Semantic Web applications.

Installation from Source Code
-----------------------------

The GitHub repository contains the source code for the package along with
numerous sample applications.  Installing the developer version of the
package includes the optional packages that are useful for BACpypes3
applications listed above, along with testing using **pytest** and documentation
using **sphinx**. Install the `Git <https://en.wikipedia.org/wiki/Git>`_ software
from `here <https://git-scm.com/downloads>`_, then make a local copy of the
repository by cloning it::

    $ git clone https://github.com/JoelBender/BACpypes3.git
    $ cd BACpypes3
    $ pipenv install --dev
    $ pipenv shell
    $ ...
    $ exit


Wireshark Packet Analysis
-------------------------

No protocol analysis workbench would be complete without an installed
copy of `Wireshark <http://www.wireshark.org/>`_::

    $ sudo apt-get install wireshark

or if you use Windows, `download it here <https://www.wireshark.org/download.html>`_.

.. caution::

    Don't forget to **turn off your firewall** before beginning to use BACpypes3!
    It will prevent you from hours of research when your code won't work as it
    should!  On a production device you should configure the firewall to only
    allow traffic to and from specific ports, usually UDP port 47808 and maybe
    others.

