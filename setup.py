#!/usr/bin/env python

from distutils.core import setup

setup(name='redundant',
      version='0.1.0',
      description='Project technical debt analysis tool',
      author='Calvin Spealman',
      author_email='calvin@caktusgroup.com',
      url='https://www.github.com/caktus/redundant',
      py_modules=['redundant'],
      scripts=['scripts/redundant'],
)
