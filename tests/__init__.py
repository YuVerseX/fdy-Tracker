"""Test package bootstrap."""
import os

# Keep unit tests hermetic from the caller's ambient proxy config.
os.environ.pop("OUTBOUND_PROXY_URL", None)
