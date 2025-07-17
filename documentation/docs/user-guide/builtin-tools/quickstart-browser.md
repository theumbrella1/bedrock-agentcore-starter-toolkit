# Getting Started with Browser

The Amazon Bedrock AgentCore Browser provides a secure, managed environment for web browsing and automation. This guide will help you implement powerful browser capabilities in your agent applications.

## Prerequisites

Before using the browser tool, ensure you have:

- An AWS account with appropriate permissions
- Python 3.10+ installed

## Install the SDK

```bash
pip install bedrock-agentcore
```

## Create a Browser Session

The bedrock-agentcore SDK provides a convenient way to create browser sessions:

```python
from bedrock_agentcore.tools.browser_client import browser_session

# Create a browser session using the context manager
with browser_session("us-west-2") as client:
    # The session_id is automatically generated
    print(f"Session ID: {client.session_id}")

    # Generate WebSocket URL and headers for connecting automation frameworks
    websocket_url, headers = client.generate_ws_headers()

    # Use these to connect your preferred browser automation tool
    # (See examples below)

# The session is automatically closed when exiting the context manager
```

For more control over the session lifecycle:

```python
from bedrock_agentcore.tools.browser_client import BrowserClient

# Create a browser client
client = BrowserClient(region_name="us-west-2")

# Start a browser session
client.start()
print(f"Session ID: {client.session_id}")

try:
    # Generate WebSocket URL and headers
    url, headers = client.generate_ws_headers()

    # Perform browser operations with your preferred automation tool

finally:
    # Always close the session when done
    client.stop()
```

## Integration Examples

### Example 1: Browser Automation with Nova Act

You can build a browser agent using Nova Act to automate web interactions:

```python
import time
from bedrock_agentcore.tools.browser_client import browser_session
from nova_act import NovaAct
from rich.console import Console

NOVA_ACT_API_KEY = "YOUR_NOVA_ACT_API_KEY"

console = Console()

def main():
    try:
        # Step 1: Create browser session
        with browser_session('us-west-2') as client:
            print("\r   ✅ Browser ready!                    ")
            ws_url, headers = client.generate_ws_headers()

            # Step 2: Use Nova Act to interact with the browser
            with NovaAct(
                    cdp_endpoint_url=ws_url,
                    cdp_headers=headers,
                    preview={"playwright_actuation": True},
                    nova_act_api_key=NOVA_ACT_API_KEY,
                    starting_page="https://www.amazon.com",
                ) as nova_act:
                    result = nova_act.act("Search for coffee maker and get the details of the lowest priced one on the first page")
                    console.print(f"\n[bold green]Nova Act Result:[/bold green] {result}")

    except KeyboardInterrupt:
        console.print("\n\n[yellow]Shutting down...[/yellow]")
        if 'client' in locals():
            client.stop()
            print("✅ Browser session terminated")
    except Exception as e:
        print(f"\n[red]Error: {e}[/red]")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
```

### Example 2: Browser Tool with Strands Framework

You can build an agent that uses the Browser Tool as one of its tools using the Strands framework:

```python
import random
from strands import Agent, tool
from bedrock_agentcore.tools.browser_client import browser_session
from nova_act import NovaAct
from browser_viewer import BrowserViewerServer

# Constants
NOVA_ACT_API_KEY = "YOUR_NOVA_ACT_API_KEY"

@tool
def browser_automation_tool(starting_url: str, instr: str) -> str:
    """
    Automates browser tasks starting from a given URL based on natural language instructions.
    Supports parallel execution and can handle moderately complex tasks with some reasoning.

    Args:
        starting_url (str): The initial URL to open in the browser.
        instr (str): A natural language instruction describing the task to be automated.

    Returns:
        str: The result of the action performed in the browser.
    """
    with browser_session('us-west-2') as client:

        # Retrieve CDP WebSocket URL and headers for control
        ws_url, headers = client.generate_ws_headers()

        # Use a random port to avoid conflicts
        port = random.randint(8000, 9000)

        # Start the browser viewer server (optional GUI)
        viewer = BrowserViewerServer(client, port=port)
        viewer_url = viewer.start(open_browser=True)
        print(f"Viewer started at: {viewer_url}")

        try:
            with NovaAct(
                cdp_endpoint_url=ws_url,
                cdp_headers=headers,
                preview={"playwright_actuation": True},
                nova_act_api_key=NOVA_ACT_API_KEY,
                starting_page=starting_url,
            ) as nova_act:
                result = nova_act.act(instr)
                return result

        except Exception as e:
            print(f"[ERROR] Failed to perform browser automation: {e}")
            raise


# Initialize the supervisor agent with available tools
supervisor_agent = Agent(tools=[browser_automation_tool])

if __name__ == "__main__":
    # Example task for the agent
    message = """
    I have the following tasks. Feel free to run them in parallel if it improves performance.
    If a CAPTCHA is encountered, instruct the browser tool to wait for manual resolution.

    1. Get the top 1 current market gainer and loser from Yahoo Finance.
    2. Fetch the most recent news about these gainer and loser stocks.
    3. Generate a short report for both the gainer and the loser.
    """
    supervisor_agent(message)
```

### Example 3: Using Playwright for Browser Control

You can use the Playwright automation framework with the Browser Tool:

```python
from playwright.sync_api import sync_playwright, Playwright, BrowserType
from bedrock_agentcore.tools.browser_client import browser_session
from browser_viewer import BrowserViewerServer
import time

def run(playwright: Playwright):
    # Create the browser session and keep it alive
    with browser_session('us-west-2') as client:
        ws_url, headers = client.generate_ws_headers()

        # Start viewer server
        viewer = BrowserViewerServer(client, port=8005)
        viewer_url = viewer.start(open_browser=True)

        # Connect using headers
        chromium: BrowserType = playwright.chromium
        browser = chromium.connect_over_cdp(
            ws_url,
            headers=headers
        )

        context = browser.contexts[0]
        page = context.pages[0]

        try:
            page.goto("https://amazon.com/")
            print(page.title())
            time.sleep(120)
        finally:
            page.close()
            browser.close()

with sync_playwright() as playwright:
    run(playwright)
```

## Browser Tool Architecture

The AWS Browser Tool provides:

- **Fully managed browser environment** running in the AWS cloud
- **WebSocket-based CDP interface** for browser control
- **Integration with popular automation frameworks** like Playwright, Puppeteer, and NovaAct
- **Security and isolation** between browser sessions

## Best Practices

To get the most out of the browser tool:

1. **Use context managers** for proper resource cleanup
2. **Handle exceptions properly** to ensure browser sessions are closed
3. **Consider performance** when making multiple browser requests
4. **Secure sensitive data** - never hardcode credentials in browser automation code
5. **Use appropriate timeouts** for network and page load operations
6. **Add error recovery** for common browser automation challenges
