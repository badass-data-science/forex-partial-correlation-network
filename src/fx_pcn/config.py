import numpy as np

PAIRS: list[str] = [
    'EUR/USD',
    'GBP/USD',
    'USD/JPY',
    'USD/CHF',
    'USD/CAD',
    'AUD/USD',
    'NZD/USD',
]

# The name recorded on every edge-table row (and folded into RDF URIs) when
# no --network-name is given -- identifies which pair set ('PAIRS' above)
# produced a given network, so custom pair sets (via --pairs/--network-name)
# never get silently conflated with the default one.
DEFAULT_NETWORK_NAME = 'forex-network-seven-majors'

MEASUREMENT = 'forward-filled candlestick'
GRANULARITY = 'H1'

WINDOW_DAYS = 5
STEP_DAYS = 1
MIN_OBSERVATIONS_PER_WINDOW = 60

MAX_LAG = 4
FDR_ALPHA = 0.05

# GraphicalLassoCV's default automatic alpha grid drifts into a near-zero
# (near-singular) regularization regime given how collinear the FX pairs are
# (shared USD legs), which makes coordinate descent numerically unstable --
# lots of ConvergenceWarning / RuntimeWarning noise even with more iterations.
# Constraining the grid to this range eliminates nearly all of that without
# ever landing on the floor (i.e. the true optimum isn't being cut off).
GRAPHICAL_LASSO_ALPHAS = np.logspace(-2.2, 0.3, 30)
