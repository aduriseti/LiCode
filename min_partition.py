r"""
will optimize this dp minimization step using a convex hull

our internal dp relation looks like

dp[i] = minimum partition score for nums i
          = min(
            value(nums[i:j]) + dp[j] + \lambda
            for j in range i, len(nums)

value = (P[j] - P[i]) * (P[j] - P[i] + 1) / 2

we can rewrite our dp term into a minimization term over a set of lines in the
2d plane of the form y = mx + b - minimizing this term then becomes finding
the minimal point on the convex hull for query point x

dp[i] = min_j((P[j]^2 - 2P[i]P[j] + P[i]^2 - P[j] - P[i]) / 2 + dp[j] + \lambda)
      = (P[i]^2 - P[i]) / 2 + \lambda + min_j(-P[j] * P[i] + (P[j]^2 - P[j]) / 2 + dp[j])

so now `m = -P[j]` and `b = (P[j]^2 - P[j]) / 2 + dp[j]`, and query points will
be `P[i]`

and the process of minimizing for a specific P[i] is querying the lb convex hull
of these lines

we can build a convex hull using a python sorted list

for 3 lines of sorted slopes, l1,l2,l3, l2 is redundant if l1 intersects l3
to the right of where l1 intersects l2

intersection point for 2 lines is:
x = (c2-c1) / (m1-m2)

so for 3 lines, l1,l2,l3, l2 is redundant when
(c3-c1) / (m1-m3) >= (c2-c1) / (m1-m2)
or
(c3-c1) * (m1-m2) >= (c2-c1) * (m1-m3)

when inserting lines into this sorted list, we will check and delete any
neighbors made redundant w/ this new line

finally, when querying for `x` pts we can perform binary search to find a line
s/t its intersection pts w/ its neighbors bracket `x`
"""


nums = [5,1,2,1]; k = 2

import numpy as np
import bisect

N = len(nums)
prefix_sum = [0]
for n in nums:
  prefix_sum.append(prefix_sum[-1] + n)

def value(i, j):
  sum_arr = prefix_sum[j] - prefix_sum[i]
  return sum_arr * (sum_arr + 1) / 2

def bsl(l, r, f, t):
  while l < r:
    m = (l + r) >> 1
    if f(m) < t:
      l = m + 1
    else:
      r = m
  return l

def intersection(l1, l2):
  m1, b1, _ = l1
  m2, b2, _ = l2
  return (b2 - b1) / (m1 - m2)

def redundant(l1, l2, l3):
  return intersection(l1, l2) <= intersection(l2, l3)

class ConvexHullLb():
  def __init__(self):
    self.hull = []

  def add(self, line):
    m, b, count = line
    idx = bisect.bisect_left(self.hull, (m, b, count))
    self.hull.insert(idx, line)
    
    # Remove redundant lines to the right
    while idx < len(self.hull) - 2:
      if redundant(self.hull[idx], self.hull[idx+1], self.hull[idx+2]):
        self.hull.pop(idx+1)
      else:
        break
    # Remove redundant lines to the left
    while idx > 1:
      if redundant(self.hull[idx-2], self.hull[idx-1], self.hull[idx]):
        self.hull.pop(idx-1)
        idx -= 1
      else:
        break
    # Check if the newly added line itself is redundant
    if 0 < idx < len(self.hull) - 1:
      if redundant(self.hull[idx-1], self.hull[idx], self.hull[idx+1]):
        self.hull.pop(idx)

  def query(self, x: float):
    def f(i):
      if i >= len(self.hull) - 1:
        return True
      return x >= intersection(self.hull[i], self.hull[i+1])
    
    idx = bsl(0, len(self.hull), f, True)
    m, b, count = self.hull[idx]
    return m * x + b, count

def minPartitionScoreForLambda(lam):
  dp = np.zeros((N+1, 2))
  dp[N] = [0, 0]
  def get_line(j):
    m = -prefix_sum[j]
    b = (prefix_sum[j]**2 + prefix_sum[j]) / 2 + dp[j, 0]
    return (m, b, dp[j, 1])
  cht = ConvexHullLb()
  cht.add(get_line(N))
  for i in range(N-1, -1, -1):
    p_i = prefix_sum[i]
    cost_i = (p_i**2 - p_i) / 2 + lam
    val, count = cht.query(p_i)
    dp[i] = [cost_i + val, count + 1]
    cht.add(get_line(i))
  return dp[0]

def shim(lam):
  return minPartitionScoreForLambda(-lam)[1]

optimal_lambda = -bsl(-int(value(0,N)), int(value(0,N)), shim, k)
score, _ = minPartitionScoreForLambda(optimal_lambda)
# should be 25
print(score - k * optimal_lambda)
