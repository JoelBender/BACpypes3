#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re

from setuptools import setup, find_packages

# load in the project metadata
init_py = open(os.path.join("bacpypes3", "__init__.py")).read()
metadata = dict(re.findall("""__([a-z]+)__ = ["]([^"]+)["]""", init_py))

requirements = []

setup(
    name="bacpypes3",
    version=metadata["version"],
    description="BACnet Communications Library",
    long_description="BACpypes3 provides a BACnet application layer and network layer written in Python3 for daemons, scripting, and graphical interfaces.",
    long_description_content_type="text/x-rst",
    author=metadata["author"],
    author_email=metadata["email"],
    url="https://github.com/JoelBender/bacpypes3",
    packages=find_packages(),
    package_data={"bacpypes3": ["py.typed"]},
    include_package_data=True,
    install_requires=requirements,
    license="MIT",
    zip_safe=False,
    classifiers=[
        "Development Status :: 2 - Pre-Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: BSD License",
        "Natural Language :: English",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
    ],
)
