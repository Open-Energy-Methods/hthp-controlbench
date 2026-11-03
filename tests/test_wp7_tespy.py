"""Run an actual TESPy network for exactly matched CoolProp cycle assumptions."""
import unittest
from ht_hp_controlbench.realfluid import cycle_point
from ht_hp_controlbench.tespy_check import tespy_same_cycle

try:import tespy
except ImportError:TESPY=False
else:TESPY=True

@unittest.skipUnless(TESPY,'TESPy optional; CI tests it on Python 3.11 and 3.12')
class TestTespyNetwork(unittest.TestCase):
    def test_nominal_component_network_matches_direct_cycle(self):
        point=cycle_point('R1233zd(E)',333.15,406.2)
        row=tespy_same_cycle(point)
        self.assertAlmostEqual(row['tespy_cop'],row['direct_cop'],delta=.02*row['direct_cop'])
        self.assertLess(abs(row['compressor_fractional_disagreement']),.02)
        self.assertLess(abs(row['condenser_fractional_disagreement']),.02)
        self.assertLess(abs(row['energy_balance_residual_w']),3.1)
    def test_invalid_condenser_load_rejected_before_network_solve(self):
        x=cycle_point('R1233zd(E)',333.15,406.2)
        with self.assertRaises(ValueError):tespy_same_cycle(x,0)

if __name__=='__main__':unittest.main()
