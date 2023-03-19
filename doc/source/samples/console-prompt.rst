.. console-prompt.py sample application

.. _console-prompt.py:

console-prompt.py
=================

This is almost identical to the :ref:`console.py` example, all this does is
add a `\-\-prompt` option.

The `ArgumentParser` class in BACpypes3 is a subclass of the built-in class
with the same name, so extending it is simple::

    args = ArgumentParser().parse_args()

The code is replaced with this::

    # add a way to change the console prompt
    parser = ArgumentParser()
    parser.add_argument(
        "--prompt",
         type=str,
         help="change the prompt",
         default="> ",
    )
    args = parser.parse_args()

And the `Console` constructor changes from this::

     console = Console()

to include the prompt::

     console = Console(prompt=args.prompt)

Turning on debugging shows the new argument along with the others that are
built-in::

    $ python3 console-prompt.py --prompt '? ' --debug
    DEBUG:__main__:args: Namespace(..., prompt='? ')
    DEBUG:__main__:settings: {'debug': ['__main__'], 'color': False, ... }
    ?

