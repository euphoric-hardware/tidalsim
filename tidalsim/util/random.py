from typing import List

def clog2(x):
  """Ceiling of log2"""
  if x <= 0:
    raise ValueError("domain error")
  return (x-1).bit_length()

def inst_points_to_inst_steps(inst_points: List[int]) -> List[int]:
    inst_steps = [inst_points[0]] + [(inst_points[i] - inst_points[i-1]) for i in range(1, len(inst_points))]
    assert all(step >= 0 for step in inst_steps)
    return inst_steps
