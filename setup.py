#!/usr/bin/env python
"""
Setup script for Jarvis OS
Install: pip install -e .
"""

from setuptools import setup, find_packages

setup(
    name="jarvis-os",
    version="1.0.0",
    packages=find_packages(),
    install_requires=[
        "requests>=2.28.0",
        "psutil>=5.9.0",
        "numpy>=1.21.0",
        "sounddevice>=0.4.5",
        "librosa>=0.10.0",
        "scipy>=1.7.0",
        "python-dotenv>=0.19.0",
        "pydantic>=1.9.0",
    ],
    extras_require={
        "cloud": [
            "google-cloud-speech>=2.20.0",
            "google-cloud-texttospeech>=2.14.0",
        ],
        "vision": [
            "opencv-python>=4.5.0",
            "pillow>=9.0.0",
        ],
        "ml": [
            "scikit-learn>=1.0.0",
            "torch>=1.10.0",
        ],
        "dev": [
            "pytest>=7.0.0",
            "pytest-cov>=3.0.0",
            "black>=22.0.0",
            "flake8>=4.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "jarvis=jarvis.cli:main",
            "jarvis-config=jarvis.config:config_wizard",
            "jarvis-setup=jarvis.setup:setup_wizard",
        ],
    },
    author="Jarvis Contributors",
    author_email="dev@jarvis-os.io",
    description="Enterprise-grade autonomous AI agent platform",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/asirselvin446-commits/Jarvis",
    project_urls={
        "Bug Reports": "https://github.com/asirselvin446-commits/Jarvis/issues",
        "Source": "https://github.com/asirselvin446-commits/Jarvis",
        "Documentation": "https://github.com/asirselvin446-commits/Jarvis/wiki",
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Intended Audience :: System Administrators",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: System :: Monitoring",
        "Topic :: Multimedia :: Sound/Audio",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
    ],
    python_requires=">=3.8",
    include_package_data=True,
    zip_safe=False,
)
