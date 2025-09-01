# setup.py 

from setuptools import setup, find_packages

setup(
    name="cobra-router",
    version="0.42.1.0",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        "construct",
        "solana",
        "solders",
        "requests",
        "asyncio",
        "aiohttp",
        "httpx",
        "base58",
        "readchar",
        "dotenv",
        "python-telegram-bot",
        "asyncpg"
    ],
    author="FLOCK4H",
    description="Cobra Router",
    url="https://github.com/FLOCK4H/Cobra",
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.7",
)