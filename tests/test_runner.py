import os
from multiprocessing import Queue
import six

import pytest
from mock import Mock

from doit.dependency import Dependency
from doit.task import Task
from doit.control import TaskDispatcher, ExecNode
from doit import runner


# sample actions
def my_print(*args):
    pass
def _fail():
    return False
def _error():
    raise Exception("I am the exception.\n")
def _exit():
    raise SystemExit()


class FakeReporter(object):
    """Just log everything in internal attribute - used on tests"""
    def __init__(self, outstream=None, options=None):
        self.log = []

    def get_status(self, task):
        self.log.append(('start', task))

    def execute_task(self, task):
        self.log.append(('execute', task))

    def add_failure(self, task, exception):
        self.log.append(('fail', task))

    def add_success(self, task):
        self.log.append(('success', task))

    def skip_uptodate(self, task):
        self.log.append(('up-to-date', task))

    def skip_ignore(self, task):
        self.log.append(('ignore', task))

    def cleanup_error(self, exception):
        self.log.append(('cleanup_error',))

    def runtime_error(self, msg):
        self.log.append(('runtime_error',))

    def teardown_task(self, task):
        self.log.append(('teardown', task))

    def complete_run(self):
        pass


@pytest.fixture
def reporter(request):
    return FakeReporter()


class TestRunner(object):
    def testInit(self, reporter, depfile_name):
        my_runner = runner.Runner(Dependency, depfile_name, reporter)
        assert False == my_runner._stop_running
        assert runner.SUCCESS == my_runner.final_result


