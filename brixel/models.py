from typing import List, Dict

def create_task(name: str, description: str, inputs: List[Dict], output: Dict) -> Dict:
    return {
        "name": name,
        "description": description,
        "configuration": {
            "inputs": inputs,
            "output": output
        }
    }
