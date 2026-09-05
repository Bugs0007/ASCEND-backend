"""Pure-function tests for core.stats — no database needed."""
import pytest

from core import stats


class TestSafeDiv:
    def test_normal(self):
        assert stats.safe_div(10, 4) == 2.5

    def test_zero_denominator_returns_default(self):
        assert stats.safe_div(10, 0) is None
        assert stats.safe_div(10, 0, default=0) == 0

    def test_none_denominator(self):
        assert stats.safe_div(10, None) is None


class TestMeanMedian:
    def test_mean_empty(self):
        assert stats.mean([]) is None

    def test_mean(self):
        assert stats.mean([1, 2, 3, 4]) == pytest.approx(2.5)

    def test_median_empty(self):
        assert stats.median([]) is None

    def test_median_odd(self):
        assert stats.median([1, 3, 2]) == 2

    def test_median_even(self):
        assert stats.median([1, 2, 3, 4]) == pytest.approx(2.5)


class TestIQR:
    def test_empty(self):
        assert stats.iqr([]) is None

    def test_known_fixture(self):
        # Textbook example: 1,2,3,4,5,6,7,8,9,10,11 -> Q1=3.5? verify via
        # linear interpolation method against a hand-computed value.
        values = list(range(1, 12))  # 1..11
        result = stats.iqr(values)
        # positions: q1 at 0.25*(11-1)=2.5 -> interpolate values[2],[3] = 3,4 -> 3.5
        # q3 at 0.75*10=7.5 -> values[7],[8] = 8,9 -> 8.5
        assert result["q1"] == pytest.approx(3.5)
        assert result["q3"] == pytest.approx(8.5)
        assert result["iqr"] == pytest.approx(5.0)
        assert result["median"] == pytest.approx(6.0)


class TestPearsonR:
    def test_empty_or_single_point(self):
        assert stats.pearson_r([], []) is None
        assert stats.pearson_r([1], [2]) is None

    def test_mismatched_lengths(self):
        assert stats.pearson_r([1, 2, 3], [1, 2]) is None

    def test_zero_variance_returns_none(self):
        assert stats.pearson_r([1, 1, 1], [1, 2, 3]) is None
        assert stats.pearson_r([1, 2, 3], [5, 5, 5]) is None

    def test_perfect_positive_correlation(self):
        xs = [1, 2, 3, 4, 5]
        ys = [2, 4, 6, 8, 10]
        assert stats.pearson_r(xs, ys) == pytest.approx(1.0)

    def test_perfect_negative_correlation(self):
        xs = [1, 2, 3, 4, 5]
        ys = [10, 8, 6, 4, 2]
        assert stats.pearson_r(xs, ys) == pytest.approx(-1.0)

    def test_hand_computed_fixture(self):
        # Hand-computed: xs=[1,2,3,4,5], ys=[2,1,4,3,5]
        # mean_x=3, mean_y=3
        # cov = (1-3)(2-3)+(2-3)(1-3)+(3-3)(4-3)+(4-3)(3-3)+(5-3)(5-3)
        #     = (-2)(-1)+(-1)(-2)+(0)(1)+(1)(0)+(2)(2) = 2+2+0+0+4 = 8
        # var_x = 4+1+0+1+4 = 10
        # var_y = 1+4+1+0+4 = 10
        # r = 8 / sqrt(10*10) = 8/10 = 0.8
        xs = [1, 2, 3, 4, 5]
        ys = [2, 1, 4, 3, 5]
        assert stats.pearson_r(xs, ys) == pytest.approx(0.8)


class TestLinearRegression:
    def test_none_below_two_points(self):
        assert stats.linear_regression([1], [2]) is None

    def test_zero_x_variance_returns_none(self):
        assert stats.linear_regression([5, 5, 5], [1, 2, 3]) is None

    def test_exact_line(self):
        xs = [0, 1, 2, 3]
        ys = [1, 3, 5, 7]  # y = 2x + 1
        slope, intercept = stats.linear_regression(xs, ys)
        assert slope == pytest.approx(2.0)
        assert intercept == pytest.approx(1.0)

    def test_project_at(self):
        xs = [0, 1, 2, 3]
        ys = [1, 3, 5, 7]
        assert stats.project_at(xs, ys, 10) == pytest.approx(21.0)

    def test_trend_line_endpoints(self):
        xs = [0, 1, 2, 3]
        ys = [1, 3, 5, 7]
        line = stats.trend_line_endpoints(xs, ys)
        assert line["x0"] == 0
        assert line["y0"] == pytest.approx(1.0)
        assert line["x1"] == 3
        assert line["y1"] == pytest.approx(7.0)
