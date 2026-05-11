"""shopping_agent — multimodal retail shopping agent, grocery-first.

This is the platform package. Public surface:
  - shopping_agent.config    : M-SEC config loader
  - shopping_agent.gateway   : M0 model gateway + role adapters
  - shopping_agent.events    : M-EVENTS event bus
  - shopping_agent.envelope  : M3 response envelope types
  - shopping_agent.specialists : M4 specialist registry
  - shopping_agent.conversation : M1 conversation state (stub)
  - shopping_agent.api       : FastAPI HTTP surface
  - shopping_agent.clients   : thin clients (CLI)
"""

__version__ = "0.1.0"
