#!/bin/bash

# build a distribution
. build_dist.sh

read -p "Upload to Test PyPI? [y/n/x] " yesno || exit 1

if [ "$yesno" = "y" ] ;
then
    twine upload -r testpypi --config-file .pypirc dist/*
elif [ "$yesno" = "n" ] ;
then
    echo "Skipped..."
else
    echo "exit..."
    exit 1
fi

