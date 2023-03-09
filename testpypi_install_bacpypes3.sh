#!/bin/bash

python3 -m pip install --upgrade \
    --index-url https://test.pypi.org/simple/ \
    --extra-index-url https://pypi.org/simple/ \
    bacpypes3
python3 -c 'import bacpypes3; print("bacpypes3:", bacpypes3.__version__, bacpypes3.__file__)'
