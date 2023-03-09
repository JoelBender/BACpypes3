# BACpypes3 Docker Samples

This sample applications and scripts are for building and running BACpypes
docker images.  The `samples/docker/` directory contains sample dockerfile
configurations and scripts to build and run them.

The repository contains a very simple `bacpypes-greetings` application and
dockerfile, along with a "build" and "run" script.  It is the "Hello, world!"
version of a Python application that imports BACpypes.

## Building Images

There are two options for installing BACpypes in an image; installing from
PyPI over the network or making a package locally and copying it into the
container.

### Option 1 - Installing from PyPI

The simplest way is to install the latest release version which is to include
this dockerfile statement:

    RUN pip install bacpypes3

The latest test version, which is at some stage of development that will most
likely pass the unit tests but might have problems, is pushed up to the test
version of PyPI:

    RUN pip install --upgrade --index-url https://test.pypi.org/simple/ \
        --extra-index-url https://pypi.org/simple/ \
        bacpypes3

The rest of the dockerfile is typical of Python applications.

### Option 2 - Building an Egg or a Wheel

If you are assisting on the development of BACpypes (thank you!) then you
will have a local check-out of the repository and making changes in your
own branch or fork.

Assuming that you are using Python3.8, build an egg by running the `setup.py`
application:

    $ python3 setup.py bdist_egg

The result will be something like `dist/bacpypes3-x.x.x-py3.x.egg`.  This file
needs to be where the application running inside the image can find it
on the Python path.

## Build Scripts

Pulling out the pieces of the `bacpypes-greetings.sh` script, first it needs
to run in the context of the `samples/docker/` directory:

    # the script needs to be run from its directory
    DIR=`dirname $0`
    pushd $DIR > /dev/null

Now the `dist/` directory is a few levels up and contains the egg, this line
finds the latest version:

    # find the latest egg in the dist directory
    BACPYPES_EGG=`ls -1 ../../dist/bacpypes3-*-py3.x.egg | tail -n 1`

Now copy that file into the `samples/docker/` directory so the docker build
mechanism can find it (it has to be in this directory or subdirectory, and
symbolic links are not allowed):

    # copy it into this build directory
    cp -v $BACPYPES_EGG .

Now run the build step and pass the egg file name (without the directory path
in front) as an argument which makes it useable in the dockerfile:

    # build the image passing in the file name
    docker build --tag bacpypes-greetings \
        --file bacpypes-greetings.dockerfile \
        --build-arg BACPYPES_EGG=`basename $BACPYPES_EGG` \
        .

And restore the current working directory:

    popd

There is now a `bacpypes-greetings` image to run.

## Dockerfile Statements

The `bacpypes-greetings.dockerfile` contains the build instructions, starting
with the base image:

    FROM python:3.x-slim

Change to a working directory, otherwise everything is a the root of the file
system:

    WORKDIR /app

Copy the Python application:

    COPY bacpypes-greetings.py .

Referencing the egg file name from the build script which is like "importing"
the value:

    ARG BACPYPES_EGG

Now copy the egg file into the working directory:

    COPY ${BACPYPES_EGG} .

Then tell the Python application that there is an additional egg to use along
the path for import statements:

    ENV PYTHONPATH ${BACPYPES_EGG}

And here is the one and only command to run:

    CMD python bacpypes-greetings.py

## Running the image

The run script is really simple in this case because there are no other
environment configuration pieces that need to be provided:

    docker run -it --rm bacpypes-greetings

This is "run interactively, and remove the container when you're done" and
should output something like this:

    Greetings from BACpypes, version x.x.x

## Docker Networking

The advantage of running containers is that they are in a "sandbox" environment
that is protected, however most BACnet applications communicate with other
BACnet devices that are not on the host.  The answer is to run the container
in "host" networking mode.

Taking a sample run command, the first part is to run the container
interactively and when it is finished then remove the container:

    docker run -it --rm \

This part maps the network of the container to the networking of the host.

        --network host

There are environment variable values that need to be passed from the shell
of the run command into the shell that is going to be executing the
`CMD python3` line in the dockerfile:

        --env BBMD_ADDRESS \
        --env TTL \

And finally the name of the image:

        who-is-console:latest

Now referencing the docker file, the ARG statements line up with the `--env`
options in the run command:

    ARG BBMD_ADDRESS
    ARG TTL

The variable expansion expressions in the CMD can now be expanded:

    CMD python3 who-is-console.py --foreign ${BBMD_ADDRESS} --ttl ${TTL}

This will be running in the container with IPv4 address of the host
using UDP port 47808 and everything the container sends will be from the host
and vice versa.
