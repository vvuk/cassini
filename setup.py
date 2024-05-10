from setuptools import setup, find_packages

setup(
    name="cassini",
    version="0.0.1",
    install_requires=[
        "alive-progress==3.1.4",
        "scapy==2.5.0",
    ],
    packages=find_packages(),
    entry_points={"console_scripts": ["cassini = cassini.cassini:main"]},
)
