
import json
from typing import Dict
import requests

from brixel.base_client import _BaseClient

from .events import ApiEventName
from .utils import safe_enum_value
from .exceptions import BrixelAPIError, BrixelConnectionError


class BrixelClient(_BaseClient):
    """Synchronous interface (requests)."""

    # ------------ override low-level HTTP helpers ---------------------- #
    def _post_json(self, path: str, payload: dict, *, timeout: int = 30) -> Dict:
        url = f"{self.api_base}{path}"
        try:
            r = requests.post(url, headers=self._headers(),
                              data=json.dumps(payload), timeout=timeout)
            r.raise_for_status()
            return r.json()
        except requests.exceptions.ConnectionError as e:
            raise BrixelConnectionError(str(e)) from e
        except requests.exceptions.Timeout:
            raise BrixelConnectionError("Timeout")
        except requests.exceptions.HTTPError as e:
            raise BrixelAPIError(e.response.text) from e
    
    def _get(self, path: str, *, timeout: int = 10) -> Dict:
        url = f"{self.api_base}{path}"
        try:
            r = requests.get(url, headers=self._headers(), timeout=timeout)
            r.raise_for_status()
            return r.json()
        except requests.exceptions.ConnectionError as e:
            raise BrixelConnectionError(str(e)) from e
        except requests.exceptions.Timeout:
            raise BrixelConnectionError("Timeout")
        except requests.exceptions.HTTPError as e:
            raise BrixelAPIError(e.response.text) from e

    def execute_plan(self, plan: dict, files: list = None) -> dict:
        
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
                result = self._execute_external_plan(context, plan_id, sub_id)
            
            global_context[sub_id] = result
            self._publish(sub_id, ApiEventName.SUB_PLAN_DONE)
        self._publish(sub_id, ApiEventName.DONE)
    

    def _execute_external_plan(self, context, plan_id, sub_plan_id):
        url = f"{self.api_base}/plan/{plan_id}/sub_plan/{sub_plan_id}/execute"
        payload = {
            "inputs": context,
            "stream": False
        }

        response = requests.post(
            url,
            headers=self._headers(),
            json=payload,
            timeout=60
        )
        response.raise_for_status()

        data = response.json()
        if data.get("messages"):
            for msg in data["messages"]:
                event = safe_enum_value(ApiEventName, msg["event"])
                if event in (ApiEventName.DONE, ApiEventName.SUB_PLAN_START, ApiEventName.SUB_PLAN_DONE, None):
                    continue
                else:
                    node = {
                        "index": msg.get("node_index"),
                        "name": msg.get("node_name")
                    } if msg.get("node_index") else None
                self._publish(msg["plan_id"], event, node, msg.get("details"))
        return data.get("output", None)
