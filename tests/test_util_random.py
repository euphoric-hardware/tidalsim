import pytest

from tidalsim.util.random import inst_points_to_inst_steps

class TestUtilRandom:
    def test_inst_points_to_inst_steps(self) -> None:
        assert inst_points_to_inst_steps([100, 1000, 2000]) == [100, 900, 1000]
        assert inst_points_to_inst_steps([100]) == [100]
        with pytest.raises(Exception):
            inst_points_to_inst_steps([100, 1000, 900]) == [100, 900, 1000]