class TestRunner_SelectTask(object):
    def test_ready(self, reporter, depfile_name):
        t1 = Task("taskX", [(my_print, ["out a"] )])
        my_runner = runner.Runner(Dependency, depfile_name, reporter)
        assert True == my_runner.select_task(ExecNode(t1, None), {})
        assert ('start', t1) == reporter.log.pop(0)
        assert not reporter.log

    def test_DependencyError(self, reporter, depfile_name):
        t1 = Task("taskX", [(my_print, ["out a"] )],
                  file_dep=["i_dont_exist"])
        my_runner = runner.Runner(Dependency, depfile_name, reporter)
        assert False == my_runner.select_task(ExecNode(t1, None), {})
        assert ('start', t1) == reporter.log.pop(0)
        assert ('fail', t1) == reporter.log.pop(0)
        assert not reporter.log

    def test_upToDate(self, reporter, depfile_name):
        t1 = Task("taskX", [(my_print, ["out a"] )], file_dep=[__file__])
        my_runner = runner.Runner(Dependency, depfile_name, reporter)
        my_runner.dep_manager.save_success(t1)
        assert False == my_runner.select_task(ExecNode(t1, None), {})
        assert ('start', t1) == reporter.log.pop(0)
        assert ('up-to-date', t1) == reporter.log.pop(0)
        assert not reporter.log

    def test_ignore(self, reporter, depfile_name):
        t1 = Task("taskX", [(my_print, ["out a"] )])
        my_runner = runner.Runner(Dependency, depfile_name, reporter)
        my_runner.dep_manager.ignore(t1)
        assert False == my_runner.select_task(ExecNode(t1, None), {})
        assert ('start', t1) == reporter.log.pop(0)
        assert ('ignore', t1) == reporter.log.pop(0)
        assert not reporter.log

    def test_alwaysExecute(self, reporter, depfile_name):
        t1 = Task("taskX", [(my_print, ["out a"] )])
        my_runner = runner.Runner(Dependency, depfile_name, reporter, always_execute=True)
        my_runner.dep_manager.save_success(t1)
        assert True == my_runner.select_task(ExecNode(t1, None), {})
        assert ('start', t1) == reporter.log.pop(0)
        assert not reporter.log

    def test_noSetup_ok(self, reporter, depfile_name):
        t1 = Task("taskX", [(my_print, ["out a"] )])
        my_runner = runner.Runner(Dependency, depfile_name, reporter)
        assert True == my_runner.select_task(ExecNode(t1, None), {})
        assert ('start', t1) == reporter.log.pop(0)
        assert not reporter.log

    def test_withSetup(self, reporter, depfile_name):
        t1 = Task("taskX", [(my_print, ["out a"] )], setup=["taskY"])
        my_runner = runner.Runner(Dependency, depfile_name, reporter)
        # defer execution
        n1 = ExecNode(t1, None)
        assert False == my_runner.select_task(n1, {})
        assert ('start', t1) == reporter.log.pop(0)
        assert not reporter.log
        # trying to select again
        assert True == my_runner.select_task(n1, {})
        assert not reporter.log


    def test_getargs_ok(self, reporter, depfile_name):
        def ok(): return {'x':1}
        def check_x(my_x): return my_x == 1
        t1 = Task('t1', [(ok,)])
        n1 = ExecNode(t1, None)
        t2 = Task('t2', [(check_x,)], getargs={'my_x':('t1','x')})
        n2 = ExecNode(t2, None)
        tasks_dict = {'t1': t1, 't2':t2}
        my_runner = runner.Runner(Dependency, depfile_name, reporter)

        # t2 gives chance for setup tasks to be executed
        assert False == my_runner.select_task(n2, tasks_dict)
        assert ('start', t2) == reporter.log.pop(0)

        # execute task t1 to calculate value
        assert True == my_runner.select_task(n1, tasks_dict)
        assert ('start', t1) == reporter.log.pop(0)
        t1_result = my_runner.execute_task(t1)
        assert ('execute', t1) == reporter.log.pop(0)
        my_runner.process_task_result(n1, t1_result)
        assert ('success', t1) == reporter.log.pop(0)

        # t2.options are set on select_task
        assert {} == t2.options
        assert True == my_runner.select_task(n2, tasks_dict)
        assert not reporter.log
        assert {'my_x': 1} == t2.options

    def test_getargs_fail(self, reporter, depfile_name):
        # invalid getargs. Exception wil be raised and task will fail
        def check_x(my_x): return True
        t1 = Task('t1', [lambda :True])
        n1 = ExecNode(t1, None)
        t2 = Task('t2', [(check_x,)], getargs={'my_x':('t1','x')})
        n2 = ExecNode(t2, None)
        tasks_dict = {'t1': t1, 't2':t2}
        my_runner = runner.Runner(Dependency, depfile_name, reporter)

        # t2 gives chance for setup tasks to be executed
        assert False == my_runner.select_task(n2, tasks_dict)
        assert ('start', t2) == reporter.log.pop(0)

        # execute task t1 to calculate value
        assert True == my_runner.select_task(n1, tasks_dict)
        assert ('start', t1) == reporter.log.pop(0)
        t1_result = my_runner.execute_task(t1)
        assert ('execute', t1) == reporter.log.pop(0)
        my_runner.process_task_result(n1, t1_result)
        assert ('success', t1) == reporter.log.pop(0)

        # select_task t2 fails
        assert False == my_runner.select_task(n2, tasks_dict)
        assert ('fail', t2) == reporter.log.pop(0)
        assert not reporter.log


    def test_getargs_dict(self, reporter, depfile_name):
        def ok(): return {'x':1}
        t1 = Task('t1', [(ok,)])
        n1 = ExecNode(t1, None)
        t2 = Task('t2', None, getargs={'my_x':('t1', None)})
        tasks_dict = {'t1': t1, 't2':t2}
        my_runner = runner.Runner(Dependency, depfile_name, reporter)
        t1_result = my_runner.execute_task(t1)
        my_runner.process_task_result(n1, t1_result)

        # t2.options are set on _get_task_args
        assert {} == t2.options
        my_runner._get_task_args(t2, tasks_dict)
        assert {'my_x': {'x':1}} == t2.options


    def test_getargs_group(self, reporter, depfile_name):
        def ok(): return {'x':1}
        t1 = Task('t1', None, task_dep=['t1:a'], has_subtask=True)
        t1a = Task('t1:a', [(ok,)], is_subtask=True)
        t2 = Task('t2', None, getargs={'my_x':('t1', None)})
        tasks_dict = {'t1': t1, 't1a':t1a, 't2':t2}
        my_runner = runner.Runner(Dependency, depfile_name, reporter)
        t1a_result = my_runner.execute_task(t1a)
        my_runner.process_task_result(ExecNode(t1a, None), t1a_result)

        # t2.options are set on _get_task_args
        assert {} == t2.options
        my_runner._get_task_args(t2, tasks_dict)
        assert {'my_x': {'a':{'x':1}} } == t2.options



    def test_getargs_group_value(self, reporter, depfile_name):
        def ok(): return {'x':1}
        t1 = Task('t1', None, task_dep=['t1:a'], has_subtask=True)
        t1a = Task('t1:a', [(ok,)], is_subtask=True)
        t2 = Task('t2', None, getargs={'my_x':('t1', 'x')})
        tasks_dict = {'t1': t1, 't1a':t1a, 't2':t2}
        my_runner = runner.Runner(Dependency, depfile_name, reporter)
        t1a_result = my_runner.execute_task(t1a)
        my_runner.process_task_result(ExecNode(t1a, None), t1a_result)

        # t2.options are set on _get_task_args
        assert {} == t2.options
        my_runner._get_task_args(t2, tasks_dict)
        assert {'my_x': {'a':1} } == t2.options



