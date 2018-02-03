#!/usr/bin/env python
import sys

from setuptools import setup


def forbid_publish():
    # no accidentally publishing experimental projects
    argv = sys.argv
    blacklist = ['register', 'upload']

    for command in blacklist:
        if command in argv:
            values = {'command': command}
            print('Command "%(command)s" has been blacklisted, exiting...' %
                  values)
            sys.exit(2)


forbid_publish()

setup(
    setup_requires=['pbr'],
    pbr=True,
)
