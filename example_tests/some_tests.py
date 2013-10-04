import unittest


class SomeImportantTests(unittest.TestCase):

    def test_truth(self):
        """Could it be true?"""
        self.assertTrue(True)

    def test_untruth(self):
        """It can't be!"""
        self.assertFalse(False)

    def test_stupidity(self):
        self.assertEqual("Me", "Smart")


if __name__ == '__main__':
    unittest.main()
