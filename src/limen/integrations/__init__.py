"""External-source integrations.

One sub-package per source. Every HTTP call goes through
:mod:`limen.integrations._http` which provides a shared
``httpx.AsyncClient`` factory, the tenacity retry policy, and the
soft-circuit-breaker decorator that returns a neutral result when a
source is unreachable instead of crashing the caller.
"""
