import inspect
import warnings
from typing import Callable, Dict, List, Any, get_type_hints
from .docstring_parser import parse_docstring

REGISTERED_TASKS: List[Callable] = []
REGISTERED_AGENTS = {}

def task(_func=None, *, agent_id: str = None, display_output: bool = False):
    def decorator(fn):
        fn._brixel_task = {"agent_id": agent_id or "default", "display_output": display_output or False}
        REGISTERED_TASKS.append(fn)
        return fn

    if _func is None:
        return decorator  # used as @task(...)
    else:
        return decorator(_func)  # used as @task


def agent(id: str):
    def wrapper(cls):
        REGISTERED_AGENTS[id] = {
            "id": id,
            "name": getattr(cls, "name", id),
            "description": getattr(cls, "description", ""),
            "context": getattr(cls, "context", ""),
        }
        return cls
    return wrapper


def validate_registered_agents_and_tasks():
    used_agent_ids = {getattr(fn, "_brixel_task", {}).get("agent_id", "default") for fn in REGISTERED_TASKS}
    defined_agent_ids = set(REGISTERED_AGENTS.keys())

    missing = used_agent_ids - defined_agent_ids
    if missing:
        print("WARNING: The following agent_ids are used in @task but not defined with @agent:")
        for agent_id in sorted(missing):
            print(f" - '{agent_id}'")
    else:
        print("All @task agent_ids have corresponding @agent definitions.")

def get_registered_tasks() -> Dict[str, List[Dict[str, Any]]]:
    tasks_by_agent = {}

    for fn in REGISTERED_TASKS:
        sig = inspect.signature(fn)
        hints = get_type_hints(fn)
        meta = getattr(fn, "_brixel_task", {})
        agent_id = meta.get("agent_id", "default")
        display_output = meta.get("display_output", False)
        doc = fn.__doc__ or ""
        parsed_doc = parse_docstring(doc)

        if not doc:
            warnings.warn(f"[{fn.__name__}] No docstring detected.", stacklevel=2)

        inputs = []
        for name, param in sig.parameters.items():
            param_type = hints.get(name, str)
            doc_info = parsed_doc["args"].get(name, {})
            if not doc_info:
                warnings.warn(f"[{fn.__name__}] No description for the arg '{name}'.", stacklevel=2)
            inputs.append({
                "name": name,
                "type": doc_info.get("type", param_type.__name__),
                "description": doc_info.get("desc", ""),
                "required": param.default is inspect.Parameter.empty
            })

        return_hint = hints.get("return", None)
        return_info = parsed_doc.get("return", {})

        has_output = return_hint not in [None, type(None)] or bool(return_info)

        task = {
            "name": fn.__name__,
            "description": parsed_doc["description"],
            "configuration": {
                "inputs": inputs
            },
            "options": {
                "display_output": display_output
            }
        }

        if has_output:
            if not return_info:
                warnings.warn(f"[{fn.__name__}] No description for the return.", stacklevel=2)

            task["configuration"]["output"] = {
                "type": return_info.get("type", return_hint.__name__ if return_hint else "string"),
                "description": return_info.get("desc", "")
            }

        tasks_by_agent.setdefault(agent_id, []).append(task)

    return tasks_by_agent