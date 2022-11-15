#!/usr/bin/python3

import redis

r = redis.Redis("localhost", 6379)
r.publish("CDSP", "EVENT")

