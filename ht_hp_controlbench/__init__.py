"""Synthetic nonlinear HTHP-ControlBench Level-1 thermal plant; no hardware validation."""
from .core import Parameters, Disturbance, State, HxResult, Rates, heat_exchanger, equilibrium, rhs, output, counterflow_effectiveness
from .sim import Simulation, simulate, Schedule
