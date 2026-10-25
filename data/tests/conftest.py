import os

# Tests must never reach a real GraphHopper (or depend on the network), even if a local .env sets GH_URL.
# app.py's .env loader uses setdefault, so an explicit empty value wins; empty means "fake provider".
os.environ["GH_URL"] = ""
