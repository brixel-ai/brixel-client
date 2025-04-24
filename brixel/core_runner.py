import ast, time
from .events import ApiEventName
from .decorators import REGISTERED_TASKS
from .node_utils import apply_update_operator

class CoreRunner:

    @staticmethod
    def build_task_map():
        return {fn.__name__: fn for fn in REGISTERED_TASKS}
    

    @staticmethod
    def safe_eval(expr: str, ctx: dict):
        if expr is None:
            return None
        try:
            return ast.literal_eval(expr)
        except Exception:
            return eval(expr, {}, ctx)


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
                publish(sub_id, ApiEventName.NODE_FINISH, node, {"value": value})

            elif name == "_append":
                value = self._evaluate_expression(node["inputs"]["value"], context)
                context.setdefault(node["output"], []).append(value)
                publish(sub_id, ApiEventName.NODE_FINISH, node, {"item": value})

            elif name == "_return":
                value = self._evaluate_expression(node["inputs"]["value"], context)
                context["_return"] = value
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
                publish(sub_id, ApiEventName.NODE_FINISH, node, {"output": context[var_name]})

            elif name == "_for":
                iterable = self._evaluate_expression(node["inputs"]["iterable"], context)
                item_var = node["inputs"]["item"]
                children = node["inputs"].get("children", [])
                for idx, item in enumerate(iterable):
                    context[item_var] = item
                    publish(sub_id, ApiEventName.FOR_ITERATION_START, node, {"iteration_index": idx, "iterable_length": len(iterable)})
                    self._execute_nodes(sub_id, children, context, task_map, publish)
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
                return result
        except Exception as e:
            publish(sub_id, ApiEventName.ERROR, node, {"error": str(e)})
            raise e
            
    def run_local_plan(self, context, sub_plan, publish):
        task_map = self.build_task_map()
        sub_id = sub_plan["id"]
        nodes = sub_plan["plan"]
        self._execute_nodes(sub_id, nodes, context, task_map, publish)
        return context.get("_return", None)