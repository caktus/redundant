#!/usr/bin/env python

from distutils.core import setup
import os

long_description = open(os.path.join(os.path.dirname(__file__), 'README.rst')).read()

setup(name='redundant',
      version='0.1.2',
      description='Project technical debt analysis tool',
      author='Calvin Spealman',
      author_email='calvin@caktusgroup.com',
      url='https://www.github.com/caktus/redundant',
      packages=['redundant'],
      scripts=['scripts/redundant'],
      long_description=long_description,
)
