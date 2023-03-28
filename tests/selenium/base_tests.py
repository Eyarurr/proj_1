import unittest
import requests
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By

class BaseHtmlTest(unittest.TestCase):

    def setUp(self):
        self.driver = webdriver.Firefox()
        self.base_url = "http://local.biganto-visual.ru/"
        self.login = "yahno@lexion-development.ru"
        self.password = "9rkzee"

    def test_login(self):
        driver = self.driver
        driver.get(self.base_url+"")        

        driver.find_element_by_css_selector(".b-auth__name").click()
        name = driver.find_element_by_name("email")
        name.send_keys(self.login)
        
        password = driver.find_element_by_name("password")
        password.send_keys(self.password)        
        password.submit()
        
        try:            
            WebDriverWait(driver, 10).until(EC.title_contains("Мои объекты"))
        finally:
            pass
    
    def test_users_remind(self):
        driver = self.driver
        driver.get(self.base_url+"users/remind/")
        email = driver.find_element_by_id("email")
        email.send_keys(self.login)
        email.submit()

        try:            
            WebDriverWait(driver, 10).until(
                EC.text_to_be_present_in_element(
                    (By.XPATH, "//p[@class='text-center']"),
                    "Письмо для восстановления пароля отправлено на адрес "+self.login+"."))
        finally:
            pass
        
    def test_call_me(self):
        driver = self.driver
        driver.get(self.base_url+"")        
        driver.find_element_by_css_selector(".b-button__red-tr").click()
       
        email = driver.find_elements_by_name("contact")
        email[1].send_keys(self.login)
        email[1].submit()
        
        try:            
            WebDriverWait(driver, 10).until(
                EC.text_to_be_present_in_element(
                    (By.XPATH, "//div[@class='b-order__result']"),
                    "Спасибо! Мы свяжемся с Вами в ближайшее время."))
        finally:
            pass
                
        driver.find_element_by_css_selector(".b-modal__close").click()
        driver.execute_script("arguments[0].scrollIntoView();", email[0])
        email[0].send_keys(self.login)
        email[0].submit()
        
        try:            
            WebDriverWait(driver, 10).until(
                EC.text_to_be_present_in_element(
                    (By.XPATH, "//div[@class='b-order__result']"),
                    "Спасибо! Мы свяжемся с Вами в ближайшее время."))
        finally:
            pass       
        
    def test_check_links(self):
        driver = self.driver
        driver.get(self.base_url+"")        
        
        elems = driver.find_elements_by_xpath("//a[@href]")

        for elem in elems:
            if (len(elem.get_attribute("href")) > 0
                    and not elem.get_attribute("href").startswith("mailto")):
                link = elem.get_attribute("href")               
                try:        
                    req = requests.get(link, auth=None, allow_redirects=False)
                    self.assertEqual(req.status_code, 200)
                except requests.ConnectionError as e:
                    print('\033[31mCONNECTION ERROR FOR PAGE %s\033[0m' % link)

    def tearDown(self):
        self.driver.close()

if __name__ == "__main__":
#    unittest.main()
    suite = unittest.TestLoader().loadTestsFromTestCase(BaseHtmlTest)    
    unittest.TextTestRunner(verbosity=2).run(suite)
