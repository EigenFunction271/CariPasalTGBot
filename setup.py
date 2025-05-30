from setuptools import setup, find_packages

setup(
    name="loophole-project-tracker",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "python-telegram-bot==20.7",
        "Flask[async]==3.0.2",
        "pyairtable==2.3.0",
        "python-dotenv==1.0.1",
        "gunicorn==21.2.0",
        "gevent==25.5.1",
        "httpx~=0.25.2",
        "uvicorn==0.27.1",
    ],
) 