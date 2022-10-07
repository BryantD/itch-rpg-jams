from setuptools import setup

setup(
    name="itch_jam",
    version="0.9",
    py_modules=["itch_jam"],
    install_requires=[
        "bs4",
        "cloup",
        "html2text",
        "requests",
        "rich",
    ],
    entry_points="""
        [console_scripts]
        itch-jam=itch_jam:cli
    """,
)
