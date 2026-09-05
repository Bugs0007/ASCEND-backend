"""
Plain-Python statistics primitives. No numpy, no pandas — the whole point is
to keep the Render image small and the free tier viable, and to have every
formula readable and unit-tested rather than opaque inside a library call.

Every function returns None (or a dict containing None fields) on
degenerate input — empty series, n<2, zero variance — rather than raising,
so callers can render "not enough data yet" instead of crashing.
"""
import math
from statistics import fmean


def safe_div(numerator, denominator, default=None):
    """Division that returns `default` instead of raising on a zero (or falsy) denominator."""
    if not denominator:
        return default
    return numerator / denominator


def mean(values):
    values = list(values)
    if not values:
        return None
    return fmean(values)


def quantile(sorted_values, q):
    """
    Linear-interpolation quantile (matches numpy's default 'linear' method),
    for consistent IQR computation. `sorted_values` must already be sorted.
    """
    n = len(sorted_values)
    if n == 0:
        return None
    if n == 1:
        return float(sorted_values[0])
    pos = q * (n - 1)
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return float(sorted_values[lo])
    frac = pos - lo
    return float(sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * frac)


def median(values):
    values = list(values)
    if not values:
        return None
    return quantile(sorted(values), 0.5)


def iqr(values):
    """
    Returns {"q1", "median", "q3", "iqr"} for a list of numbers, or None if
    empty. `iqr` is q3 - q1.
    """
    values = list(values)
    if not values:
        return None
    s = sorted(values)
    q1 = quantile(s, 0.25)
    q3 = quantile(s, 0.75)
    return {"q1": q1, "median": quantile(s, 0.5), "q3": q3, "iqr": q3 - q1}


def pearson_r(xs, ys):
    """
    Pearson correlation coefficient. None if the series differ in length,
    have fewer than 2 points, or either has zero variance (undefined r).
    """
    xs = list(xs)
    ys = list(ys)
    n = len(xs)
    if n < 2 or n != len(ys):
        return None
    mean_x = fmean(xs)
    mean_y = fmean(ys)
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)
    if var_x == 0 or var_y == 0:
        return None
    return cov / math.sqrt(var_x * var_y)


def linear_regression(xs, ys):
    """
    Ordinary least squares. Returns (slope, intercept), or None if there are
    fewer than 2 points or x has zero variance (a vertical line has no
    slope/intercept form here).
    """
    xs = list(xs)
    ys = list(ys)
    n = len(xs)
    if n < 2 or n != len(ys):
        return None
    mean_x = fmean(xs)
    mean_y = fmean(ys)
    var_x = sum((x - mean_x) ** 2 for x in xs)
    if var_x == 0:
        return None
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    slope = cov / var_x
    intercept = mean_y - slope * mean_x
    return slope, intercept


def trend_line_endpoints(xs, ys):
    """
    Fits a line and returns its two endpoints spanning the observed x range,
    ready for a frontend to draw directly: {"x0","y0","x1","y1"}. None if a
    regression can't be fit (see linear_regression).
    """
    xs = list(xs)
    reg = linear_regression(xs, ys)
    if reg is None:
        return None
    slope, intercept = reg
    x0, x1 = min(xs), max(xs)
    return {
        "x0": x0,
        "y0": slope * x0 + intercept,
        "x1": x1,
        "y1": slope * x1 + intercept,
    }


def project_at(xs, ys, target_x):
    """Evaluate the OLS fit of (xs, ys) at target_x. None if it can't be fit."""
    reg = linear_regression(xs, ys)
    if reg is None:
        return None
    slope, intercept = reg
    return slope * target_x + intercept
