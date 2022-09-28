from setuptools import setup

setup(
    name="itch_jam",
    version="0.1",
    py_modules=["itch_jam"],
    install_requires=["click", "cloup", "requests", "bs4", "tqdm", "dataset", "rich"],
    entry_points="""
        [console_scripts]
        itch-jam=itch_jam:cli
    """,
)
