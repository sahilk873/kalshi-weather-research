import unittest
from decode_ecmwf_ensemble import POINTS
class EcmwfEnsembleTest(unittest.TestCase):
 def test_points(self): self.assertEqual(len(POINTS),5)
if __name__=="__main__": unittest.main()
