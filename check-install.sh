#!/bin/bash

for version in 3.7 3.8 3.9 3.10;
do
if [ -a "`which python$version`" ]; then
    echo "===== $version ====="
    python$version check-install.py
    echo
fi
done
