import json, httpx
from typing import Dict, Optional

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
    #  generate_plan – async
    # ------------------------------------------------------------------ #

    async def generate_plan(
        self,
        *,
        message: str,
        files: Optional[list] = None,
        data: Optional[dict] = None,
        module_id: Optional[str] = None,
        context: str = "",
        agents: Optional[list] = None,
        auto_tasks: bool = True,
        timeout: int = 30,
    ) -> dict:
        payload = self._build_generate_plan_payload(
            message=message,
            files=files,
            data=data,
            module_id=module_id,
            context=context,
            agents=agents,
            auto_tasks=auto_tasks,
        )

        try:
            return await self._post_json("/generate_plan", payload, timeout=timeout)
        except BrixelConnectionError:
            raise
        except Exception as exc:
            raise BrixelAPIError(str(exc)) from exc

    async def _post_multipart_file_async(self, content: bytes, filename: str) -> dict:
        url, headers, files = self._prepare_upload_request(content, filename)
        headers = self._headers(json=False)
        
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, files=files)

        if response.status_code != 200:
            raise BrixelAPIError(f"Failed to upload file: {response.text}")

        return response.json()

    # ------------------------------------------------------------------ #
    #  execute_plan – async
    # ------------------------------------------------------------------ #

    async def execute_plan(self, plan: dict, files: list = None, data: dict = None) -> dict:
        return await self._run_execution_loop_async(plan, files, data)

    async def _run_local_async(self, context: dict, sub_plan: dict) -> dict:
        return self.runner.run_local_plan(context, sub_plan, self._publish)

    async def _run_external_async(self, context: dict, plan_id: str, sub_plan_id: str) -> dict:
        return await self._execute_external_plan(context, plan_id, sub_plan_id)


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
                    elif event == ApiEventName.ERROR:
                        raise Exception(msg.get("details",{}).get("error", "Unknown error from external agent"))
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
