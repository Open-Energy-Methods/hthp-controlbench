"""WP7 property-consistent *model* for MPC and observer prediction.

Uses the independent WP8 enthalpy-state RK4 formulation and the WP7
CoolProp refrigerant Q/P map. The WP7 experiment truth is implemented
separately in wp7_control.py. Agreement tests are *code cross-checks*,
not independent machine calibration or hardware validation.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

import numpy as np

from .core import Disturbance, Parameters, State
from .realfluid import CycleMap, PointRejected, _prop, water_loop_state
from .storage_flexibility import _stage


@dataclass(frozen=True)
class PropertyPredictor:
    model: CycleMap
    props: object
    mass_kg: float = 5000.0

    def __post_init__(self):
        if not isfinite(self.mass_kg) or self.mass_kg <= 0:
            raise ValueError("positive finite enthalpy buffer mass required")

    @property
    def pressure_pa(self) -> float:
        return self.model.assumptions.service_header_pressure_pa

    def enthalpy(self, buffer_k: float) -> float:
        water_loop_state(buffer_k,self.model.assumptions,self.props)
        return _prop(self.props,"H","IF97::Water","T",float(buffer_k),
                     "P",self.pressure_pa)

    def temperature(self, enthalpy: float) -> float:
        tb = _prop(self.props,"T","IF97::Water","P",self.pressure_pa,
                   "H",float(enthalpy))
        water_loop_state(tb,self.model.assumptions,self.props)
        return tb

    def validate(self, y: np.ndarray, d: Disturbance) -> State:
        if not np.all(np.isfinite(y)):
            raise PointRejected("nonfinite_property_predictor_endpoint")
        tb=self.temperature(y[1])
        water_loop_state(max(float(y[0]),tb),self.model.assumptions,self.props)
        self.model.evaluate(float(y[2]),d.t_source,float(y[0]))
        return State(float(y[0]),tb,float(y[2]))

    def advance(self, x: State, u: float, p: Parameters, d: Disturbance,
                period: float, step: float) -> State:
        """Predict with pressure-specific IF97 enthalpy, never constant-water-cp.

        The identical physical control command is held for each interval.
        Every RK4 substage and ACCEPTED endpoint must be within the property
        and assumed liquid-water envelope. No extrapolated rescue.
        """
        if not (isfinite(period) and isfinite(step) and period>0 and step>0):
            raise ValueError("positive finite integration grid required")
        count=int(round(period/step))
        if count<1 or abs(count*step-period)>1e-8:
            raise ValueError("property predictor requires aligned timestep")
        if not p.n_min<=u<=p.n_max:
            raise PointRejected("property_predictor_command_outside_bounds")
        if abs(p.n_min-self.model.modulations[0])>1e-12 or abs(p.n_max-self.model.modulations[-1])>1e-12:
            raise PointRejected("property_predictor_envelope_not_equal_to_actuator_limits")
        y=np.array([x.th,self.enthalpy(x.tb),x.n,0.,0.,0.,0.,0.],dtype=float)
        self.validate(y,d)
        for _ in range(count):
            k1=_stage(y,u,self.model,self.mass_kg,p,d,self.props)
            k2=_stage(y+step*k1/2.,u,self.model,self.mass_kg,p,d,self.props)
            k3=_stage(y+step*k2/2.,u,self.model,self.mass_kg,p,d,self.props)
            k4=_stage(y+step*k3,u,self.model,self.mass_kg,p,d,self.props)
            proposed=y+step*(k1+2*k2+2*k3+k4)/6.
            accepted=self.validate(proposed,d)
            y=proposed
        return accepted

    def power(self, x: State, p: Parameters, d: Disturbance) -> float:
        if not p.n_min-1e-10<=x.n<=p.n_max+1e-10:
            raise PointRejected("property_power_query_modulation_outside_bounds")
        water_loop_state(max(x.th,x.tb),self.model.assumptions,self.props)
        return self.model.evaluate(x.n,d.t_source,x.th)[1]