class TestTask_Teardown(object):
    def test_ok(self, reporter, depfile_name):
        touched = []
        def touch():
            touched.append(1)
        t1 = Task('t1', [], teardown=[(touch,)])
        my_runner = runner.Runner(Dependency, depfile_name, reporter)
        my_runner.teardown_list = [t1]
        my_runner.teardown()
        assert 1 == len(touched)
        assert ('teardown', t1) == reporter.log.pop(0)
        assert not reporter.log

    def test_reverse_order(self, reporter, depfile_name):
        def do_nothing():pass
        t1 = Task('t1', [], teardown=[do_nothing])
        t2 = Task('t2', [], teardown=[do_nothing])
        my_runner = runner.Runner(Dependency, depfile_name, reporter)
        my_runner.teardown_list = [t1, t2]
        my_runner.teardown()
        assert ('teardown', t2) == reporter.log.pop(0)
        assert ('teardown', t1) == reporter.log.pop(0)
        assert not reporter.log

    def test_errors(self, reporter, depfile_name):
        def raise_something(x):
            raise Exception(x)
        t1 = Task('t1', [], teardown=[(raise_something,['t1 blow'])])
        t2 = Task('t2', [], teardown=[(raise_something,['t2 blow'])])
        my_runner = runner.Runner(Dependency, depfile_name, reporter)
        my_runner.teardown_list = [t1, t2]
        my_runner.teardown()
        assert ('teardown', t2) == reporter.log.pop(0)
        assert ('cleanup_error',) == reporter.log.pop(0)
        assert ('teardown', t1) == reporter.log.pop(0)
        assert ('cleanup_error',) == reporter.log.pop(0)
        assert not reporter.log


class TestTask_RunAll(object):
    def test_reporter_runtime_error(self, reporter, depfile_name):
        t1 = Task('t1', [], calc_dep=['t2'])
        t2 = Task('t2', [lambda: {'file_dep':[1]}])
        my_runner = runner.Runner(Dependency, depfile_name, reporter)
        my_runner.run_all(TaskDispatcher({'t1':t1, 't2':t2}, [], ['t1', 't2']))
        assert ('start', t2) == reporter.log.pop(0)
        assert ('execute', t2) == reporter.log.pop(0)
        assert ('success', t2) == reporter.log.pop(0)
        assert ('runtime_error',) == reporter.log.pop(0)
        assert not reporter.log


# run tests in both single process runner and multi-process runner
RUNNERS = [runner.Runner, runner.MThreadRunner]
# TODO: test should be added and skipped!
if runner.MRunner.available():
    RUNNERS.append(runner.MRunner)
