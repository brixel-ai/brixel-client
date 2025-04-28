# brixel

[![PyPI version](https://badge.fury.io/py/brixel.svg)](https://pypi.org/project/brixel/)

> A powerful Python SDK for building and executing task-oriented workflows using the [Brixel API](https://brixel.ai).

---

## ✨ Features

- ✅ Generate plans based on natural language and agent/task definitions.
- ⚙️ Execute local plans with full support for conditional logic and loops.
- 🧠 Decorators to register tasks and agents from any Python module.
- 🔁 Integrated streaming/message broker system.
- 📦 Compatible with `asyncio`, lists, functions, and queues for messaging.
- ☁️ Support for remote execution of hosted and external agents.
- 🖥️ Expose external agents via HTTP using `BrixelServer`.

---

## 📦 Installation

```bash
pip install brixel
```

---

## 🏁 Get Started

To use the Brixel SDK, you'll need a **free** Brixel account and an API key.

1. Go to [**https://console.brixel.ai**](https://console.brixel.ai)
2. Create an account (or log in)
3. Navigate to the **API Keys** section
4. **Generate new API Key** to generate your personal API token

```python
from brixel.client import BrixelClient

client = BrixelClient(api_key="your_api_key_here")
```

> 💡 You can also define the key using the environment variable `BRIXEL_API_KEY`  
> The client will automatically use it if `api_key` is not explicitly passed.

---

## 🚀 Quickstart

### 1. Define Tasks with `@task`

```python
from pathlib import Path
from brixel.decorators import task
from PIL import Image
import base64
import requests
from io import BytesIO

@task(agent_id="image")
def download_image_as_base64(url: str) -> str:
    """Download an image from a URL and return its base64 representation.

    Args:
        url (str): The image URL.

    Returns:
        str: Base64-encoded image data.
    """
    response = requests.get(url)
    response.raise_for_status()
    return base64.b64encode(response.content).decode()

@task(agent_id="image")
def resize_image(image_b64: str, width: int, height: int) -> str:
    """Resize an image to the specified dimensions.

    Args:
        image_b64 (str): Base64-encoded image.
        width (int): Target width.
        height (int): Target height.

    Returns:
        str: Resized image as base64 string.
    """
    image = Image.open(BytesIO(base64.b64decode(image_b64)))
    resized = image.resize((width, height))
    buffered = BytesIO()
    resized.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode()

@task(agent_id="image")
def save_image_to_file(image_b64: str, filename: str, path: str = None) -> str:
    """Save a base64-encoded image to a file.

    Args:
        image_b64 (str): The base64-encoded image string.
        filename (str): The name of the file to save (e.g., 'output.png').
        path (str, optional): Directory to save the file in. Defaults to current directory.

    Returns:
        str: Full path of the saved file.
    """
    if not path:
        path = "."
    full_path = Path(path) / filename
    image_data = base64.b64decode(image_b64)
    full_path.write_bytes(image_data)
    return str(full_path.resolve())

```
> 💡 **Tip**  
> Use [Google-style](https://sphinxcontrib-napoleon.readthedocs.io/en/latest/example_google.html) docstrings for your task functions to improve automatic metadata extraction (descriptions, types, etc.).


### 2. Declare an Agent with `@agent`

```python
from brixel.decorators import agent

@agent(id="image")
class ImageAgent:
    name = "Image Agent"
    description = "Performs all kind of operations on images."
```

### 3. Generate a Plan

```python
import my_registered_tasks  # ensure tasks are imported
import my_registered_agents # ensure agents are imported

from brixel.client import BrixelClient

# You can also use the BRIXEL_API_KEY environment variable
client = BrixelClient(api_key="your_api_key")

files = ["https://cdn.brixel.ai/logo/brixel_logo_full.png"]
plan = client.generate_plan(
    message="Can you resize this picture in 120x38 px and save it as brixel_resized.png?",
    files=files

)
```

### 4. Execute the Plan

```python
client.execute_plan(plan, files)
```

---

## 🌐 Mixing Local, Hosted and External Agents with `module_id`

Brixel allows you to combine **local** agents (defined in your code) with **hosted** (agents created on Brixel platform) and **external** agents (external agents connected with Brixel).

### 🔑 Using a `module_id`

To reference **agents already configured in a specific module on Brixel**, provide a `module_id` when generating your plan:

```python
plan = client.generate_plan(
    message="Take this image, resize it and upload it on Google drive",
    module_id="d8f575aa-731c-4842-93e9-614a0e31b360",
    files=files
)
```
> 💡 **Tip**  
> The module must be an **API** module

Brixel will generate a plan based on your local agents **PLUS** module agents

### ⚙️ Execution Behavior

When you call `client.execute_plan(...)`:

- Agents defined with `@agent` in your code (`type: "local"`) are **executed locally** in Python via the SDK.
- Hosted or external agents (`type: "hosted"` or `type: "external"`) are **executed remotely via Brixel’s API**.

This enables you to:

- Extend your plans with **SaaS tools, connectors, or cloud-based agents**.
- Build, test, and debug locally.

> This makes Brixel an ideal hybrid orchestration solution — combining the flexibility of local development with the power of hosted services.

---

## 🧩 Agents & Tasks Explorer

```python
# print the full agents and tasks structured sent to brixel when generating a plan
print(client.describe_registered_agents(full=True))

# print the tasks registered
print(client.describe_registered_tasks())
```

---

## 📡 Message Broker Support

You can pass a message broker to the client:

```python
import example_decorated_image_tasks
import example_decorated_agents
from brixel.client import BrixelClient
from brixel.events import ApiEventName


event_log = []

client = BrixelClient(
    api_key="your_api_key",
    message_broker=event_log
)

files = ["https://cdn.brixel.ai/logo/brixel_logo_full.png"]

plan = client.generate_plan(
    message="Can you resize this picture in 120x38 px and save it as brixel_resized.png?",
    files=files
)

client.execute_plan(plan, files)

print("\nRegistered events :")
for event in event_log:
    print(event)

```

Or in async mode with a queue and **AsyncBrixelClient**

```python
import asyncio
import example_decorated_image_tasks
import example_decorated_agents
from brixel.async_client import AsyncBrixelClient
from brixel.events import ApiEventName


async def consume_queue(queue):
    while True:
        item = await queue.get()
        print("Received event :", item)
        if item["event"] == ApiEventName.ERROR or item["event"] == ApiEventName.DONE:
            break
        
async def main():
    queue = asyncio.Queue(maxsize=100)

    client = AsyncBrixelClient(api_key="your_api_key", message_broker=queue)
    consumer_task = asyncio.create_task(consume_queue(queue))

    files = ["https://cdn.brixel.ai/logo/brixel_logo_full.png"]
    plan = await client.generate_plan(
        message="Can you resize this picture in 120x38 px and save it as brixel_resized.png?",
        files=files
    )

    await client.execute_plan(plan, files)

    await consumer_task

asyncio.run(main())
```

supports:
- ✅ `list.append()`
- ✅ `asyncio.Queue`
- ✅ `async def websocket.send(msg)`
- ✅ `callable` / `async callable`
- ✅ `async generators`

---

## 🖥️ External Agent: Server Mode with FastAPI

Brixel also supports running **external** agents using the `BrixelServer` class and exposing them over HTTP with frameworks like **FastAPI**. This is useful for:

- Using your local agent outside the **API** module and make it available for your organisation


### Requirements

To expose an agent as an **external server-based agent**, your FastAPI app must implement:

1. **An endpoint to expose agent configuration and tasks**  
   This is used by Brixel to **discover the available tasks** and register the agent.

   ```http
   GET /get_configuration
   ```

2. **An endpoint to execute a sub-plan**  
   This receives a `sub_plan`, a `sub_id`, and a **signed payload** to ensure the plan originated from Brixel.

   ```http
   POST /execute_plan
   ```

   The `payload` should include:
   - `plan_id`: the ID of the parent plan
   - `sub_id`: the unique sub-plan identifier
   - `sub_plan`: the list of steps to execute
   - `inputs`: optional input values
   - `signature`: a signed string that validates the payload origin

> 🔐 **Security Tip**  
> You can (and should) add extra authentication mechanisms, such as:
> - API key in headers
> - OAuth bearer tokens

> The path of the two endpoints are not important, they need to be configured on Brixel platform when creating an Agent of type **external**
>
> The authentication mechanisms need also to be configured on Brixel platform


### 🛠️ Example: Expose your agent with FastAPI

```python
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import asyncio
import json

from brixel.server import BrixelServer
from brixel.events import ApiEventName
from brixel.decorators import agent, task

@agent(id="image")
class ImageAgent:
    name = "Image Agent"
    description = "Performs various operations on images."

@task(agent_id="image")
def grayscale_image(image_b64: str) -> str:
    # Your task logic here...
    pass

app = FastAPI()
secret = "your_shared_secret"
options = {"stream": True}

@app.get("/get_configuration")
def get_configuration():
    server = BrixelServer(agent_id="image", secret=secret, options=options)
    return server.get_configuration()

class SubPlanInput(BaseModel):
    plan_id: str
    sub_id: int
    sub_plan: list
    signature: str = None
    inputs: dict = None

def make_broker(queue: asyncio.Queue):
    loop = asyncio.get_running_loop()
    def broker_sync(msg: dict):
        loop.call_soon_threadsafe(queue.put_nowait, msg)
    return broker_sync

async def event_stream(queue: asyncio.Queue):
    while True:
        item = await queue.get()
        yield f"{json.dumps(item)}\n"
        if item["event"] in (ApiEventName.DONE, ApiEventName.ERROR):
            break

@app.post("/execute_plan")
async def execute_plan(payload: SubPlanInput):
    """
    Execute a sub-plan locally and stream events back to the client.
    """
    q_messages: asyncio.Queue = asyncio.Queue()
    broker = make_broker(q_messages)
    server = BrixelServer(agent_id="image", secret=secret, options=options, message_broker=broker)

    async def run_plan_in_thread():
        """Run plan in a separate thread and push results into the queue."""
        try:
            await asyncio.to_thread(
                server.execute_plan,
                sub_id=payload.sub_id,
                sub_plan=payload.sub_plan,
                signature=payload.signature,
                inputs=payload.inputs,
            )
        except Exception as exc:
            await q_messages.put({
                "event": ApiEventName.ERROR,
                "details": {"error": str(exc)},
            })

    asyncio.create_task(run_plan_in_thread())

    return StreamingResponse(
        event_stream(q_messages),
        media_type="application/json",
    )

```

> 💡 **Use case**  
> You can test your agents locally with the **API** module, then, once they are ready, deploy them as **external** agents to be use on every modules
>
> Your externals agents behave like a local agent, the execution of the sub plan is still done on your server

---

## 🧭 Visualizing Execution Plans

Brixel provides a built-in utility to **render and inspect execution plans as flowcharts**.  
This can help you debug and understand how your tasks are connected.

### 🖼️ Display a Plan

You can visualize a plan using the `display_plan` function:

```python
from brixel.visualization import display_plan

plan = client.generate_plan(
    message="Resize the image and send it to Slack",
    files=["https://cdn.brixel.ai/logo/brixel_logo_full.png"],
    module_id="8349egzb-e092-4862-b374-332832daa957"
)

display_plan(plan, filename="my_plan_graph.png")
```


### 📦 Optional dependencies

To use this feature, you need to install extra packages:

```bash
pip install brixel[viz]
```

This will install:

- `graphviz` (binary required for rendering)
- `pydot`
- `matplotlib`

> ⚠️ Make sure the `dot` executable from Graphviz is available in your system PATH.
```bash
sudo apt install graphviz
```

## 📘 License

Apache 2 License — [Brixel](https://brixel.ai)
