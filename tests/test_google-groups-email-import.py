ggei = __import__('google-groups-email-import')
from time import time

def test_rate_limiter_below_limit():
    rl = ggei.RateLimiter(100, 1)
    t0 = time()
    for i in range(100):
        rl.wait_for_clearance()
        rl.register()
    elapsed = time() - t0
    assert elapsed < 0.001

def test_rate_limiter_limit_enforced():
    rl = ggei.RateLimiter(1, 1)
    t0 = time()
    for i in range(2):
        rl.wait_for_clearance()
        rl.register()
    elapsed = time() - t0
    assert 1 < elapsed < 1 + 0.005

