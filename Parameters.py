import numpy as np
import sys

class Parameters:
    required_params = ['nx', 'nz', 'lx', 'lz', 'final_time']

    # Default parameters
    integrator_order = 2
    integrator = 'explicit'
    spatial_derivative_order = 2
    alpha = 0.51
    cfl_cutoff = 0.5
    cfl_cadence = 10 # Number of timesteps between CFL checks
    ke_cadence = 100 # Number of timesteps between kinetic energy save
    save_cadence = 100
    load_from = None

    complex = np.complex128
    float = np.float64

    # Required parameters
    nx = None
    nz = None
    lx = None
    lz = None
    final_time = None

    def __init__(self, params, validate=True):
        if validate:
            if not self.is_valid(params):
                sys.exit(-1)

        self.load_from_dict(params)
        self.set_derived_params(params)

    def load_from_dict(self, params):
        for key in params:
            setattr(self, key, params[key])

    def is_valid(self, params):
        valid = True
        for key in self.required_params:
            if key not in params:
                print(key, "missing from input parameters.")
                valid = False
        return int(valid)

    def set_derived_params(self, params):
        if 'dump_cadence' not in params:
            self.dump_cadence = 0.1*self.final_time

        self.nn = (self.nx-1)//3
        self.nm = (self.nz-1)//3

        self.kn = 2*np.pi/self.lx
        self.km = 2*np.pi/self.lz

        self.dx = self.lx/self.nx
        self.dz = self.lz/self.nz

        if 'initial_dt' not in params:
            self.initial_dt = 0.2*min(self.dx, self.dz)
