from setuptools import setup

setup(
    name="itch_jam",
    version="1.5",
    py_modules=["itch_jam", "itch_jam_lib"],
    install_requires=[
        "bs4",
        "click-extra",
        "cloup",
        "deepl",
        "html2text",
        "Jinja2",
        "lingua-language-detector",
        "requests",
        "rich",
    ],
    entry_points="""
        [console_scripts]
        itch-jam=itch_jam:itch_jam
    """,
)
