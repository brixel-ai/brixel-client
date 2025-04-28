import json, httpx
from typing import Dict

from brixel.base_client import _BaseClient
from brixel.exceptions import BrixelAPIError, BrixelConnectionError
from .events import ApiEventName
from .utils import safe_enum_value

class AsyncBrixelClient(_BaseClient):
    """Async interface (httpx.AsyncClient, streaming by default)."""

     # ---------- override async HTTP helper (awaitable) ----------------- #
    async def _post_json(self, path: str, payload: dict,
                         *, timeout: int = 30) -> Dict:
        url = f"{self.api_base}{path}"
        async with httpx.AsyncClient(timeout=timeout) as cli:
            try:
                r = await cli.post(url, headers=self._headers(), json=payload)
                r.raise_for_status()
                return r.json()
            except httpx.ConnectError as e:
                raise BrixelConnectionError(str(e)) from e
            except httpx.TimeoutException:
                raise BrixelConnectionError("Timeout")
            except httpx.HTTPStatusError as e:
                raise BrixelAPIError(str(e.response.text)) from e

    async def _get(self, path: str, *, timeout: int = 10) -> Dict:
        url = f"{self.api_base}{path}"
        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                r = await client.get(url, headers=self._headers())
                r.raise_for_status()
                return r.json()
            except httpx.ConnectError as e:
                raise BrixelConnectionError(str(e)) from e
            except httpx.TimeoutException:
                raise BrixelConnectionError("Timeout")
            except httpx.HTTPStatusError as e:
                raise BrixelAPIError(str(e.response.text)) from e
    
    # ------------------------------------------------------------------ #
    #  execute_plan – async
    # ------------------------------------------------------------------ #

    async def execute_plan(self, plan: dict, files: list = None) -> dict:
        
        global_context = {}
        plan_id = plan["plan_id"]

        for sub_plan in plan.get("sub_plans", []):
            sub_id = sub_plan["id"]
            agent_type = sub_plan["agent"]["type"]

            context = {
                "files": files or []
            }

            if sub_plan.get('inputs'):
                for sp_input in sub_plan.get("inputs", []):
                    context[sp_input["name"]] = global_context.get(sp_input["from"])
            
            self._publish(sub_id, ApiEventName.SUB_PLAN_START)
            if agent_type == "local":
                result = self.runner.run_local_plan(context, sub_plan, self._publish)
            else:
                result = await self._execute_external_plan(context, plan_id, sub_id)
            
            global_context[sub_id] = result
            self._publish(sub_id, ApiEventName.SUB_PLAN_DONE)
        self._publish(sub_id, ApiEventName.DONE)


    async def _execute_external_plan(self, context, plan_id, sub_plan_id):
        url = f"{self.api_base}/plan/{plan_id}/sub_plan/{sub_plan_id}/execute"
        async with httpx.AsyncClient(timeout=60) as client:
            async with client.stream(
                "POST", url,
                headers=self._headers(),
                json={"inputs": context, "stream": True}
            ) as resp:
                resp.raise_for_status()
                ret = None
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    msg = json.loads(line)
                    event = safe_enum_value(ApiEventName, msg["event"])
                    if not event:
                        continue
                    elif event == ApiEventName.DONE:
                        ret = msg.get("details", {}).get("output")
                    elif event in (ApiEventName.SUB_PLAN_START, ApiEventName.SUB_PLAN_DONE, None):
                        continue
                    else:
                        node = {"index": msg.get("node_index"),
                                "name":  msg.get("node_name")} if msg.get("node_index") else None
                        self._publish(msg["plan_id"],
                                    event,
                                    node,
                                    msg.get("details"))
                return ret
        return None
