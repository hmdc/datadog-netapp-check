from setuptools import setup

setup(
    name='datadog-netapp-check',
    version='1.0',
    packages=[''],
    url='https://github.com/hmdc/datadog-netapp-check',
    license='MIT',
    author='Evan Sarmiento',
    author_email='evansarm@hmdc.harvard.edu',
    description='DataDog check for ONTAP',
    data_files=[('/etc/dd-agent/checks.d', 'netapp.py')]
)
