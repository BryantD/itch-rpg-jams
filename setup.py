from setuptools import setup

setup(
    name="itch_jam",
    version="1.0",
    py_modules=["itch_jam"],
    install_requires=[
        "bs4",
        "click-extra",
        "cloup",
        "deepl",
        "html2text",
        "Jinja2",
        "lingua",
        "requests",
        "rich",
    ],
    entry_points="""
        [console_scripts]
        itch-jam=itch_jam:itch_jam
    """,
)
