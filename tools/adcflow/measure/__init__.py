"""Measurement functions of the acceptance tests.

Each test of specs/blocks/*.yaml names ``measure: adcflow.measure.<module>:<fn>``;
the function is called as ``fn(job_dir, ctx)`` after the simulation and returns
a dict of metrics whose keys are the ``metric`` names of the specs.
"""
