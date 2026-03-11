"""
Rate limiter singleton for API endpoints.
Shared across api/chat.py and api/sessions.py to ensure consistent configuration.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
