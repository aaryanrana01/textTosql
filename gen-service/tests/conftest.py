"""Test-wide settings, applied before any app module is imported:
tests never send traces to Langfuse and never touch the real Redis cache."""
import os

os.environ["LANGFUSE_PUBLIC_KEY"] = ""
os.environ["LANGFUSE_SECRET_KEY"] = ""
os.environ["REDIS_URL"] = ""
