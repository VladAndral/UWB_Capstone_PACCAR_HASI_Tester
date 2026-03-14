import unittest, utils

class UtilsTest(unittest.TestCase):
    
    def test_loadFilePathReturnType(self):
        self.assertIsInstance(utils.loadFilePath("primaryDBC"), str)
        self.assertIsInstance(utils.loadFilePath("secondaryDBC"), str)
        self.assertIsInstance(utils.loadFilePath("config"), str)
        self.assertNotIsInstance(utils.loadFilePath("Vector"), str)
        