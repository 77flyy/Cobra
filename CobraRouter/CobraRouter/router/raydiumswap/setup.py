# setup.py 

from setuptools import setup, find_packages

setup(
    name="raydiumswap",
    version="1.0.0",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        "construct",
        "solana",
        "solders",
        "requests",
        "asyncio",
    ],
    author="FLOCK4H for Sorin",
    description="Raydium Program Transactions Library",
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.7",
)