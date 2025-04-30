# brixel/server.py
from __future__ import annotations

import hmac, hashlib, json, os
from datetime import datetime, timezone
import time
from typing import Any, Dict, Optional, List

from .core_runner   import CoreRunner
from .decorators    import REGISTERED_AGENTS, get_registered_tasks           # already returns nice structure
from .events        import ApiEventName
from .utils         import sync_send                      # same helper as the client


# --------------------------------------------------------------------------- #
#  small helpers for HMAC-SHA256 signatures
# --------------------------------------------------------------------------- #
def _canonical(data: Dict) -> bytes:
    """
    Deterministic JSON serialisation (no spaces, sorted keys).
    """
    return json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

def _verify_signature(sub_plan: Dict, signature: str, secret: str) -> None:
    """Raises ValueError if the signature is missing or invalid."""
    if not signature:
        raise ValueError("Missing 'signature' field in sub-plan")

    expected = hmac.new(secret.encode(), _canonical(sub_plan), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise ValueError("Invalid signature")


# --------------------------------------------------------------------------- #
#  The actual server class
# --------------------------------------------------------------------------- #
class BrixelServer:
    """
    Lightweight helper meant to be called by a *remote* Brixel instance.
    It executes **one** local sub-plan and returns its output.

    Parameters
    ----------
    secret : str | None
        Shared secret used to verify the `signature` field of the sub-plan.
        If *None*, no signature check is performed (⚠️  not recommended).
        The value can also be supplied via the `BRIXEL_SERVER_SECRET`
        environment variable.
    message_broker : Any | None
        Same idea as on the client side (list, asyncio.Queue, websocket…).
    """

    # ------------------------------------------------------------------ #
    def __init__(
        self,
        *,
        secret: str | None = None,
        message_broker: Any | None = None,
        agent_id: str | None = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.secret  = secret or os.getenv("BRIXEL_SERVER_SECRET")
        self.broker  = message_broker
        self.agent_id = agent_id
        self.options = options or {}
        self.runner  = CoreRunner()

    # ------------------------------------------------------------------ #
    #  public – configuration helper
    # ------------------------------------------------------------------ #    
    def get_configuration(self) -> Dict:
        """
        Return agent metadata and associated tasks.
        """

        tasks_by_agent = get_registered_tasks()

        if self.agent_id and self.agent_id in REGISTERED_AGENTS:
            info = REGISTERED_AGENTS[self.agent_id]
            agent_id = self.agent_id
        else:
            first_item = next(iter(REGISTERED_AGENTS.items()), None)
            if not first_item:
                return None
            agent_id, info = first_item

        return {
            "id":          info["id"],
            "name":        info["name"],
            "description": info["description"],
            "context":     info["context"],
            "tasks":       tasks_by_agent.get(agent_id, []),
            "options":     self.options
        }



    # ------------------------------------------------------------------ #
    #  public – execute ONE sub-plan
    # ------------------------------------------------------------------ #
    def execute_plan(
        self,
        sub_id: int,
        sub_plan: List[Dict[str, Any]],
        signature: Optional[str] = None,
        inputs: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Run *one* local sub-plan and return its `output`.

        Raises
        ------
        ValueError  – if the agent is not local or the signature is wrong.
        """

        # 1) signature check (if a secret is configured)
        if self.secret:
            _verify_signature(sub_plan, signature, self.secret)

        if not inputs:
            inputs = {}

        # 3) initial execution context
        ctx: Dict[str, Any] = {**inputs}

        # 4) run
        start = time.time()
        self._publish(sub_id, ApiEventName.SUB_PLAN_START)
        try:
            result = self.runner.run_local_plan(ctx, {"id": sub_id, "plan": sub_plan}, self._publish, self.agent_id)
        except Exception as exc:
            self._publish(sub_id, ApiEventName.EXECUTION_INTERRUPTED, details=
            {
                "reason": {
                    "error": str(exc)
                }
            })
            raise
        self._publish(sub_id, ApiEventName.SUB_PLAN_DONE, details={
            "plan_id": sub_id,
            "execution_time": time.time() - start,
        })

        self._publish(sub_id, ApiEventName.DONE, details={
            "execution_time": time.time() - start,
            "finish_reason": "success",
            "displayed_outputs": ctx.get("displayed_outputs", []),
            "output": result,
        })

        return result
    # ------------------------------------------------------------------ #
    #  internal broker helper (same pattern as in the client)
    # ------------------------------------------------------------------ #
    def _publish(
        self,
        plan_id: str,
        event: ApiEventName,
        node: Optional[dict] = None,
        details: Optional[dict] = None,
    ) -> None:
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
            msg["details"] = details

        sync_send(self.broker, msg)
