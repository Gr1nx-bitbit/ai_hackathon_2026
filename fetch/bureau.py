"""
Bureau — runs the pipeline agent and client agent together in one process.

Use this for local end-to-end testing without needing Agentverse or two
separate terminal windows.

    uv run python -m fetch.bureau

The client agent sends all four demo scenarios on startup and logs each
response as it arrives.
"""

from uagents import Bureau

from fetch.pipeline_agent import agent as pipeline_agent
from fetch.client_agent import create_client_agent

# Inject the pipeline agent's address so the client knows where to send requests.
# Both agents share the same process, so the address is available immediately.
client_agent = create_client_agent(pipeline_address=pipeline_agent.address)

bureau = Bureau(agents=[pipeline_agent, client_agent])

if __name__ == "__main__":
    bureau.run()
