from setuptools import setup, find_namespace_packages

setup(
    name="cli-anything-acrobat",
    version="1.0.0",
    description="CLI harness for Adobe Acrobat DC — PDF operations from the command line",
    packages=find_namespace_packages(include=["cli_anything.*"]),
    install_requires=[
        "click>=8.0.0",
        "prompt-toolkit>=3.0.0",
        "pypdf>=6.0.0",
        "PyMuPDF>=1.20.0",
    ],
    entry_points={
        "console_scripts": [
            "cli-anything-acrobat=cli_anything.acrobat.acrobat_cli:main",
        ],
    },
    python_requires=">=3.10",
    package_data={
        "cli_anything.acrobat": ["skills/*.md"],
    },
)
