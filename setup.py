from setuptools import find_packages, setup

setup(
    name="toolforge-jobs-framework-cli",
    version="8",
    author="Arturo Borrero Gonzalez",
    author_email="aborrero@wikimedia.org",
    license="GPL-3.0-or-later",
    packages=find_packages(),
    entry_points={"console_scripts": ["toolforge-jobs = tjf_cli.cli:main"]},
    description="Command line interface for the Toolforge Jobs framework",
    install_requires=["PyYAML", "requests", "tabulate"],
)
