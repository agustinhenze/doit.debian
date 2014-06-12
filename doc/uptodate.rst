================
custom uptodate
================

The basics of `uptodate` was already introduced. Here we look in more
detail into some implementations shipped with `doit`. And the API used by those.


result-dependency
----------------------

In some cases you can not determine if a task is "up-to-date" only based on
input files, the input could come from a database or an external process.
*doit* defines a "result-dependency" to deal with these cases without need to
create an intermediate file with the results of the process.

i.e. Suppose you want to send an email every time you run *doit* on a mercurial
repository that contains a new revision number.

.. literalinclude:: tutorial/taskresult.py


Note the `result_dep` with the name of the task ('version'). `doit` will keep
track of the output of the task *version* and will execute *send_email* only
when the mercurial repository has a new version since last
time *doit* was executed.

The "result" from the dependent task compared between different runs is given
by its last action.
The content for python-action is the value of the returned string or dict.
For cmd-actions it is the output send to stdout plus stderr.

`result_dep` also supports group-tasks. In this case it will check that the
result of all subtasks did not change. And also the existing sub-tasks are
the same.



run-once
---------------

Sometimes there is no dependency for a task but you do not want to execute it
all the time. With "run_once" the task will not be executed again after the first
successful run. This is mostly used together with targets.

Suppose you need to download something from internet.
There is no dependency, but you do not want to download it many times.


.. literalinclude:: tutorial/download.py

Note that even with *run_once* the file will be downloaded again in case the target is removed.


.. code-block:: console

    $ doit
    .  get_pylogo
    $ doit
    -- get_pylogo
    $ rm python-logo.gif
    $ doit
    .  get_pylogo



timeout
---------

``timeout`` is used to expire a task after a certain time interval.

i.e. You want to re-execute a task only if the time elapsed since the last
time it was executed is bigger than 5 minutes.

.. literalinclude:: tutorial/timeout.py


``timeout`` is function that takes an ``int`` (seconds) or ``timedelta`` as a
parameter. It returns a callable suitable to be used as an ``uptodate`` callable.



config_changed
---------------

``config_changed`` is used to check if any "configuration" value for the task has
changed. Config values can be a string or dict.

For dict's the values are converted to string (actually it uses python's `repr()`)
and only a digest/checksum of the dictionaries keys and values are saved.

.. literalinclude:: tutorial/config_params.py


check_timestamp_unchanged
--------------------------

``check_timestamp_unchanged`` is used to check if specified timestamp of a given
file/dir is unchanged since last run.

The timestamp field to check defaults to ``mtime``, but can be selected by
passing ``time`` parameter which can be one of: ``atime``, ``ctime``, ``mtime``
(or their aliases ``access``, ``status``, ``modify``).

Note that ``ctime`` or ``status`` is platform dependent.
On Unix it is the time of most recent metadata change,
on Windows it is the time of creation.
See `Python library documentation for os.stat`__ and Linux man page for
stat(2) for details.

__ http://docs.python.org/library/os.html#os.stat

It also accepts an ``cmp_op`` parameter which defaults to ``operator.eq`` (==).
To use it pass a callable which takes two parameters (prev_time, current_time)
and returns True if task should be considered up-to-date, False otherwise.
Here ``prev_time`` is the time from the last successful run and ``current_time``
is the time obtained in current run.

If the specified file does not exist, an exception will be raised.
If a file is a target of another task you should probably add
``task_dep`` on that task to ensure the file is created before it is checked.

.. literalinclude:: tutorial/check_timestamp_unchanged.py


.. _uptodate_api:

uptodate API
--------------

This section will explain how to extend ``doit`` writing an ``uptodate``
implementation. So unless you need to write an ``uptodate`` implementation
you can skip this.

The callable must take at least two positional parameters ``task`` and ``values``.
The callable can also be represented by a tuple (callable, args, kwargs).

   -  ``task`` parameter will give you access to task object. So you have access
      to its metadata and opportunity to modify the task itself!
   -  ``values`` is a dictionary with the computed values saved in the last
       successful execution of the task.


Let's start with trivial example.

.. literalinclude:: tutorial/uptodate_callable.py

Note that `check_outdated` function is not actually using the parameters.
You could also execute this function in the task-creator and pass the value
to to `uptodate`. The advantage of just passing the callable is that this
check will not be executed at all if the task was not selected to be executed.


