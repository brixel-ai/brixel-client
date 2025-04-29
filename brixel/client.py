
import json
import os
from typing import Dict, Optional
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



    def generate_plan(
        self,
        *,
        message: str,
        files: Optional[list] = None,
        module_id: Optional[str] = None,
        context: str = "",
        agents: Optional[list] = None,
        auto_tasks: bool = True,
        timeout: int = 30,
    ) -> dict:
        payload = self._build_generate_plan_payload(
            message=message,
            files=files,
            module_id=module_id,
            context=context,
            agents=agents,
            auto_tasks=auto_tasks,
        )

        try:
            return self._post_json("/generate_plan", payload, timeout=timeout)
        except BrixelConnectionError:
            raise
        except Exception as exc:
            raise BrixelAPIError(str(exc)) from exc
        
    def _post_multipart_file(self, content: bytes, filename: str) -> dict:
        url, headers, files = self._prepare_upload_request(content, filename)
        headers = self._headers(json=False)
        response = requests.post(url, headers=headers, files=files)

        if response.status_code != 200:
            raise BrixelAPIError(f"Failed to upload file: {response.text}")

        return response.json()
    
    def execute_plan(self, plan: dict, files: list = None) -> dict:
        return self._run_execution_loop(plan, files)

    def _run_local(self, context: dict, sub_plan: dict) -> dict:
        return self.runner.run_local_plan(context, sub_plan, self._publish)

    def _run_external(self, context: dict, plan_id: str, sub_plan_id: str) -> dict:
        return self._execute_external_plan(context, plan_id, sub_plan_id)
    

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
                elif event == ApiEventName.ERROR:
                    raise Exception(msg.get("details",{}).get("error", "Unknown error from external agent"))
                else:
                    node = {
                        "index": msg.get("node_index"),
                        "name": msg.get("node_name")
                    } if msg.get("node_index") else None
                self._publish(msg["plan_id"], event, node, msg.get("details"))
        return data.get("output", None)
