#!/usr/bin/env python

import os
from setuptools import setup

os.system("pandoc -o README.txt -f markdown -t rst README.md")

setup(name='charon',
      version='14.8',
      description='Database for IGN projects and samples, with RESTful interface.',
      license='MIT',
      author='Per Kraulis',
      author_email='per.kraulis@scilifelab.se',
      url='https://github.com/NationalGenomicsInfrastructure/charon',
      packages=['charon'],
      package_dir={'charon': 'charon'},
      include_package_data=True,
      install_requires=['tornado>=3.2',
                        'ibmcloudant>=0.10.7',
                        'pyyaml>=3.10',
                        'requests>=2.2'],
     )
