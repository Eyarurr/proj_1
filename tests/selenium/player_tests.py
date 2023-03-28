import unittest
import os
import time
import glob

from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.firefox.firefox_profile import FirefoxProfile


class PlayerTest(unittest.TestCase):    
    
    def setUp(self):
       self.driver = webdriver.Firefox()
       self.base_url = "http://yaho.room-park.biganto.ru/tour/314/"
       self.login = "yahno@lexion-development.ru"
       self.password = "9rkzee"
    
    
    def test_control_dollhouse(self):
        driver = self.driver
        driver.get(self.base_url+"")        
        
        try:            
            WebDriverWait(driver, 10).until(
                EC.visibility_of_element_located(
                    (By.XPATH, "//div[contains(@class,'action__dollhouse')]"))).click()
            
            driver.find_element(By.XPATH, "//div[contains(@class,'action__dollhouse')]").click()
            
            WebDriverWait(driver, 10).until(
                EC.text_to_be_present_in_element((By.XPATH, "//div[contains(@class,'b-hint--light')]"),
                    "Чтобы двигать модель, перетаскивайте её мышкой, поворачивайте правой кнопкой или с зажатым Alt"))
            
            WebDriverWait(driver, 10).until(
                EC.visibility_of_element_located(
                    (By.XPATH, "//div[contains(@class,'b-toolbar__inner')]/div[@title='Модель']"))).click()           
        finally:
            pass
        
    
    def test_control_tours_link(self):
        driver = self.driver
        driver.get(self.base_url+"")
        
        try:            
            WebDriverWait(driver, 5).until(
                EC.visibility_of_element_located(
                    (By.XPATH, "//div[contains(@class,'b-modal--help')]/div[@class='b-modal__close']"))).click()
            
            time.sleep(3)
            WebDriverWait(driver, 5).until(
                EC.visibility_of_element_located(
                    (By.XPATH, "//div[contains(@class,'b-toolbar__main')]/div[contains(@class,'action__link_generator')]"))).click()
                        
            
            WebDriverWait(driver, 5).until(
                EC.visibility_of_element_located(
                    (By.XPATH, "/html/body/div/div[8]/div[2]/div[4]/span[2]"))).click()                   
        finally:
            pass
        
    
    def test_screen_full_size(self):
        driver = self.driver
        driver.get(self.base_url+"")
        width_before = driver.get_window_size().get('width')
        driver.maximize_window()        
        width_after = driver.get_window_size().get('width')
        
        assert width_before < width_after
        
    
    def test_download_screenshot(self):
        fp = webdriver.FirefoxProfile()
        fp.set_preference('browser.download.folderList', 2)
        fp.set_preference('browser.download.manager.showWhenStarting', False)
        fp.set_preference('browser.download.dir', os.getcwd())
        fp.set_preference("browser.helperApps.neverAsk.saveToDisk", 'image/png')
        driver = webdriver.Firefox(firefox_profile = fp)       
        driver.get(self.base_url+"")
        
        try:            
            WebDriverWait(driver, 10).until(
                EC.visibility_of_element_located(
                    (By.XPATH, "//div[contains(@class,'b-toolbar__main')]/div[contains(@class,'action__screenshot')]"))).click()
        
            driver.find_element(By.XPATH, "//div[contains(@class,'action__screenshot')]").click()
            
            time.sleep(5)
            assert len(glob.glob(os.getcwd()+'/skybox*.png')) > 0
            
        finally:
            pass
        
        driver.close()
        
    def test_map_open_close(self):
        driver = self.driver
        driver.get(self.base_url+"")
        
        try:            
            WebDriverWait(driver, 5).until(
                EC.visibility_of_element_located(
                    (By.XPATH, "//div[contains(@class,'b-map__zoom')]"))).click()
            driver.find_element(By.XPATH, "//div[contains(@class,'b-map__zoom')]").click()   
            time.sleep(2)
            driver.find_element(By.XPATH, "//div[contains(@class,'b-map__zoom')]").click()   
            driver.find_element(By.XPATH, "//div[contains(@class,'b-map__close')]").click()
            driver.find_element(By.XPATH, "//div[contains(@class,'b-toolbar--bottom')]").click()
            driver.find_element(By.XPATH, "//div[contains(@class,'b-map__zoom')]").click()
            
            #WebDriverWait(driver, 5).until(
            #    EC.visibility_of_element_located(
            #        (By.XPATH, "//div[contains(@class,'b-map__zoom')]"))).click()
        finally:
            pass
        
    def test_points_on_map(self):
        driver = self.driver
        driver.implicitly_wait(3)
        driver.get(self.base_url+"")
        
        try:            
            WebDriverWait(driver, 5).until(
                EC.visibility_of_element_located(
                    (By.XPATH, "//*[@id='map']/div[2]/div[2]/div/div/div[3]"))).click()
            
            driver.find_element(By.XPATH, "//*[@id='map']/div[2]/div[2]/div/div/div[3]").click()
            time.sleep(2)
            
        finally:
            pass
        
        
    def tearDown(self):
        self.driver.close()

if __name__ == "__main__":
    #unittest.main()
    suite = unittest.TestLoader().loadTestsFromTestCase(PlayerTest)    
    unittest.TextTestRunner(verbosity=2).run(suite)