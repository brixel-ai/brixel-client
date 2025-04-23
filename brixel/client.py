import os
from datetime import datetime, time, timezone
import json
import ast
import requests

from brixel.node_utils import apply_update_operator

from .events import ApiEventName
from .utils import sync_send
from .exceptions import BrixelAPIError, BrixelConnectionError
from .decorators import get_registered_tasks, REGISTERED_TASKS, get_registered_tasks, REGISTERED_AGENTS


class BrixelClient:
    def __init__(self, api_key: str = None, message_broker=None):
        self.api_key = api_key or os.getenv("BRIXEL_API_KEY")
        if not self.api_key:
            raise ValueError("API key is required. Provide it via the 'api_key' parameter or set the 'BRIXEL_API_KEY' environment variable.")
        self.api_base_url = "https://api.brixel.ai/api/modules/api"
        self.message_broker = message_broker
        self.api_base_url = "http://localhost:8000/api/modules/api"  # For local testing


    def list_registered_tasks(self):
        return [fn.__name__ for fn in REGISTERED_TASKS]


    def describe_registered_tasks(self):
        return get_registered_tasks()


    def list_registered_agents(self):
        """
        Retourne la liste des IDs des agents déclarés via @agent.
        """
        return list(REGISTERED_AGENTS.keys())

    def describe_registered_agents(self, full: bool = False):
        """
        Retourne les métadonnées des agents et les tâches associées.
        
        Args:
            full (bool): Si True, inclut les tâches complètes au lieu de juste leurs noms.

        Returns:
            List[Dict]: Un dictionnaire par agent.
        """
        agents = []
        tasks_by_agent = get_registered_tasks()

        for agent_id, info in REGISTERED_AGENTS.items():
            agents.append({
                "id": info["id"],
                "name": info["name"],
                "description": info["description"],
                "tasks": tasks_by_agent.get(agent_id, []) if full else [
                    task["name"] for task in tasks_by_agent.get(agent_id, [])
                ]
            })

        return agents

    
    def _get_headers(self):
        return {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
    
    

    def _publish(self, plan_id, event: ApiEventName, node: dict = None, details: dict = None):
        if self.message_broker is None:
            return

        msg = {
            "plan_id": plan_id,
            "event": event.value,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        if node:
            msg["node_index"] = node.get("index")
            msg["node_name"] = node.get("name")

        if details:
            msg["details"] = details

        sync_send(self.message_broker, msg)

    def __build_task_map(self):
        return {fn.__name__: fn for fn in REGISTERED_TASKS}
    

    def _evaluate_expression(self, expr, context):
        try:
            return ast.literal_eval(expr)
        except Exception:
            try:
                return eval(expr, {}, context)
            except Exception:
                if expr in context:
                    return context[expr]
                raise Exception(f"Can't evaluate: {expr}")
    
    def _execute_if_chain(self, sub_id, chain, context, task_map):
        for node in chain:
            name = node["name"]
            if name in ("_if", "_elif"):
                cond = self._evaluate_expression(node["inputs"]["condition"], context)
                if cond:
                    for child in node["inputs"].get("children", []):
                        self._execute_node(sub_id, child, context, task_map)
                    return
            elif name == "_else":
                for child in node["inputs"].get("children", []):
                    self._execute_node(sub_id, child, context, task_map)
                return


    def _execute_nodes(self, sub_id, nodes, context, task_map):
        idx = 0
        while idx < len(nodes):
            node = nodes[idx]
            name = node["name"]
            if name in ("_if", "_elif", "_else"):
                # collect chain
                chain = []
                while idx < len(nodes) and nodes[idx]["name"] in ("_if", "_elif", "_else"):
                    chain.append(nodes[idx])
                    idx += 1
                self._execute_if_chain(sub_id, chain, context, task_map)
            else:
                self._execute_node(sub_id, node, context, task_map)
                idx += 1
                if "_return" in context:
                    break

    def _execute_node(self, sub_id, node, context, task_map):
        try:
            self._publish(sub_id, ApiEventName.NODE_START, node)
            name = node["name"]
            if name == "_assign":
                value = self._evaluate_expression(node["inputs"]["value"], context)
                context[node["output"]] = value
                self._publish(sub_id, ApiEventName.NODE_FINISH, node, {"value": value})

            elif name == "_append":
                value = self._evaluate_expression(node["inputs"]["value"], context)
                context.setdefault(node["output"], []).append(value)
                self._publish(sub_id, ApiEventName.NODE_FINISH, node, {"item": value})

            elif name == "_return":
                value = self._evaluate_expression(node["inputs"]["value"], context)
                context["_return"] = value
                self._publish(sub_id, ApiEventName.NODE_FINISH, node, {"output": value})
                return value
            
            elif name == "_break":
                context["_break_flag"] = True
                self._publish(sub_id, ApiEventName.NODE_FINISH, node)

            elif name == "_raise":
                self._publish(sub_id, ApiEventName.NODE_FINISH, node, {"exception": node["inputs"]["exception"]})
                raise Exception(node["inputs"]["exception"])
            
            elif name == "_update":
                op = node["inputs"]["operator"]
                value = self._evaluate_expression(node["inputs"]["value"], context)
                var_name = node["output"]

                if var_name not in context:
                    raise Exception(f"Variable '{var_name}' not defined for update")

                context[var_name] = apply_update_operator(context[var_name], op, value)
                self._publish(sub_id, ApiEventName.NODE_FINISH, node, {"output": context[var_name]})

            elif name == "_for":
                iterable = self._evaluate_expression(node["inputs"]["iterable"], context)
                item_var = node["inputs"]["item"]
                children = node["inputs"].get("children", [])
                for idx, item in enumerate(iterable):
                    context[item_var] = item
                    self._publish(sub_id, ApiEventName.FOR_ITERATION_START, node, {"iteration_index": idx, "iterable_length": len(iterable)})
                    self._execute_nodes(sub_id, children, context, task_map)
                    if context.get("_break_flag"):
                        context["_break_flag"] = False
                        break
                    if "_return" in context:
                        self._publish(sub_id, ApiEventName.NODE_FINISH, node)
                        return context["_return"]
                self._publish(sub_id, ApiEventName.NODE_FINISH, node)

            elif name == "_while":
                condition = node["inputs"]["condition"]
                children = node["inputs"].get("children", [])
                counter = 0
                start = time.time()
                while self._evaluate_expression(condition, context):
                    self._publish(sub_id, ApiEventName.FOR_ITERATION_START, node, {"iteration_index": counter})
                    self._execute_nodes(sub_id, children, context, task_map)
                    if context.get("_break_flag"):
                        context["_break_flag"] = False
                        self._publish(sub_id, ApiEventName.NODE_FINISH, node, {"iterations": counter, "duration": time.time()-start})
                        return
                    if "_return" in context:
                        self._publish(sub_id, ApiEventName.NODE_FINISH, node, {"iterations": counter, "duration": time.time()-start})
                        return context["_return"]
                    counter +=1
                self._publish(sub_id, ApiEventName.NODE_FINISH, node, {"iterations": counter, "duration": time.time()-start})

            else:
                task_fn = task_map.get(name)
                if not task_fn:
                    raise Exception(f"Function '{name}' not found")
                inputs = {
                    k: self._evaluate_expression(v, context)
                    for k, v in node["inputs"].items()
                }
                result = task_fn(**inputs)
                self._publish(sub_id, ApiEventName.NODE_FINISH, node, {"output": result})
                if "output" in node:
                    context[node["output"]] = result
                return result
        except Exception as e:
            self._publish(sub_id, ApiEventName.ERROR, node, {"error": str(e)})
            raise e
               
    def generate_plan(self, message: str, files: list = None, module_id: str = None, context: str = "", agents: list = None, auto_tasks: bool = True) -> dict:
        if not agents:
            agents = []

        if auto_tasks:
            tasks_by_agent = get_registered_tasks()

            for agent_id, tasks in tasks_by_agent.items():
                agent_info = REGISTERED_AGENTS.get(agent_id, {
                    "id": agent_id,
                    "name": agent_id,
                    "description": "No description provided."
                })
                agents.append({
                    "id": agent_info["id"],
                    "name": agent_info["name"],
                    "description": agent_info["description"],
                    "tasks": tasks
                })
        payload = {
            "module_id": module_id,
            "context": context,
            "message": message,
            "files": files or [],
            "agents": agents or []
        }

        try:
            response = requests.post(
                self.api_base_url + "/generate_plan",
                headers=self._get_headers(),
                data=json.dumps(payload),
                timeout=30
            )
            response.raise_for_status()
            return response.json()

        except requests.exceptions.HTTPError as errh:
            raise BrixelAPIError(errh.response.text)
        except requests.exceptions.ConnectionError:
            raise BrixelConnectionError("Error connecting to the server")
        except requests.exceptions.Timeout:
            raise BrixelConnectionError("Connexion timeout")
        except Exception as exc:
            raise BrixelAPIError(str(exc))

    def _execute_local_plan(self, context, sub_plan):
        task_map = self.__build_task_map()
        sub_id = sub_plan["id"]
        nodes = sub_plan["plan"]
        self._execute_nodes(sub_id, nodes, context, task_map)
        return context.get("_return", None)

    def _execute_external_plan(self, context, plan_id, sub_plan_id):
        url = f"{self.api_base_url}/{plan_id}/sub_plan/{sub_plan_id}/execute"
        response = requests.post(url, headers=self._get_headers(), timeout=60)
        response.raise_for_status()
        return response.json()

    def execute_plan(self, plan: dict, files: list = None) -> dict:
        context = {
            "files": files or []
        }
        plan_id = plan["plan_id"]

        for sub_plan in plan.get("sub_plans", []):
            sub_id = sub_plan["id"]
            agent_type = sub_plan["agent"]["type"]

            if agent_type == "local":
                print(f"⚙️ Executing local sub-plan {sub_id}")
                self._execute_local_plan(context, sub_plan)
            else:
                print(f"🌐 Executing external sub-plan {sub_id}")
                self._execute_external_plan(context, plan_id, sub_id)
            self._publish(sub_id, ApiEventName.SUB_PLAN_DONE)
        self._publish(sub_id, ApiEventName.DONE)