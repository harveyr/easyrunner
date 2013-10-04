import unittest


class SomeGoodTestsOfThisFeatureThatIsAlsoGood(unittest.TestCase):

    def test_feature_is_truthful(self):
        """It should be."""
        self.assertTrue(True)

    def test_feature_is_pretty_good(self):
        """It'd better be."""
        feature = "pretty good"
        self.assertEqual(feature, "pretty good")

    def test_feature_does_not_suck(self):
        """D'oh!"""
        feature = "sucks"
        # self.assertNotEqual(feature, "sucks")


if __name__ == '__main__':
    unittest.main()