Example: run-once implementation
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Most of the time an `uptodate` implementation will compare the current value
of something with the value it had last time the task was executed.

We already saw how tasks can save values by returning dict on its actions.
But usually the "value" we want to check is independent from the task actions.
So the first step is to add a callable to the task so it can save some extra
values. These values are not used by the task itself, they are only used
for dependency checking.

The Task has a property called ``value_savers`` that contains a list of
callables. These callables should return a dict that will be saved together
with other task values. The ``value_savers`` will be executed after all actions.

The second step is to actually compare the saved value with its "current" value.

Let's take a look in the ``run_once`` implementation.

.. literalinclude:: tutorial/run_once.py

The function ``save_executed`` returns a dict. In this case it is not checking
for any value because it just checks it the task was ever executed.

The next line we use the ``task`` parameter adding
``save_executed`` to ``task.value_savers``.So whenever this task is executed this
task value 'run-once' will be saved.

Finally the return value should be a boolean to indicate if the task is
up-to-date or not. Remember that the 'values' parameter contains the dict with
the values saved from last successful execution of the task.
So it just checks if this task was executed before by looking for the
``run-once`` entry in ```values``.


Example: timeout implementation
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Let's look another example, the ``timeout``. The main difference is that
we actually pass the parameter ``timeout_limit``. Here we present
a simplified version that only accepts integers (seconds) as a parameter.


.. code-block:: python

    class timeout(object):
        def __init__(self, timeout_limit):
            self.limit_sec = timeout_limit

        def __call__(self, task, values):
            def save_now():
                return {'success-time': time_module.time()}
            task.value_savers.append(save_now)
            last_success = values.get('success-time', None)
            if last_success is None:
                return False
            return (time_module.time() - last_success) < self.limit_sec

This is a class-based implementation where the objects are made callable
by implementing a ``__call__`` method.

On ``__init__`` we just save the ``timeout_limit`` as an attribute.

The ``__call__`` is very similar with the ``run-once`` implementation.
First it defines a function (``save_now``) that is registered
into ``task.value_savers``. Than it compares the current time
with the time that was saved on last successful execution.


Example: result_dep implementation
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The ``result_dep`` is more complicated due to two factors. It needs to modify
the task's ``task_dep``. It needs to check the task's saved values and metadata
from a task different from where it is being applied.

A ``result_dep`` implies that its dependency is also a ``task_dep``.
We have seen that the callable takes a `task` parameter that we used
to modify the task object. The problem is that modifying ``task_dep``
when the callable gets called would be "too late" according to the
way `doit` works. When an object is passed ``uptodate`` and this
object's class has a method named ``configure_task`` it will be called
during the task creation.

The base class ``dependency.UptodateCalculator`` gives access to
an attribute named ``tasks_dict`` containing a dictionary with
all task objects where the ``key`` is the task name (this is used to get all
sub-tasks from a task-group). And also a method called ``get_val`` to access
the saved values and results from any task.


.. code-block:: python

    class result_dep(UptodateCalculator):
        """check if result of the given task was modified
        """
        def __init__(self, dep_task_name):
            self.dep_name = dep_task_name
            self.result_name = '_result:%s' % self.dep_name

        def configure_task(self, task):
            """to be called by doit when create the task"""
            # result_dep creates an implicit task_dep
            task.task_dep.append(self.dep_name)

        def _result_single(self):
            """get result from a single task"""
            return self.get_val(self.dep_name, 'result:')

        def _result_group(self, dep_task):
            """get result from a group task
            the result is the combination of results of all sub-tasks
            """
            prefix = dep_task.name + ":"
            sub_tasks = {}
            for sub in dep_task.task_dep:
                if sub.startswith(prefix):
                    sub_tasks[sub] = self.get_val(sub, 'result:')
            return sub_tasks

        def __call__(self, task, values):
            """return True if result is the same as last run"""
            dep_task = self.tasks_dict[self.dep_name]
            if not dep_task.has_subtask:
                dep_result = self._result_single()
            else:
                dep_result = self._result_group(dep_task)
            task.value_savers.append(lambda: {self.result_name: dep_result})

            last_success = values.get(self.result_name)
            if last_success is None:
                return False
            return (last_success == dep_result)