@pytest.fixture(params=RUNNERS)
def RunnerClass(request):
    return request.param


def ok(): return "ok"
def ok2(): return "different"

class TestRunner_run_tasks(object):

    def test_teardown(self, reporter, RunnerClass, depfile_name):
        t1 = Task('t1', [], teardown=[ok])
        t2 = Task('t2', [])
        my_runner = RunnerClass(Dependency, depfile_name, reporter)
        assert [] == my_runner.teardown_list
        my_runner.run_tasks(TaskDispatcher({'t1':t1, 't2':t2}, [], ['t1', 't2']))
        my_runner.finish()
        assert ('teardown', t1) == reporter.log[-1]

    # testing whole process/API
    def test_success(self, reporter, RunnerClass, depfile_name):
        t1 = Task("t1", [(my_print, ["out a"] )] )
        t2 = Task("t2", [(my_print, ["out a"] )] )
        my_runner = RunnerClass(Dependency, depfile_name, reporter)
        my_runner.run_tasks(TaskDispatcher({'t1':t1, 't2':t2}, [], ['t1', 't2']))
        assert runner.SUCCESS == my_runner.finish()
        assert ('start', t1) == reporter.log.pop(0), reporter.log
        assert ('execute', t1) == reporter.log.pop(0)
        assert ('success', t1) == reporter.log.pop(0)
        assert ('start', t2) == reporter.log.pop(0)
        assert ('execute', t2) == reporter.log.pop(0)
        assert ('success', t2) == reporter.log.pop(0)

    # test result, value, out, err are saved into task
    def test_result(self, reporter, RunnerClass, depfile_name):
        def my_action():
            import sys
            sys.stdout.write('out here')
            sys.stderr.write('err here')
            return {'bb': 5}
        task = Task("taskY", [my_action] )
        my_runner = RunnerClass(Dependency, depfile_name, reporter)
        assert None == task.result
        assert {} == task.values
        assert [None] == [a.out for a in task.actions]
        assert [None] == [a.err for a in task.actions]
        my_runner.run_tasks(TaskDispatcher({'taskY':task}, [], ['taskY']))
        assert runner.SUCCESS == my_runner.finish()
        assert {'bb': 5} == task.result
        assert {'bb': 5} == task.values
        assert ['out here'] == [a.out for a in task.actions]
        assert ['err here'] == [a.err for a in task.actions]

    # whenever a task fails remaining task are not executed
    def test_failureOutput(self, reporter, RunnerClass, depfile_name):
        t1 = Task("t1", [_fail])
        t2 = Task("t2", [_fail])
        my_runner = RunnerClass(Dependency, depfile_name, reporter)
        my_runner.run_tasks(TaskDispatcher({'t1':t1, 't2':t2}, [], ['t1', 't2']))
        assert runner.FAILURE == my_runner.finish()
        assert ('start', t1) == reporter.log.pop(0)
        assert ('execute', t1) == reporter.log.pop(0)
        assert ('fail', t1) == reporter.log.pop(0)
        # second task is not executed
        assert 0 == len(reporter.log)


    def test_error(self, reporter, RunnerClass, depfile_name):
        t1 = Task("t1", [_error])
        t2 = Task("t2", [_error])
        my_runner = RunnerClass(Dependency, depfile_name, reporter)
        my_runner.run_tasks(TaskDispatcher({'t1':t1, 't2':t2}, [], ['t1', 't2']))
        assert runner.ERROR == my_runner.finish()
        assert ('start', t1) == reporter.log.pop(0)
        assert ('execute', t1) == reporter.log.pop(0)
        assert ('fail', t1) == reporter.log.pop(0)
        # second task is not executed
        assert 0 == len(reporter.log)


    # when successful dependencies are updated
    def test_updateDependencies(self, reporter, RunnerClass, depfile_name):
        depPath = os.path.join(os.path.dirname(__file__),"data/dependency1")
        ff = open(depPath,"a")
        ff.write("xxx")
        ff.close()
        dependencies = [depPath]

        filePath = os.path.join(os.path.dirname(__file__),"data/target")
        ff = open(filePath,"a")
        ff.write("xxx")
        ff.close()
        targets = [filePath]

        t1 = Task("t1", [my_print], dependencies, targets)
        my_runner = RunnerClass(Dependency, depfile_name, reporter)
        my_runner.run_tasks(TaskDispatcher({'t1':t1}, [], ['t1']))
        assert runner.SUCCESS == my_runner.finish()
        d = Dependency(depfile_name)
        assert d._get("t1", os.path.abspath(depPath))


    def test_continue(self, reporter, RunnerClass, depfile_name):
        t1 = Task("t1", [(_fail,)] )
        t2 = Task("t2", [(_error,)] )
        t3 = Task("t3", [(ok,)])
        my_runner = RunnerClass(Dependency, depfile_name, reporter, continue_=True)
        disp = TaskDispatcher({'t1':t1, 't2':t2, 't3':t3}, [], ['t1', 't2', 't3'])
        my_runner.run_tasks(disp)
        assert runner.ERROR == my_runner.finish()
        assert ('start', t1) == reporter.log.pop(0)
        assert ('execute', t1) == reporter.log.pop(0)
        assert ('fail', t1) == reporter.log.pop(0)
        assert ('start', t2) == reporter.log.pop(0)
        assert ('execute', t2) == reporter.log.pop(0)
        assert ('fail', t2) == reporter.log.pop(0)
        assert ('start', t3) == reporter.log.pop(0)
        assert ('execute', t3) == reporter.log.pop(0)
        assert ('success', t3) == reporter.log.pop(0)
        assert 0 == len(reporter.log)


    def test_continue_dont_execute_parent_of_failed_task(self, reporter,
                                                         RunnerClass, depfile_name):
        t1 = Task("t1", [(_error,)] )
        t2 = Task("t2", [(ok,)], task_dep=['t1'])
        t3 = Task("t3", [(ok,)])
        my_runner = RunnerClass(Dependency, depfile_name, reporter, continue_=True)
        disp = TaskDispatcher({'t1':t1, 't2':t2, 't3':t3}, [], ['t1', 't2', 't3'])
        my_runner.run_tasks(disp)
        assert runner.ERROR == my_runner.finish()
        assert ('start', t1) == reporter.log.pop(0)
        assert ('execute', t1) == reporter.log.pop(0)
        assert ('fail', t1) == reporter.log.pop(0)
        assert ('start', t2) == reporter.log.pop(0)
        assert ('fail', t2) == reporter.log.pop(0)
        assert ('start', t3) == reporter.log.pop(0)
        assert ('execute', t3) == reporter.log.pop(0)
        assert ('success', t3) == reporter.log.pop(0)
        assert 0 == len(reporter.log)


    def test_continue_dep_error(self, reporter, RunnerClass, depfile_name):
        t1 = Task("t1", [(ok,)], file_dep=['i_dont_exist'] )
        t2 = Task("t2", [(ok,)], task_dep=['t1'])
        my_runner = RunnerClass(Dependency, depfile_name, reporter, continue_=True)
        disp = TaskDispatcher({'t1':t1, 't2':t2}, [], ['t1', 't2'])
        my_runner.run_tasks(disp)
        assert runner.ERROR == my_runner.finish()
        assert ('start', t1) == reporter.log.pop(0)
        assert ('fail', t1) == reporter.log.pop(0)
        assert ('start', t2) == reporter.log.pop(0)
        assert ('fail', t2) == reporter.log.pop(0)
        assert 0 == len(reporter.log)


    def test_continue_ignored_dep(self, reporter, RunnerClass, depfile_name):
        t1 = Task("t1", [(ok,)], )
        t2 = Task("t2", [(ok,)], task_dep=['t1'])
        my_runner = RunnerClass(Dependency, depfile_name, reporter, continue_=True)
        my_runner.dep_manager.ignore(t1)
        disp = TaskDispatcher({'t1':t1, 't2':t2}, [], ['t1', 't2'])
        my_runner.run_tasks(disp)
        assert runner.SUCCESS == my_runner.finish()
        assert ('start', t1) == reporter.log.pop(0)
        assert ('ignore', t1) == reporter.log.pop(0)
        assert ('start', t2) == reporter.log.pop(0)
        assert ('ignore', t2) == reporter.log.pop(0)
        assert 0 == len(reporter.log)


    def test_getargs(self, reporter, RunnerClass, depfile_name):
        def use_args(arg1):
            six.print_(arg1)
        def make_args(): return {'myarg':1}
        t1 = Task("t1", [(use_args,)], getargs=dict(arg1=('t2','myarg')) )
        t2 = Task("t2", [(make_args,)])
        my_runner = RunnerClass(Dependency, depfile_name, reporter)
        my_runner.run_tasks(TaskDispatcher({'t1':t1, 't2':t2}, [], ['t1', 't2']))
        assert runner.SUCCESS == my_runner.finish()
        assert ('start', t1) == reporter.log.pop(0)
        assert ('start', t2) == reporter.log.pop(0)
        assert ('execute', t2) == reporter.log.pop(0)
        assert ('success', t2) == reporter.log.pop(0)
        assert ('execute', t1) == reporter.log.pop(0)
        assert ('success', t1) == reporter.log.pop(0)
        assert 0 == len(reporter.log)


    # SystemExit runner should not interfere with SystemExit
    def testSystemExitRaises(self, reporter, RunnerClass, depfile_name):
        t1 = Task("t1", [_exit])
        my_runner = RunnerClass(Dependency, depfile_name, reporter)
        disp = TaskDispatcher({'t1':t1}, [], ['t1'])
        pytest.raises(SystemExit, my_runner.run_tasks, disp)
        my_runner.finish()


