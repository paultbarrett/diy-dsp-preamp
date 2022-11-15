# pylint: disable=missing-module-docstring
# pylint: disable=missing-class-docstring
# pylint: disable=missing-function-docstring

import logging
import time
import os
import threading

import dataclasses

# redis
import json
import redis

from const import REDIS_SERVER, REDIS_PORT, REDIS_DB


# ---------------------

RUNNING = True

# ---------------------

HOMEDIR = os.environ.get('HOME')

# Logging
LOGFORMAT = "%(levelname)s %(name)s %(funcName)s() %(message)s"
# add timestamp if not called from systemd (see pymedia@.service)
if 'FROM_SYSTEMD' not in os.environ and os.environ.get('FROM_SYSTEMD') != "1":
    LOGFORMAT = f"%(asctime)s,%(msecs)d {LOGFORMAT}"
LOGLEVEL = os.environ.get('LOGLEVEL', 'INFO').upper()
logging.basicConfig(
    level=LOGLEVEL,
    format=LOGFORMAT,
    datefmt="%H:%M:%S",
)

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

@dataclasses.dataclass
class ConnParam:
    """Simple class holding server/port connection parameters."""
    server: str
    port: int

class RedisHelper():
    def __init__(
            self,
            pubsub_name,
            host=REDIS_SERVER,
            port=REDIS_PORT,
            database=REDIS_DB,
            decode_responses=False,
            ):
        self._log = logging.getLogger(f"{pubsub_name}:{self.__class__.__name__}")
        self.redis = redis.Redis(host=host, port=port, db=database,
                                 decode_responses=decode_responses)
        self.pubsub_name = pubsub_name
        self.pubsub_action_name = f"{pubsub_name}:ACTION"
        self.pubsub_event_name = f"{pubsub_name}:EVENT"

        try:
            self.redis.ping()
        except (redis.exceptions.ConnectionError, ConnectionRefusedError) as ex:
            self._log.error(ex)
            raise SystemExit from ex

    def get_s(self, key, conv=None):
        """ Read a json encoded redis key."""
        try:
            val = json.loads(self.redis.get(key))
        except (ValueError, TypeError):
            val = None
        except redis.exceptions.RedisError as ex:
            self._log.error(ex)
            raise SystemExit from ex
        if conv == "string":
            return '' if val is None else str(val)
        return val

    def set_s(self, key, value):
        """Set a json encoded redis key."""
        try:
            self.redis.set(key, json.dumps(value))
        except redis.exceptions.RedisError as ex:
            self._log.error(ex)
            raise SystemExit from ex

    def t_wait_action(self, func_process):
        """Create and return a thread to wait_message()."""
        thread = threading.Thread(target=self.wait_action,
                                  args=(func_process,))
        thread.daemon = True
        return thread

    def wait_action(self, func_process):
        """Wait for messages and run user provided function in thread."""
        try:
            pubsub = self.redis.pubsub(ignore_subscribe_messages=True)
            pubsub.subscribe(self.pubsub_action_name)
        except redis.exceptions.RedisError as ex:
            self._log.error("Could not subscribe to %s: %s",
                           self.pubsub_action_name, ex)
            raise SystemExit from ex
        try:
            while True:
                message = pubsub.get_message(timeout=1)
                if message:
                    self._log.debug("received message '%s' ; action is '%s'",
                                  message, message["data"].decode())
                    thread = threading.Thread(target=func_process,
                        args=(message["data"].decode(),))
                    thread.start()
        except KeyboardInterrupt:
            return

    def set_alive(self, wait_set = True, wait_set_tries = 4):
        """Set NAME:last_alive redis key

        Various scripts/functions make use of that key to find out if one of the
        scripts has updated redis recently (ie. is alive).

        With wait_set = True, the function could be blocking for max.
        wait_set_tries * 0.1s
        """
        time_now = time.time()
        self.set_s(f"{self.pubsub_name}:last_alive", time_now)
        if wait_set:
            for _try in range(wait_set_tries):
                if self.get_s(f"{self.pubsub_name}:last_alive") == time_now:
                    return
                self._log.debug("%s:last_alive isn't updated yet - try # %d/%d",
                               self.pubsub_name, _try, wait_set_tries)
                time.sleep(0.1)
            raise Exception(
                    f"wait_set=True and {self.pubsub_name}:last_alive isn't",
                    f" set to {time_now} after {wait_set_tries} tries")

    def update_stats(self, stats, send_data_changed_event = False):
        """Update NAME:keys with dictionnary values

        Optionally send a "data changed" event
        """
        for item in stats:
            self.set_s(f"{self.pubsub_name}:{item}", stats[item])
        self.set_s(f"{self.pubsub_name}:last_stats_update", time.time())
        if send_data_changed_event:
            self.publish_event("stats")

    def publish_event(self, event_data):
        """Publish (send) an event."""
        self._log.debug("publishing event '%s:%s'", self.pubsub_event_name,
                      event_data)
        try:
            self.redis.publish(self.pubsub_event_name, event_data)
        except redis.exceptions.RedisError as ex:
            self._log.error("Could not publish event '%s:%s': %s",
                           self.pubsub_event_name, event_data, ex)
            raise SystemExit from ex

    def send_action(self, dest, action):
        """Publish (send) an action."""
        pubsub_action_name = f"{dest}:ACTION"
        self._log.debug("publishing (sending) action '%s:%s'",
                       pubsub_action_name, action)
        try:
            self.redis.publish(pubsub_action_name, action)
        except redis.exceptions.RedisError as ex:
            self._log.error("Could not send action '%s:%s': %s",
                           pubsub_action_name, action, ex)
            raise SystemExit from ex


def cdsp_ping(redis_r, max_age=20):
    if not bool(redis_r.get_s("CDSP:is_on")):
        logging.debug("Cdsp isn't running")
        return False
    cdsp_last_alive = redis_r.get_s("CDSP:last_alive")
    if cdsp_last_alive is None:
        logging.error("no 'CDSP:last_alive' key")
        return False

    try:
        if time.time() - float(cdsp_last_alive) > max_age:
            logging.debug("Cdsp hasn't updated redis in %s seconds", max_age)
            return False
    except TypeError:
        logging.error("cdsp_last_alive isn't a float")
        return False

    return True
