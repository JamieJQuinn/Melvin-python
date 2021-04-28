#!/usr/bin/env python3

import numpy as np
from numpy.random import default_rng

import cupy
import time
from utility import sech
import matplotlib.pyplot as plt

from Parameters import Parameters
from SpectralTransformer import SpectralTransformer
from DataTransferer import DataTransferer
from Variable import Variable
from TimeDerivative import TimeDerivative
from SpatialDifferentiator import SpatialDifferentiator
from Integrator import Integrator
from Timer import Timer
from ScalarTracker import ScalarTracker
from RunningState import RunningState
from ArrayFactory import ArrayFactory
from Operators import double_fourier_viscous_op

xp=cupy

def load_initial_conditions(params, w, tmp):
    x = np.linspace(0, params.lx, params.nx, endpoint = False)
    z = np.linspace(0, params.lz, params.nz, endpoint = True)
    X, Z = np.meshgrid(x, z, indexing='ij')

    rng = default_rng(0)

    epsilon = 1e-2

    w0_p = np.zeros_like(X)
    tmp0_p = np.zeros_like(X)

    tmp0_p += epsilon*(2*rng.random((params.nx, params.nz))-1.0)

    w.load(w0_p, is_physical=True)
    tmp.load(tmp0_p, is_physical=True)

def calc_kinetic_energy(ux, uz, xp, params):
    nx, nz = params.nx, params.nz
    ke = uz.getp()**2 + ux.getp()**2
    total_ke = 0.5*xp.sum(ke)/(nx*nz)
    return total_ke

def calc_nusselt_number(tmp, uz, xp, params):
    # From Stellmach et al 2011 (DOI: 10.1017/jfm.2011.99)
    flux = xp.mean(tmp.getp()*uz.getp())
    return 1.0 - flux

def form_dumpname(index):
    return f'dump{index:04d}.npz'

def dump(index, xp, data_trans, w, dw, tmp, dtmp):
    fname = form_dumpname(index)
    np.savez(fname, 
                w =data_trans.to_host( w[:]),
                dw=data_trans.to_host(dw.get_all()),
                tmp =data_trans.to_host( tmp[:]),
                dtmp=data_trans.to_host(dtmp.get_all()), 
                curr_idx = dw.get_curr_idx())

def load(index, xp, w, dw, tmp, dtmp):
    fname = form_dumpname(index)
    dump_arrays = xp.load(fname)
    w.load(dump_arrays['w'])
    dw.load(dump_arrays['dw'])
    tmp.load(dump_arrays['tmp'])
    dtmp.load(dump_arrays['dtmp'])

    # This assumes all variables are integrated together
    dw.set_curr_idx(dump_arrays['curr_idx'])
    dtmp.set_curr_idx(dump_arrays['curr_idx'])

def main():
    PARAMS = {
        "nx": 2**10,
        "nz": 2**10,
        "lx": 335.0,
        "lz": 536.0,
        "initial_dt": 1e-3,
        "cfl_cutoff": 0.5,
        "Pr":7.0,
        "R0":1.1,
        "tau":1.0/3.0,
        "final_time": 1e-1,
        "spatial_derivative_order": 2,
        "integrator_order": 2,
        "integrator": "explicit",
        "save_cadence": 1e-2,
        # "load_from": 49,
        "dump_cadence": 10
    }
    params = Parameters(PARAMS)
    state = RunningState(params)

    data_trans = DataTransferer(xp)

    array_factory = ArrayFactory(params, xp)
    # Create mode number matrix
    n, m = array_factory.make_mode_number_matrices()

    # Algorithms
    sd = SpatialDifferentiator(params, xp, n, m)
    st = SpectralTransformer(params, xp, array_factory)
    integrator = Integrator(params, xp)

    # Trackers
    ke_tracker = ScalarTracker(params, xp, "kinetic_energy.npz")
    nusselt_tracker = ScalarTracker(params, xp, "nusselt.npz")

    # Simulation variables

    w = Variable(params, xp, sd=sd, st=st, dt=data_trans, array_factory=array_factory, dump_name="w")
    dw = TimeDerivative(params, xp)
    tmp = Variable(params, xp, sd=sd, st=st, dt=data_trans, array_factory=array_factory, dump_name="tmp")
    dtmp = TimeDerivative(params, xp)

    psi = Variable(params, xp, sd=sd, st=st, array_factory=array_factory, dump_name='psi')
    ux = Variable(params, xp, sd=sd, st=st, array_factory=array_factory, dump_name='ux')
    uz = Variable(params, xp, sd=sd, st=st, array_factory=array_factory, dump_name='uz')

    # Load initial conditions

    if params.load_from is not None:
        load(params.load_from, xp, w, dw, tmp, dtmp)
        integrator.override_dt(state.dt)
    else:
        load_initial_conditions(params, w, tmp)

    total_start = time.time()
    wallclock_remaining = 0.0
    timer = Timer()

    # Main loop

    while state.t < params.final_time:
        if state.save_counter <= state.t:
            state.save_counter += params.save_cadence
            print(f"{state.t/params.final_time *100:.2f}% complete",
                  f"t = {state.t:.2f}", 
                  f"dt = {state.dt:.2e}", 
                  f"Remaining: {wallclock_remaining/3600:.2f} hr")
            # tmp.save()
            ke_tracker.save()
            # nusselt_tracker.save()

        if state.dump_counter <= state.t:
            state.dump_counter += params.dump_cadence
            dump(state.dump_index, xp, data_trans,
                 w, dw, tmp, dtmp)
            state.save(state.dump_index)
            state.dump_index += 1

        if state.ke_counter < state.loop_counter:
            # Calculate kinetic energy
            state.ke_counter += params.ke_cadence
            ke_tracker.append(state.t, calc_kinetic_energy(ux, uz, xp, params))
            nusselt_tracker.append(state.t, calc_nusselt_number(tmp, uz, xp, params))

            # Calculate remaining time in simulation
            timer.split()
            wallclock_per_timestep = timer.diff/params.ke_cadence
            wallclock_remaining = wallclock_per_timestep*(params.final_time - state.t)/state.dt

        if state.cfl_counter < state.loop_counter:
            # Adapt timestep
            state.cfl_counter += params.cfl_cadence
            state.dt = integrator.set_dt(ux, uz)

        # SOLVER STARTS HERE
        psi.set_as_laplacian_soln(-w.gets())

        # Remove mean z variation
        tmp[:,0] = 0.0

        ux[:] = -psi.sddz()
        ux.to_physical()
        uz[:] = psi.sddx()
        uz.to_physical()

        lin_op = lambda var: return double_fourier_viscous_op(params.Pr, w)
        dw[:] = -w.vec_dot_nabla(ux.getp(), uz.getp()) - params.Pr*tmp.sddx()
        integrator.integrate(w, dw, lin_op)

        lin_op = lambda var: return double_fourier_viscous_op(1.0, tmp)
        dtmp[:] = -tmp.vec_dot_nabla(ux.getp(), uz.getp())
        integrator.integrate(tmp, dtmp, lin_op)

        state.t += state.dt
        state.loop_counter += 1

    total_end = time.time() - total_start
    print(f"Total time: {total_end/3600:.2f} hr")
    print(f"Total time: {total_end:.2f} s")

if __name__=="__main__":
    main()