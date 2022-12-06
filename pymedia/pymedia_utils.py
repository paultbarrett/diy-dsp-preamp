# pylint: disable=missing-module-docstring
# pylint: disable=missing-class-docstring
# pylint: disable=missing-function-docstring

import logging
import threading
import os

# ---------------------

# Logging
LOGFORMAT = "%(levelname)s %(name)s %(funcName)s() %(message)s"

# add timestamp if not called from systemd (see pymedia@.service)
if 'FROM_SYSTEMD' not in os.environ and os.environ.get('FROM_SYSTEMD') != "1":
    LOGFORMAT = f"%(asctime)s,%(msecs)d {LOGFORMAT}"

logging.basicConfig(
        level=os.environ.get('LOGLEVEL', 'INFO').upper(),
        format=LOGFORMAT,
        datefmt="%H:%M:%S"
        )

# https://stackoverflow.com/questions/29069655/python-logging-with-a-common-logger-class-mixin-and-class-inheritance
class Log(type):
    """Logging metaclass.
    Name mangling ensures each class uses its own logger.
    Logger name derived accounting for inheritance for the bonus marks

    The logger for each class is created at class definition and accessed via a
    direct attribute reference, avoiding a getLogger() call.
    """
    def __init__(cls, *args):
        super().__init__(*args)
        logger_attribute_name = '_' + cls.__name__ + '__logger'
        logger_name = '.'.join([c.__name__ for c in cls.mro()[-2::-1]])
        setattr(cls, logger_attribute_name, logging.getLogger(logger_name))


class SimpleThreads():
    """Manage (add/start/join) a list of threads."""
    def __init__(self):
        self._log = logging.getLogger(self.__class__.__name__)
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
