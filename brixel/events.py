from enum import Enum

class ApiEventName(str, Enum):
    NODE_START = "node_start"
    NODE_FINISH = "node_finish"
    FOR_ITERATION_START = "for_iteration_start"
    WHILE_ITERATION_START = "while_iteration_start"
    ERROR = "error"
    SUB_PLAN_DONE = "sub_plan_done"
    DONE = "done"