"""Compatibility alias for the shared service container."""

import sys

from rentivo.services import container as _shared_container

# Legacy tests and integrations patch factories on this module. Aliasing the
# module keeps those patch points attached to the extracted implementation.
sys.modules[__name__] = _shared_container
