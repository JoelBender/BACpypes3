#!/bin/bash

# remove everything in the current dist/ directory
[ -d dist ] && rm -Rfv dist

# start with a clean build directory
[ -d build ] && rm -Rfv build

# use the build package
python3 -m build --no-isolation

echo
echo	This is what was built...
echo
ls -1 dist/
echo

# copy the wheel into the docker samples
cp -v dist/*.whl samples/docker/

echo
