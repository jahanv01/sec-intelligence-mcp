"""Test-session setup: disable real LangFuse tracing during tests.

Must run before any test module imports tools.analyze_filing (or anything else that
triggers langfuse.get_client()) -- otherwise, since .env has real LangFuse credentials
configured (Issue 8.1), @observe-decorated code would emit real traces to the real cloud
project on every test run.
"""

import os

os.environ["LANGFUSE_TRACING_ENABLED"] = "false"