@pytest.mark.skipif('not runner.MRunner.available()')
class TestMReporter(object):
    class MyRunner(object):
        def __init__(self):
            self.result_q = Queue()

    def testReporterMethod(self, reporter):
        fake_runner = self.MyRunner()
        mp_reporter = runner.MReporter(fake_runner, reporter)
        my_task = Task("task x", [])
        mp_reporter.add_success(my_task)
        # note limit is 2 seconds because of http://bugs.python.org/issue17707
        got = fake_runner.result_q.get(True, 2)
        assert {'name': "task x", "reporter": 'add_success'} == got

    def testNonReporterMethod(self, reporter):
        fake_runner = self.MyRunner()
        mp_reporter = runner.MReporter(fake_runner, reporter)
        assert hasattr(mp_reporter, 'add_success')
        assert not hasattr(mp_reporter, 'no_existent_method')


@pytest.mark.skipif('not runner.MRunner.available()')
class TestMRunner_get_next_task(object):
    # simple normal case
    def test_run_task(self, reporter, depfile_name):
        t1 = Task('t1', [])
        t2 = Task('t2', [])
        run = runner.MRunner(Dependency, depfile_name, reporter)
        run._run_tasks_init(TaskDispatcher({'t1':t1, 't2':t2}, [], ['t1', 't2']))
        assert t1 == run.get_next_task(None).task
        assert t2 == run.get_next_task(None).task
        assert None == run.get_next_task(None)

    def test_stop_running(self, reporter, depfile_name):
        t1 = Task('t1', [])
        t2 = Task('t2', [])
        run = runner.MRunner(Dependency, depfile_name, reporter)
        run._run_tasks_init(TaskDispatcher({'t1':t1, 't2':t2}, [], ['t1', 't2']))
        assert t1 == run.get_next_task(None).task
        run._stop_running = True
        assert None == run.get_next_task(None)

    def test_waiting(self, reporter, depfile_name):
        t1 = Task('t1', [])
        t2 = Task('t2', [], setup=('t1',))
        run = runner.MRunner(Dependency, depfile_name, reporter)
        run._run_tasks_init(TaskDispatcher({'t1':t1, 't2':t2}, [], ['t2']))

        # first start task 1
        n1 = run.get_next_task(None)
        assert t1 == n1.task

        # hold until t1 is done
        assert isinstance(run.get_next_task(None), runner.Hold)
        assert isinstance(run.get_next_task(None), runner.Hold)
        n1.run_status = 'done'

        n2 = run.get_next_task(n1)
        assert t2 == n2.task
        assert None == run.get_next_task(n2)


    def test_waiting_controller(self, reporter, depfile_name):
        t1 = Task('t1', [])
        t2 = Task('t2', [], calc_dep=('t1',))
        run = runner.MRunner(Dependency, depfile_name, reporter)
        run._run_tasks_init(TaskDispatcher({'t1':t1, 't2':t2}, [], ['t1', 't2']))

        # first task ok
        assert t1 == run.get_next_task(None).task

        # hold until t1 finishes
        assert 0 == run.free_proc
        assert isinstance(run.get_next_task(None), runner.Hold)
        assert 1 == run.free_proc



