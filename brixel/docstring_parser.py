import re

def parse_docstring(docstring: str):
    """
    Parse une docstring au format Google / NumPy.
    Retourne un dict : { 'description': str, 'args': {name: {'type':..., 'desc':...}}, 'return': {type, desc} }
    """
    parsed = {
        "description": "",
        "args": {},
        "return": {}
    }

    if not docstring:
        return parsed

    lines = docstring.strip().splitlines()
    mode = "desc"
    arg_name = None

    for line in lines:
        line = line.strip()

        if re.match(r"^(Args|Arguments|Parameters):", line, re.IGNORECASE):
            mode = "args"
            continue
        if re.match(r"^(Returns?|Yields?):", line, re.IGNORECASE):
            mode = "return"
            continue

        if mode == "desc":
            parsed["description"] += line + " "

        elif mode == "args":
            match = re.match(r"^(\w+)\s*\(([^)]+)\):\s*(.+)", line)
            if match:
                arg_name, arg_type, arg_desc = match.groups()
                parsed["args"][arg_name] = {
                    "type": arg_type.strip(),
                    "desc": arg_desc.strip()
                }

        elif mode == "return":
            match = re.match(r"^([^:]+):\s*(.+)", line)
            if match:
                ret_type, ret_desc = match.groups()
                parsed["return"] = {
                    "type": ret_type.strip(),
                    "desc": ret_desc.strip()
                }

    parsed["description"] = parsed["description"].strip()
    return parsed
