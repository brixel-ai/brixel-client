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
    def _headers(self, *, json: bool = True) -> Dict[str, str]:
        headers = {
            "x-api-key": self.api_key,
            "Accept": "application/json",
        }
        if json:
            headers["Content-Type"] = "application/json"
        return headers

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
    
    def _prepare_upload_request(self, content: bytes, filename: str):
        url = f"{self.api_base}/upload_file"
        headers = self._headers(json=False)
        files = {
            "file": (filename, content),
        }
        return url, headers, files
    
    def upload_content(self, content: bytes, filename: str) -> dict:
        return self._post_multipart_file(content, filename)

    async def async_upload_content(self, content: bytes, filename: str) -> dict:
        return await self._post_multipart_file_async(content, filename)

    def _post_multipart_file(self, path: str, content: bytes, filename: str) -> dict:
        raise NotImplementedError

    async def _post_multipart_file_async(self, path: str, content: bytes, filename: str) -> dict:
        raise NotImplementedError

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



    def _build_generate_plan_payload(
        self,
        *,
        message: str,
        files: Optional[list] = None,
        module_id: Optional[str] = None,
        context: str = "",
        agents: Optional[list] = None,
        auto_tasks: bool = True,
    ) -> dict:
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

        return {
            "module_id": module_id,
            "context":   context,
            "message":   message,
            "files":     files or [],
            "agents":    agents,
        }
    
    def _run_local(self, context: dict, sub_plan: dict) -> dict:
        raise NotImplementedError

    async def _run_local_async(self, context: dict, sub_plan: dict) -> dict:
        raise NotImplementedError

    def _run_external(self, context: dict, plan_id: str, sub_plan_id: str) -> dict:
        raise NotImplementedError

    async def _run_external_async(self, context: dict, plan_id: str, sub_plan_id: str) -> dict:
        raise NotImplementedError
    

    def _build_execution_context(self, sub_plan: dict, global_context: dict, files: list) -> dict:
        context = {"files": files or []}
        if sub_plan.get("inputs"):
            for sp_input in sub_plan["inputs"]:
                context[sp_input["name"]] = global_context.get(sp_input["from"])
        return context


    def _run_execution_loop(self, plan: dict, files: list = None) -> dict:
        plan_id = plan["plan_id"]
        global_context = {}

        for sub_plan in plan.get("sub_plans", []):
            sub_id = sub_plan["id"]
            agent_type = sub_plan["agent"]["type"]
            context = self._build_execution_context(sub_plan, global_context, files)

            self._publish(sub_id, ApiEventName.SUB_PLAN_START)
            if agent_type == "local":
                result = self._run_local(context, sub_plan)
            else:
                result = self._run_external(context, plan_id, sub_id)
            global_context[sub_id] = result
            self._publish(sub_id, ApiEventName.SUB_PLAN_DONE)

        self._publish(plan_id, ApiEventName.DONE)
        return global_context

    async def _run_execution_loop_async(self, plan: dict, files: list = None) -> dict:
        plan_id = plan["plan_id"]
        global_context = {}

        for sub_plan in plan.get("sub_plans", []):
            sub_id = sub_plan["id"]
            agent_type = sub_plan["agent"]["type"]
            context = self._build_execution_context(sub_plan, global_context, files)

            self._publish(sub_id, ApiEventName.SUB_PLAN_START)
            if agent_type == "local":
                result = await self._run_local_async(context, sub_plan)
            else:
                result = await self._run_external_async(context, plan_id, sub_id)
            global_context[sub_id] = result
            self._publish(sub_id, ApiEventName.SUB_PLAN_DONE)

        self._publish(plan_id, ApiEventName.DONE)
        return global_context

    # ------------------------------------------------------------------ #
    #  SUB-CLASSES MUST OVERRIDE ↓
    # ------------------------------------------------------------------ #
    # sync version – returns Dict
    def _post_json(self, path: str, payload: dict, *, timeout: int) -> Dict: ...
    # sync or async override
    def _get(self, path: str, *, timeout: int = 10) -> Dict: ...

