#!/usr/bin/env python

from distutils.core import setup

setup(name='debtcollector',
      version='0.1.0',
      description='Project technical debt analysis tool',
      author='Calvin Spealman',
      author_email='calvin@caktusgroup.com',
      url='https://www.github.com/caktus/debtcollector',
      my_modules=['debtcollector'],
      scripts=['scripts/debtcollector'],
)
