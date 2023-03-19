.. BACpypes3 documentation master file, created by
   sphinx-quickstart on Sat Mar 11 00:14:30 2023.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Welcome to BACpypes3!
=====================

.. toctree::
   :maxdepth: 2
   :caption: Contents:

BACpypes3 is a library for building Python applications that communicate using
the :term:`BACnet` protocol.  Installation is easy::

    $ pip install bacpypes3

You will be installing the latest released version from
`PyPI <https://pypi.org/project/bacpypes3/>`_. You can also check out the
latest version from `GitHub <https://github.com/JoelBender/BACpypes3/>`_::

    $ git clone https://github.com/JoelBender/BACpypes3.git
    $ cd BACpypes3

And then use the `pipenv <https://pypi.org/project/pipenv/>`_ utility to create
a virtual environment, install all of the developer tools, then activate it::

    $ pipenv install --dev
    $ pipenv shell

.. note::

    If you would like to participate in development, please join
    the chat room on `Gitter <https://gitter.im/JoelBender/bacpypes>`_.

Getting Started
---------------

The **bacpypes3** module can be run directly.  It will create a small
:term:`stack` of communications objects that are bound together as a
:term:`BACnet device` and present a shell-like prompt::

    $ python3 -m bacpypes3
    >

The module has a variety options for configuring the small stack for different
environments::

    $ python3 -m bacpypes3 --help

And the shell has commands that are useful for examining the local
:term:`BACnet internetwork`, its topology, the connected devices, and their
objects::

    > help

.. toctree::
    :maxdepth: 2

    gettingstarted/index.rst
    samples/index.rst


Glossary
--------

.. toctree::
    :maxdepth: 2

    glossary.rst


Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
