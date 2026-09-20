from setuptools import setup, find_packages

setup(
    name="slicesim",
    version="1.0.0",
    packages=find_packages(),
    install_requires=[
        'cycler',
        'kiwisolver',
        'matplotlib>=3.5.0',
        'numpy>=1.23.0',
        'Pillow>=9.0.0',
        'pyparsing',
        'python-dateutil',
        'PyYAML>=6.0',
        'randomcolor',
        'scikit-learn>=1.1.0',
        'scipy>=1.8.0',
        'simpy>=4.0.0',
        'six'
    ],
) 