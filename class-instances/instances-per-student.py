#!/usr/bin/env python3

import json
import os
import sys

j = json.load(sys.stdin)

course_id = j['course_id']
seats = j['seats']

os.mkdir(course_id)
os.chdir(course_id)


for i, s in enumerate(seats):
    os.umask(0o177)
    with open('student-{}.pem'.format(i), 'w')  as f:
        print(s['key'], file=f)
        print(json.dumps(s, indent=4), file=f)

with open('instances.json', 'w') as f:
    json.dump(j, f, sort_keys=True, indent=4)

print(course_id)
