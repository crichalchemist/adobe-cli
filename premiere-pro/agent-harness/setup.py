from setuptools import setup, find_namespace_packages

setup(
    name="cli-anything-premierepro",
    version="1.0.0",
    description="Adobe Premiere Pro 2025 CLI harness",
    python_requires=">=3.10",
    packages=find_namespace_packages(include=["cli_anything.*"]),
    package_data={
        "cli_anything.premierepro": ["skills/*.md", "cep/**/*", "cep/CSXS/*", "cep/js/*"],
    },
    install_requires=[
        "click>=8.0",
        "requests>=2.28",
        "opencv-python-headless",
    ],
    entry_points={
        "console_scripts": [
            "cli-anything-premierepro=cli_anything.premierepro.premierepro_cli:cli",
        ],
    },
)
