# pylint: disable=missing-module-docstring
# pylint: disable=missing-class-docstring
# pylint: disable=missing-function-docstring

import logging
import os

_LOG_FORMAT = ("[%(levelname)s] %(name)s:"
               "%(funcName)s(%(lineno)d) %(custom)s %(message)s")

_LOG_DATE_FORMAT = "%H:%M:%S"

_LOG_LEVEL = os.environ.get("LOGLEVEL", "INFO").upper()

# add timestamp if not called from systemd (see pymedia@.service)
if 'FROM_SYSTEMD' not in os.environ and os.environ.get('FROM_SYSTEMD') != "1":
    _LOG_FORMAT = f"%(asctime)s,%(msecs)d %(filename)s {_LOG_FORMAT}"

#logging.basicConfig(
#    level=_LOG_LEVEL,
#    format=_LOG_FORMAT,
#    datefmt=_date_format,
#)

def get_file_handler():
    file_handler = logging.FileHandler("x.log")
    file_handler.setLevel(logging.WARNING)
    file_handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    return file_handler

def get_stream_handler():
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(_LOG_LEVEL)
    stream_handler.setFormatter(logging.Formatter(_LOG_FORMAT,
                                                  datefmt=_LOG_DATE_FORMAT))
    return stream_handler

def get_logger(name, custom_field=""):
    logger = logging.getLogger(name)
    logger.setLevel(_LOG_LEVEL)
    #logger.addHandler(get_file_handler())
    logger.addHandler(get_stream_handler())
    logger = logging.LoggerAdapter(logger, {"custom": custom_field})
    return logger
