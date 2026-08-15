"""Put ``api/`` on the import path so tests import the deployed modules directly.

Without this, collection order decides whether ``nymrel_public_mcp_server`` is
importable, which makes a full-suite run pass or fail for reasons unrelated to
the code under test.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "api"))
