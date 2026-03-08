"""Tests for src/cost.py — shared cost calculation."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from cost import compute_cost


class TestComputeCost:

    def test_opus_pricing(self):
        # input=1000, output=500, cache_create=200, cache_read=300
        # 1000*15/1e6 + 200*18.75/1e6 + 300*1.50/1e6 + 500*75/1e6
        # = 0.015 + 0.00375 + 0.00045 + 0.0375 = 0.05670
        result = compute_cost(1000, 500, 200, 300, 'claude-opus-4-20250514')
        assert round(result, 5) == 0.05670

    def test_non_opus_pricing(self):
        # Same token counts, non-opus rates
        # 1000*3/1e6 + 200*3.75/1e6 + 300*0.30/1e6 + 500*15/1e6
        # = 0.003 + 0.00075 + 0.00009 + 0.0075 = 0.01134
        result = compute_cost(1000, 500, 200, 300, 'claude-sonnet-4-20250514')
        assert round(result, 5) == 0.01134

    def test_model_string_detection_opus(self):
        # Any model containing 'opus' gets opus pricing
        result = compute_cost(1000, 0, 0, 0, 'claude-opus-4-20250514')
        expected = 1000 * 15 / 1e6
        assert result == expected

    def test_model_string_detection_non_opus(self):
        result = compute_cost(1000, 0, 0, 0, 'claude-sonnet-4-20250514')
        expected = 1000 * 3 / 1e6
        assert result == expected

    def test_all_zeros(self):
        assert compute_cost(0, 0, 0, 0, 'claude-opus-4-20250514') == 0.0
        assert compute_cost(0, 0, 0, 0, 'claude-sonnet-4-20250514') == 0.0
