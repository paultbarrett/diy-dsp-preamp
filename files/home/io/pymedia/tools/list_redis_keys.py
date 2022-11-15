#!/usr/bin/python3

import json
import redis

r = redis.Redis("localhost", 6379)
for key in sorted(r.scan_iter()):
    try:
        val = json.loads(r.get(key))
        print("{0:<40} {1}".format(str(key), val))
    except ValueError:
        val = ""
