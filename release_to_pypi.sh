#!/bin/bash

# build a distribution
. bdist.sh

read -p "Upload to PyPI? [y/n/x] " yesno || exit 1

if [ "$yesno" = "y" ] ;
then
    twine upload dist/*
elif [ "$yesno" = "n" ] ;
then
    echo "Skipped..."
else
    echo "exit..."
    exit 1
fi

