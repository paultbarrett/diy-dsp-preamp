# pylint: disable=missing-module-docstring
# pylint: disable=missing-class-docstring
# pylint: disable=missing-function-docstring

import time
import threading
import json
import redis
import pymedia_logger

# ---------------------

class RedisHelper():
    def __init__(
            self,
            host,
            port,
            database,
            pubsub_name,
            decode_responses=False,
            ):
        self._log = pymedia_logger.get_logger(__class__.__name__)
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

    def get(self, key, conv=None):
        """Read a json encoded redis key for the default pubsub. """
        return self.get_s(f"{self.pubsub_name}:{key}", conv)

    def get_s(self, key, conv=None):
        """Read a json encoded redis key."""
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

    def set(self, key, value):
        """Set a json encoded redis key for the default pubsub. """
        self.set_s(f"{self.pubsub_name}:{key}", value)

    def set_s(self, key, value):
        """Set a json encoded redis key."""
        try:
            self.redis.set(key, json.dumps(value))
        except redis.exceptions.RedisError as ex:
            self._log.error(ex)
            raise SystemExit from ex

    def t_wait_action(self, func, *args, **kwargs):
        """Create and return a thread to wait_message()."""
        self._log.debug("Creating wait_action thread")
        thread = threading.Thread(target=self.wait_action,
                                  args=(func, *args), kwargs=kwargs)
        thread.daemon = True
        return thread

    def wait_action(self, func, *args, **kwargs):
        """Wait for messages and run user provided function in thread."""
        self._log.debug("Waiting for messages (actions)")
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
                    kwargs["action"] = message["data"].decode()
                    thread = threading.Thread(target=func, args=args,
                                              kwargs=kwargs)
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
        self.set("last_alive", time_now)
        if wait_set:
            for _try in range(wait_set_tries):
                # >= rather than == because another thread may have updated the
                # key meanwhile
                if float(self.get("last_alive")) >= time_now:
                    return
                self._log.debug("%s:last_alive isn't updated yet - try # %d/%d",
                               self.pubsub_name, _try, wait_set_tries)
                time.sleep(0.1)
            raise Exception(
                    f"wait_set=True and {self.pubsub_name}:last_alive isn't"
                    " set to {time_now} after {wait_set_tries} tries")


    def check_timestamp(self, key, max_age=2):
        """Check if the timestamp in key is more recent than max_age sec."""
        tstamp = self.get_s(key)

        if tstamp is None:
            self._log.error("no '%s' key", key)
            return False

        try:
            if time.time() - float(tstamp) < max_age:
                return True
        except TypeError:
            self._log.error("'%s' isn't a float", key)
        else:
            self._log.debug("%s hasn't updated redis in %s seconds",
                          key, max_age)

        return False

    def check_alive(self, pubsub_name, max_age=20):
        """Check if a 'last_alive' key was set less than max_age sec. ago."""
        return self.check_timestamp(f"{pubsub_name}:last_alive", max_age)

    def update_stats(self, stats, send_data_changed_event = False):
        """Update NAME:keys with dictionnary values

        Optionally send a "data changed" event
        """
        for item in stats:
            self.set_s(f"{self.pubsub_name}:{item}", stats[item])
        self.set_s(f"{self.pubsub_name}:last_stats_update", time.time())
        if send_data_changed_event:
            self.publish_event("stats")

    def publish_event(self, event_data="foo"):
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
