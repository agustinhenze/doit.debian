Configuration
=============


doit.cfg
--------

`doit` uses an INI style configuration file
(see `configparser <https://docs.python.org/3/library/configparser.html>`_).
Note: key/value entries can be separated only by the equal sign `=`.

If a file name `doit.cfg` is present in the current working directory,
it is processed. It supports 3 kind of sections:

- a `GLOBAL` section
- a section for each command
- a section for each plugin category


GLOBAL section
^^^^^^^^^^^^^^

The `GLOBAL` section may contain command line options that will
be used (if applicable) by any commands.

Example setting the DB backend type::

 [GLOBAL]
 backend = json

All commands that has a `backend` option (*run*, *clean*, *forget*, etc),
will use this option without the need this option in the command line.


commands section
^^^^^^^^^^^^^^^^

To configure options for a specific command, use a section with
the command name::

 [list]
 status = True
 subtasks = True

.. note::

  The key name is the internal option name, it might not be the same as
  the string using in the command line. i.e. `subtasks` above refers to
  `--all`.


plugins sections
^^^^^^^^^^^^^^^^

Check the :ref:`plugins <plugins>` section for an introduction
on available plugin categories.


configuration at *dodo.py*
--------------------------

As a convenience you can also set `GLOBAL` options directly into a `dodo.py`.
Just put the option in the `DOIT_CONFIG` dict.
This example below sets the default tasks to be run, the ``continue`` option,
and a different reporter.

.. literalinclude:: tutorial/doit_config.py

So if you just execute

.. code-block:: console

   $ doit

it will have the same effect as executing

.. code-block:: console

   $ doit --continue --reporter json my_task_1 my_task_2


.. note::

  Not all options can be set on `dodo.py` file.
  The parameters ``--file`` and ``--dir`` can not be used on config because
  they control how the *dodo* file itself is loaded.

  Also if the command does not read the `dodo.py` file it obviously will
  not be used.