@pytest.mark.skipif('not runner.MRunner.available()')
class TestMRunner_start_process(object):
    # 2 process, 3 tasks
    def test_all_processes(self, reporter, monkeypatch, depfile_name):
        mock_process = Mock()
        monkeypatch.setattr(runner.MRunner, 'Child', mock_process)
        t1 = Task('t1', [])
        t2 = Task('t2', [])
        td = TaskDispatcher({'t1':t1, 't2':t2}, [], ['t1', 't2'])
        run = runner.MRunner(Dependency, depfile_name, reporter, num_process=2)
        run._run_tasks_init(td)
        result_q = Queue()
        task_q = Queue()

        proc_list = run._run_start_processes(task_q, result_q)
        run.finish()
        assert 2 == len(proc_list)
        assert t1.name == task_q.get().name
        assert t2.name == task_q.get().name


    # 2 process, 1 task
    def test_less_processes(self, reporter, monkeypatch, depfile_name):
        mock_process = Mock()
        monkeypatch.setattr(runner.MRunner, 'Child', mock_process)
        t1 = Task('t1', [])
        td = TaskDispatcher({'t1':t1}, [], ['t1'])
        run = runner.MRunner(Dependency, depfile_name, reporter, num_process=2)
        run._run_tasks_init(td)
        result_q = Queue()
        task_q = Queue()

        proc_list = run._run_start_processes(task_q, result_q)
        run.finish()
        assert 1 == len(proc_list)
        assert t1.name == task_q.get().name


    # 2 process, 2 tasks (but only one task can be started)
    def test_waiting_process(self, reporter, monkeypatch, depfile_name):
        mock_process = Mock()
        monkeypatch.setattr(runner.MRunner, 'Child', mock_process)
        t1 = Task('t1', [])
        t2 = Task('t2', [], task_dep=['t1'])
        td = TaskDispatcher({'t1':t1, 't2':t2}, [], ['t1', 't2'])
        run = runner.MRunner(Dependency, depfile_name, reporter, num_process=2)
        run._run_tasks_init(td)
        result_q = Queue()
        task_q = Queue()

        proc_list = run._run_start_processes(task_q, result_q)
        run.finish()
        assert 2 == len(proc_list)
        assert t1.name == task_q.get().name
        assert isinstance(task_q.get(), runner.Hold)


@pytest.mark.skipif('not runner.MRunner.available()')
class TestMRunner_execute_task(object):
    def test_hold(self, reporter, depfile_name):
        run = runner.MRunner(Dependency, depfile_name, reporter)
        task_q = Queue()
        task_q.put(runner.Hold()) # to test
        task_q.put(None) # to terminate function
        result_q = Queue()
        run.execute_task_subprocess(task_q, result_q)
        run.finish()
        # nothing was done
        assert result_q.empty() # pragma: no cover (coverage bug?)


def test_MThreadRunner_available():
    assert runner.MThreadRunner.available() == True
