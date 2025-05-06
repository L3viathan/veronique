import requests
from time import sleep
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select

def test_unauthenticated(veronique):
    r = requests.get(f"http://{veronique}/")
    assert r.status_code == 401


def _add_root_fact(browser, name):
    browser.find_element(By.ID, "add-button").click()
    browser.find_element(By.LINK_TEXT, "Root claim").click()
    elem = browser.find_element(By.NAME, "name")
    elem.send_keys(name)
    elem.send_keys(Keys.RETURN)
    sleep(0.1)


def _add_verb(browser, name, data_type):
    browser.find_element(By.ID, "add-button").click()
    browser.find_element(By.LINK_TEXT, "Verb").click()
    elem = browser.find_element(By.NAME, "label")
    elem.send_keys(name)
    elem = browser.find_element(By.NAME, "data_type")
    select = Select(elem)
    select.select_by_visible_text(data_type)
    elem = browser.find_element(By.NAME, "label")
    elem.send_keys(Keys.RETURN)
    sleep(0.1)


def _make_link(browser, subject_name, verb_name, object_name):
    browser.get(browser.root_url)
    elem = browser.find_element(By.NAME, "q")
    elem.send_keys(subject_name[:4])
    breakpoint()
    browser.find_element(By.LINK_TEXT, subject_name).click()

    browser.find_element(By.CSS_SELECTOR, "td:nth-child(2) .new-item-placeholder").click()
    elem = browser.find_element(By.NAME, "verb")
    select = Select(elem)
    select.select_by_visible_text(f"{verb_name} (directed_link)")

    elem = browser.find_element(By.NAME, "ac-query")
    elem.send_keys(object_name)
    browser.find_element(By.LINK_TEXT, object_name).click()

    browser.find_element(By.CSS_SELECTOR, "button[type=submit]").click()
    sleep(0.1)


def test_browser(browser):
    _add_root_fact(browser, "Véronique")
    _add_root_fact(browser, "L3viathan")
    _add_verb(browser, "develops", "directed_link")
    _make_link(browser, "L3viathan", "develops", "Véronique")
    ...
