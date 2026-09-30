"""Mock provider-integration service.

This is the HTTP layer the agent's tools talk to instead of reading SQLite
directly. It stands in for the gateway a lender would put in front of real
vendor APIs (SentiLink, Socure, LexisNexis and friends) — which are all HTTP
services taking identity attributes, not internal row ids.
"""
