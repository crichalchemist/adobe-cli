from setuptools import setup, find_namespace_packages

setup(
    name="cli-anything-illustrator",
    version="1.0.0",
    description="Adobe Illustrator 2026 CLI harness — part of the cli-anything suite.",
    python_requires=">=3.10",
    packages=find_namespace_packages(include=["cli_anything.*"]),
    install_requires=[
        "click>=8.0",
        "prompt_toolkit>=3.0",
    ],
    entry_points={
        "console_scripts": [
            "cli-anything-illustrator=cli_anything.illustrator.illustrator_cli:main",
        ],
    },
    package_data={
        "cli_anything.illustrator": ["skills/SKILL.md"],
    },
)
