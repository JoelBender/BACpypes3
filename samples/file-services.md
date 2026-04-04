# File Services

This is a brief description of the File Services sample applications, and
examples of running them.  There are two applications, **file-server.py**
and **file-console.py**.

Assume that these examples are running on the host at 10.0.1.176.

## Running the Server

The server application is a console-less application that has two File
objects; one that uses Record Access and the other that uses Stream Access.

One one terminal window, launch the application and there will be some
debugging output:

    $ uv run python3 samples/file-server.py --debug
    DEBUG:__main__:args: Namespace(loggers=False, debug=[], color=None,
        route_aware=None, name='Excelsior', instance=999, network=0,
        address=None, vendoridentifier=999, foreign=None, ttl=30, bbmd=None)

Note that **address=None** which implies that the application will be using
whatever network interface is available.  This is the default for the
**--address** parameter and is the same as providing it explicitly:

    $ uv run python3 samples/file-server.py --address host --debug

Or the explicit reference to the host address and network:

    $ uv run python3 samples/file-server.py --address 10.0.1.176/24 --debug

First is debugging of the custom application.  When file services is merged
into the **main** branch this will no longer be custom:

    DEBUG:__main__:app: <__main__.CustomApplication object at 0x10bab8ec0>

Here are the contents of the two file objects, note the the **fileSize**
and **recordCount** properties are Python property objects that are
calculated on demand, the others are static:

    DEBUG:__main__:record_access_file_object: <bacpypes3.local.file.LocalRecordAccessFileObject object at 0x10bab9fd0>
        <bacpypes3.local.file.LocalRecordAccessFileObject object at 0x10bab9fd0>
            objectIdentifier = (<ObjectType: file>, 1)
            objectName = 'File 1'
            objectType = <ObjectType: file>
            fileSize = <property object at 0x106036f70>
            fileAccessMethod = <FileAccessMethod: record-access>
            recordCount = <property object at 0x106037060>
    DEBUG:__main__:stream_access_file_object: <bacpypes3.local.file.LocalStreamAccessFileObject object at 0x10bab8590>
        <bacpypes3.local.file.LocalStreamAccessFileObject object at 0x10bab8590>
            objectIdentifier = (<ObjectType: file>, 2)
            objectName = 'File 2'
            objectType = <ObjectType: file>
            fileSize = <property object at 0x106037240>
            fileAccessMethod = <FileAccessMethod: stream-access>

### Running the Client

The client application presents a console for read and write commands.  In
a second terminal window, launch the application with a custom port number
and there will be some debugging output:

    $ uv run samples/file-console.py --address host:47809 --debug
    DEBUG:__main__:args: Namespace(loggers=False, debug=[], color=None,
        route_aware=None, name='Excelsior', instance=999, network=0,
        address='host:47809', vendoridentifier=999, foreign=None, ttl=30, bbmd=None)
    DEBUG:__main__:app: <__main__.CustomApplication object at 0x10b7c17f0>

Two applications running on the same machine cannot open the same port at the
same time, so the **--address=host:47809** puts the "device" on a different
BACnet network.  You'll also note that the same device name and device instance
number are being reused, which would be a violation of the standard if they
were both members of the same BACnet intranet.

Ignoring all that for testing:

    > help
    read_record and read_stream commands.

    commands: exit, help, read_record, read_stream, write_record, write_stream

### Reading and Writing Records

Try a **read_record** command:

    > read_record host file,1 1 1

The first parameter is the BACnet address of the server which is running on
the **host** address using the default port 47808.  The second parameter is the
object identifier of the Record Access File Object, the next two parameters
are the file start position and the number of recrods:

    DEBUG:__main__.SampleCmd:do_read_record <IPv4Address 10.0.1.176> (<ObjectType: file>, 1) 1 1
    DEBUG:__main__.SampleCmd:    - exception: <bacpypes3.primitivedata.Error(atomic-read-file)(ErrorPDU,0) instance at 0x10b751e80>
        <bacpypes3.primitivedata.Error(atomic-read-file)(ErrorPDU,0) instance at 0x10b751e80>
            pduSource = <IPv4Address 10.0.1.176>
            pduExpectingReply = False
            pduNetworkPriority = 0
            apduType = 5
            apduService = 6
            apduInvokeID = 0
            errorClass = <ErrorClass: services>
            errorCode = <ErrorCode: invalid-file-start-position>
            pduData = x''

This is returning an error because the file object has no records!  Now let's
write one:

    > write_record host file,1 0 snork
    DEBUG:__main__.SampleCmd:do_write_record <IPv4Address 10.0.1.176> (<ObjectType: file>, 1) 0 ('snork',)
    file_start_record=0

Success, now we can read it:

    > read_record host file,1 0 1
    DEBUG:__main__.SampleCmd:do_read_record <IPv4Address 10.0.1.176> (<ObjectType: file>, 1) 0 1
    end_of_file=1, returned_record_count=1, file_record_data=[b'snork\n']

This particular file assumes that records are terminated with newline terminated so the newline
is added at the end of the request and returned in the record contents.  The sample application
can write more than one record:

    > write_record host file,1 0 rec0 rec1 rec2
    DEBUG:__main__.SampleCmd:do_write_record <IPv4Address 10.0.1.176> (<ObjectType: file>, 1) 0 ('rec0', 'rec1', 'rec2')
    file_start_record=0

And reading them returns a list:

    > read_record host file,1 0 99
    DEBUG:__main__.SampleCmd:do_read_record <IPv4Address 10.0.1.176> (<ObjectType: file>, 1) 0 99
    end_of_file=1, returned_record_count=3, file_record_data=[b'rec0\n', b'rec1\n', b'rec2\n']

### Reading and Writing Streams

The Stream Access File also starts out empty so add some data so we can read it back out:

    > write_stream host file,2 0 snork
    DEBUG:__main__.SampleCmd:do_write_stream <IPv4Address 10.0.1.176> (<ObjectType: file>, 2) 0 'snork'
    file_start_position=0

In this case there is no newline at the end, it is just character data.  There
is no attempt to interpret the record data as hex encoded.

    > read_stream host file,2 0 999
    DEBUG:__main__.SampleCmd:do_read_stream <IPv4Address 10.0.1.176> (<ObjectType: file>, 2) 0 999
    DEBUG:__main__.SampleCmd:    - file_data: b'snork'
    end_of_file=1, file_start_position=0, file_data=b'snork'

Writing to a stream needs the offset and data:

    > write_stream host file,2 2 XX
    DEBUG:__main__.SampleCmd:do_write_stream <IPv4Address 10.0.1.176> (<ObjectType: file>, 2) 2 'XX'
    file_start_position=2

Now reading it back out shows the XX data stuffed in the middle.

    > read_stream host file,2 0 999
    DEBUG:__main__.SampleCmd:do_read_stream <IPv4Address 10.0.1.176> (<ObjectType: file>, 2) 0 999
    DEBUG:__main__.SampleCmd:    - file_data: b'snXXk'
    end_of_file=1, file_start_position=0, file_data=b'snXXk'
