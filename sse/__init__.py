"""Standalone async service serving GET /api/v1/manager/board/events (SSE).

Deliberately does not import ``webapp``: that would build the whole Flask
app (and require all of its config) just to stream move pings.
"""
