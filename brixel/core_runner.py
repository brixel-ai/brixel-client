import ast, time
from typing import Any
from .events import ApiEventName
from .decorators import REGISTERED_TASKS
from .node_utils import apply_update_operator

class CoreRunner:

    @staticmethod
    def build_task_map(agent_id: str = None):
        return {
            fn.__name__: fn
            for fn in REGISTERED_TASKS
            if agent_id is None or getattr(fn, "_brixel_task", {}).get("agent_id", "default") == agent_id
        }

    

    @staticmethod
    def safe_eval(expr: str, ctx: dict):
        if expr is None:
            return None
        try:
            return ast.literal_eval(expr)
        except Exception:
            return eval(expr, {}, ctx)

    @staticmethod
    def add_output_to_display_outputs(node: dict, result: Any, ctx: dict):
        if node.get("options", {}).get("display_output"):
            if not ctx.get("displayed_outputs"):
                ctx["displayed_outputs"] = []
            ctx["displayed_outputs"].append({
                "index": node["index"],
                "output": result
            })

    def _evaluate_expression(self, expr, context):
        try:
            if expr is None:
                return expr
            return ast.literal_eval(expr)
        except Exception:
            try:
                return eval(expr, {}, context)
            except Exception:
                if expr in context:
                    return context[expr]
                raise Exception(f"Can't evaluate: {expr}")
    
    def _execute_if_chain(self, sub_id, chain, context, task_map, publish):
        for node in chain:
            try:
                name = node["name"]
                if name in ("_if", "_elif"):
                    cond = self._evaluate_expression(node["inputs"]["condition"], context)
                    if cond:
                        for child in node["inputs"].get("children", []):
                            self._execute_node(sub_id, child, context, task_map, publish)
                        return
                elif name == "_else":
                    for child in node["inputs"].get("children", []):
                        self._execute_node(sub_id, child, context, task_map, publish)
                    return
            except Exception as exc:
                publish(sub_id, ApiEventName.ERROR, node, {"error": str(exc)})
                raise


    def _execute_nodes(self, sub_id, nodes, context, task_map, publish):
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
                self._execute_if_chain(sub_id, chain, context, task_map, publish)
            else:
                self._execute_node(sub_id, node, context, task_map, publish)
                idx += 1
                if "_return" in context:
                    break

    def _execute_node(self, sub_id, node, context, task_map, publish):
        try:
            publish(sub_id, ApiEventName.NODE_START, node)
            name = node["name"]
            if name == "_assign":
                value = self._evaluate_expression(node["inputs"]["value"], context)
                context[node["output"]] = value
                self.add_output_to_display_outputs(node, value, context)
                publish(sub_id, ApiEventName.NODE_FINISH, node, {"value": value})

            elif name == "_append":
                value = self._evaluate_expression(node["inputs"]["value"], context)
                context.setdefault(node["output"], []).append(value)
                self.add_output_to_display_outputs(node, value, context)
                publish(sub_id, ApiEventName.NODE_FINISH, node, {"item": value})

            elif name == "_return":
                value = self._evaluate_expression(node["inputs"]["value"], context)
                context["_return"] = value
                self.add_output_to_display_outputs(node, value, context)
                publish(sub_id, ApiEventName.NODE_FINISH, node, {"output": value})
                return value
            
            elif name == "_break":
                context["_break_flag"] = True
                publish(sub_id, ApiEventName.NODE_FINISH, node)

            elif name == "_raise":
                publish(sub_id, ApiEventName.NODE_FINISH, node, {"exception": node["inputs"]["exception"]})
                raise Exception(node["inputs"]["exception"])
            
            elif name == "_update":
                op = node["inputs"]["operator"]
                value = self._evaluate_expression(node["inputs"]["value"], context)
                var_name = node["output"]

                if var_name not in context:
                    raise Exception(f"Variable '{var_name}' not defined for update")

                context[var_name] = apply_update_operator(context[var_name], op, value)
                self.add_output_to_display_outputs(node, context[var_name], context)
                publish(sub_id, ApiEventName.NODE_FINISH, node, {"output": context[var_name]})

            elif name == "_for":
                item_name  = node["inputs"]["item"]
                index_var  = node["inputs"].get("index")
                key_var    = node["inputs"].get("key")
                base_iter  = self._evaluate_expression(node["inputs"]["iterable"], context)

                if key_var is not None:
                    # for key, val in data.items()
                    loop_iterable = base_iter.items()
                else:
                    # for val in data or for idx, val in enumerate(data)
                    loop_iterable = base_iter

                for idx, element in enumerate(loop_iterable):
                    publish(sub_id, ApiEventName.FOR_ITERATION_START, node, {"iteration_index": idx, "iterable_length": len(base_iter)})
                    if key_var is not None:
                        k, v = element
                        context[key_var]  = k
                        context[item_name] = v
                    else:
                        context[item_name] = element
                        if index_var is not None:
                            context[index_var] = idx
                    self._execute_nodes(sub_id, node.get("inputs", {}).get("children", []), context, task_map, publish)

                    if context.get("_break_flag"):
                        context["_break_flag"] = False
                        break
                    if "_return" in context:
                        publish(sub_id, ApiEventName.NODE_FINISH, node)
                        return context["_return"]
                publish(sub_id, ApiEventName.NODE_FINISH, node)

            elif name == "_while":
                condition = node["inputs"]["condition"]
                children = node["inputs"].get("children", [])
                counter = 0
                start = time.time()
                while self._evaluate_expression(condition, context):
                    publish(sub_id, ApiEventName.FOR_ITERATION_START, node, {"iteration_index": counter})
                    self._execute_nodes(sub_id, children, context, task_map, publish)
                    if context.get("_break_flag"):
                        context["_break_flag"] = False
                        publish(sub_id, ApiEventName.NODE_FINISH, node, {"iterations": counter, "duration": time.time()-start})
                        return
                    if "_return" in context:
                        publish(sub_id, ApiEventName.NODE_FINISH, node, {"iterations": counter, "duration": time.time()-start})
                        return context["_return"]
                    counter +=1
                publish(sub_id, ApiEventName.NODE_FINISH, node, {"iterations": counter, "duration": time.time()-start})

            else:
                task_fn = task_map.get(name)
                if not task_fn:
                    raise Exception(f"Function '{name}' not found")
                inputs = {
                    k: self._evaluate_expression(v, context)
                    for k, v in node["inputs"].items()
                }
                result = task_fn(**inputs)
                publish(sub_id, ApiEventName.NODE_FINISH, node, {"output": result})
                if "output" in node:
                    context[node["output"]] = result
                self.add_output_to_display_outputs(node, result, context)
                return result
        except Exception as e:
            publish(sub_id, ApiEventName.ERROR, node, {"error": str(e)})
            raise e
            
    def run_local_plan(self, context, sub_plan, publish, agent_id=None):
        task_map = self.build_task_map(agent_id)
        sub_id = sub_plan["id"]
        nodes = sub_plan["plan"]
        self._execute_nodes(sub_id, nodes, context, task_map, publish)
        return context.get("_return", None)