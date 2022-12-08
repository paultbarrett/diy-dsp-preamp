# pylint: disable=missing-module-docstring
# pylint: disable=missing-class-docstring
# pylint: disable=missing-function-docstring

import threading
import time

import pymedia_logger

# ---------------------

class SimpleThreads():
    """Manage (add/start/join) a list of threads."""
    def __init__(self):
        self._log = pymedia_logger.get_logger(__class__.__name__)
        self._threads = []
        self._started = False
        self._joined = False

    def add_target(self, target, *args, **kwargs):
        """Create a thread and add to the list of threads."""
        if self._started:
            self._log.warning("Creating thread but threads were already started")
        new_thread = threading.Thread(target=target, args=args, kwargs=kwargs)
        new_thread.daemon = True
        self._threads.append(new_thread)

    def add_thread(self, thread):
        """Add an existing thread to the list of threads."""
        if self._started:
            self._log.warning("Adding thread but threads were already started")
        thread.daemon = True
        self._threads.append(thread)

    def start(self):
        """Start all threads in the list."""
        for thread in self._threads:
            thread.start()
        self._started = True

    def join(self):
        """Join all threads in the list."""
        for thread in self._threads:
            thread.join()
        self._joined = True


class AutoOff():
    """AutoOff timer."""
    def __init__(
            self,
            func_condrun,
            func_test,
            func_shutdown,
            _redis,
            timeout,
            label="",
            check_interval=30,
            start = True,
            func_condrun_args=(),
            func_test_args=(),
            func_shutdown_args=(),
        ):
        self._log = pymedia_logger.get_logger(__class__.__name__)
        self._func_condrun = func_condrun
        self._func_test = func_test
        self._func_shutdown = func_shutdown
        self._redis = _redis
        self._timeout = timeout
        self._check_interval = check_interval
        self.label = label
        self.run = threading.Thread(target=self._run)
        self._func_condrun_args = func_condrun_args
        self._func_test_args = func_test_args
        self._func_shutdown_args = func_shutdown_args

        if start:
            self.run.daemon = True
            self.run.start()

    # blocking function - should be run in an executor
    def _run(self):
        end_time = None
        prev_state = False
        self._log.debug(
            "setting up auto %s off task. check_interval:%ds timeout:%dm",
            self.label,
            self._check_interval,
            self._timeout,
        )
        self._log.debug(
            " functions: condrun:%s() test:%s() off:%s()",
            self._func_condrun.__name__,
            self._func_test.__name__,
            self._func_shutdown.__name__,
        )
        while True:
            state = self._func_condrun(*self._func_condrun_args)
            if state:
                if self._func_test(*self._func_test_args) or not prev_state:
                    self._log.debug("(re)setting end time (%s)", self.label)
                    end_time = time.monotonic() + self._timeout * 60.0
                elif end_time:
                    if time.monotonic() >= end_time:
                        self._log.info("auto off time after %f minutes (%s)",
                                     self._timeout, self.label)
                        self._func_shutdown(*self._func_shutdown_args)
                        self._redis.publish_event("auto off")
                    else:
                        self._log.debug(
                            "%.1f seconds remaining before auto %s off",
                            end_time - time.monotonic(),
                            self.label,
                        )
            prev_state = state
            time.sleep(self._check_interval)
