import requests
from time import sleep
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By

def test_unauthenticated(veronique):
    r = requests.get(f"http://{veronique}/")
    assert r.status_code == 401


def _add_root_fact(browser, name):
    browser.find_element(By.ID, "add-button").click()
    elem = browser.find_element(By.NAME, "name")
    elem.send_keys(name)
    elem.send_keys(Keys.RETURN)
    sleep(0.1)


def _add_verb(browser, name):
    ...


def test_browser(browser):
    _add_root_fact(browser, "Véronique")
    _add_root_fact(browser, "L3viathan")
    ...
