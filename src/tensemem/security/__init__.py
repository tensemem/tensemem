"""Secret scrubbing, fencing, and sensitive-predicate policy."""

from tensemem.security.fence import strip, wrap
from tensemem.security.scrub import REPLACEMENT, scrub

__all__ = ["REPLACEMENT", "scrub", "strip", "wrap"]
