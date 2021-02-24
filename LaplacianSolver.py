class LaplacianSolver:
    def __init__(self, params, xp, n, m):
        self._xp = xp
        self._params = params

        p = self._params

        # Laplacian matrix
        self.lap = -((n*p.kn)**2 + (m*p.km)**2)

    def solve(self, in_arr, out_arr):
        # Avoid div by 0 errors
        self.lap[0,0] = 1.0
        out_arr[:] = in_arr/self.lap
        self.lap[0,0] = 0.0
