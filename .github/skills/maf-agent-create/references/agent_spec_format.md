# Agent spec format (maf-agent-create)

`maf-agent-create` can emit and consume a small declarative YAML spec.

## YAML schema

Top-level object:

- `agents`: list of agent objects

Each agent object:

- `name` (string, required): Foundry agent name
- `instructions` (string, optional): system instructions for the agent

Example:

```yaml
agents:
  - name: ResearchAgent
    instructions: |-
      You are ResearchAgent. Provide accurate technical research.
      Do not invent links or claims; clearly label uncertainty.
  - name: WriterAgent
    instructions: |-
      You are WriterAgent. Write high-quality technical Markdown.
      Be precise; include runnable code blocks when requested.
```

## Output id map JSON

When `--write-id-map` is used, the script writes a JSON object mapping agent name to agent id:

```json
{
  "ResearchAgent": "ResearchAgent:2",
  "WriterAgent": "WriterAgent:2"
}
```

This file plugs directly into the workflow runner:

- `--azure-ai-agent-id-map-json path/to/agent_id_map.json`
