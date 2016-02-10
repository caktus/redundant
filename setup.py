#!/usr/bin/env python

from distutils.core import setup

setup(name='redundant',
      version='0.1.1',
      description='Project technical debt analysis tool',
      author='Calvin Spealman',
      author_email='calvin@caktusgroup.com',
      url='https://www.github.com/caktus/redundant',
      packages=['redundant'],
      scripts=['scripts/redundant'],
      long_description=open('README.md').read(),
)
