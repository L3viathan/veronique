import sys
import pytest
import subprocess
from time import sleep
from selenium import webdriver


@pytest.fixture(scope="session")
def veronique(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("veronique")
    import os
    proc = subprocess.Popen(
        [sys.executable, "-m", "sanic", "api", "-p", "8007"],
        env={
            "VERONIQUE_DB": f"{tmp_path}/test.db",
            "VERONIQUE_CREDS": "foo:bar",
        }
    )
    try:
        sleep(1)
        yield "localhost:8007"
    finally:
        proc.terminate()
        proc.wait(timeout=1)
        proc.kill()


@pytest.fixture
def browser(veronique):
    driver = webdriver.Firefox()
    driver.get(f"http://foo:bar@{veronique}")
    driver.implicitly_wait(2)
    try:
        yield driver
    finally:
        driver.close()
