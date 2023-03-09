#!/bin/bash

# remove everything in the current dist/ directory
[ -d dist ] && rm -Rfv dist

# start with a clean build directory
[ -d build ] && rm -Rfv build

for version in 3.7 3.8 3.9 3.10; do
    latest=`which python$version`
    if [ -a "$latest" ]; then
        $latest setup.py bdist_egg
        rm -Rfv build/
    fi
done

# use the latest version to build the wheel
$latest setup.py bdist_wheel

echo
echo	This is what was built...
echo
ls -1 dist/
echo

# copy the wheel in to the docker samples
cp -v dist/*.whl samples/docker/

echo
