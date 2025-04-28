from __future__ import annotations
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .events import ApiEventName
from .decorators import (
    REGISTERED_TASKS, REGISTERED_AGENTS,
    get_registered_tasks,
)
from .utils import sync_send
from .core_runner import CoreRunner
from .exceptions import BrixelAPIError, BrixelConnectionError


class _BaseClient:
    """
    Common mixin for sync & async clients.
    Sub-classes must implement the 2 low-level HTTP helpers:

        _post_json(...)          ← sync, returns Python dict
        _post_json_stream(...)   ← async iterator yielding JSON lines (only for async)
    """

    # ------------------------------------------------------------------ #
    #  ctor & shared state
    # ------------------------------------------------------------------ #
    def __init__(self,
                 api_key: Optional[str] = None,
                 api_base: str | None = None,
                 message_broker: Any | None = None) -> None:

        self.api_key  = api_key or os.getenv("BRIXEL_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Provide an API key or set the BRIXEL_API_KEY environment variable."
            )

        self.api_base = api_base or "https://api.brixel.ai/api/modules/api"
        self.broker   = message_broker
        self.runner   = CoreRunner()

    # ------------------------------------------------------------------ #
    #  helper: HTTP headers
    # ------------------------------------------------------------------ #
    def _headers(self) -> Dict[str, str]:
        return {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    # -------------  meta-information helpers (one implementation) ------ #
    def list_registered_tasks(self) -> List[str]:
        return [fn.__name__ for fn in REGISTERED_TASKS]

    def describe_registered_tasks(self) -> Dict[str, List[Dict[str, Any]]]:
        return get_registered_tasks()

    def list_registered_agents(self) -> List[str]:
        """
        Returns the list of IDs of agents declared via @agent.
        """

        return list(REGISTERED_AGENTS.keys())

    def describe_registered_agents(self, *, full: bool = False) -> List[Dict]:
        """
        Returns agent metadata and associated tasks.

        Args:
        full (bool): If True, includes full tasks instead of just their names.

        Returns:
        List[Dict]: A dictionary per agent.
        """

        tasks_by_agent = get_registered_tasks()
        return [
            {
                "id":          info["id"],
                "name":        info["name"],
                "description": info["description"],
                "tasks": (
                    tasks_by_agent.get(agent_id, [])
                    if full else
                    [t["name"] for t in tasks_by_agent.get(agent_id, [])]
                ),
            }
            for agent_id, info in REGISTERED_AGENTS.items()
        ]

    # ------------------------------------------------------------------ #
    #  broker publish (shared)
    # ------------------------------------------------------------------ #
    def _publish(self,
                 plan_id: str,
                 event: ApiEventName,
                 node: Optional[dict] = None,
                 details: Optional[dict] = None) -> None:
        if self.broker is None:
            return

        msg = {
            "plan_id":   plan_id,
            "event":     event.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if node:
            msg["node_index"] = node.get("index")
            msg["node_name"]  = node.get("name")
        if details:
            msg["details"]    = details

        sync_send(self.broker, msg)

    # ------------------------------------------------------------------ #
    #  list_modules (one implementation)
    # ------------------------------------------------------------------ #
    def list_modules(self) -> List[Dict[str, Any]]:
        """
        Fetches the list of modules from the API.
        Returns a list of modules with their metadata and minimal agent data.
        """
        return self._get("/list")


    # ------------------------------------------------------------------ #
    #  generate_plan (one implementation)
    # ------------------------------------------------------------------ #
    def generate_plan(self,
                      *,
                      message: str,
                      files: Optional[list] = None,
                      module_id: str | None = None,
                      context: str = "",
                      agents: Optional[list] = None,
                      auto_tasks: bool = True,
                      timeout: int = 30) -> Dict:

        agents = agents or []
        if auto_tasks:
            tasks_by_agent = get_registered_tasks()
            for agent_id, tasks in tasks_by_agent.items():
                if not tasks:
                    continue
                info = REGISTERED_AGENTS.get(agent_id, {
                    "id": agent_id,
                    "name": agent_id,
                    "description": "",
                })
                agents.append({
                    "id":          info["id"],
                    "name":        info["name"],
                    "description": info["description"],
                    "tasks":       tasks,
                })

        payload = {
            "module_id": module_id,
            "context":   context,
            "message":   message,
            "files":     files or [],
            "agents":    agents,
        }

        try:
            return self._post_json("/generate_plan", payload, timeout=timeout)
        except BrixelConnectionError:
            raise
        except Exception as exc:          # capture http-errors in subclass
            raise BrixelAPIError(str(exc)) from exc

    # ------------------------------------------------------------------ #
    #  SUB-CLASSES MUST OVERRIDE ↓
    # ------------------------------------------------------------------ #
    # sync version – returns Dict
    def _post_json(self, path: str, payload: dict, *, timeout: int) -> Dict: ...
    # sync or async override
    def _get(self, path: str, *, timeout: int = 10) -> Dict: ...

