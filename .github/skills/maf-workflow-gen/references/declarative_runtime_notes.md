# maf-workflow-gen runtime notes

This skill generates a local runner that interprets a subset of Microsoft Agent Framework declarative workflow YAML.

## Supported action kinds (runtime)

- `SendActivity`
  - Prints `activity` after `{...}` placeholder rendering.
- `Question`
  - Reads from stdin and stores into `property` (e.g., `Local.Topic`).
  - Supported entity kinds: `StringPrebuiltEntity`, `NumberPrebuiltEntity`, `BooleanPrebuiltEntity`.
- `SetTextVariable`
  - Stores `value` into `variable` after placeholder rendering.
- `SetVariable`
  - Stores `value` into `variable`.
  - For strings starting with `=` evaluates a minimal Power FX subset.
  - For other strings, applies `{...}` placeholder rendering.
  - For non-string YAML values, stores them as-is.
- `InvokeAzureAgent`
  - Builds a prompt from `input.messages`.
  - Default invoker is **manual**: prints the prompt and asks you to paste the output.
  - Stores output as a list of messages into `output.messages` (e.g., `Local.ResearchNotes`).
- `ConditionGroup`
  - Evaluates `conditions[*].condition` (minimal Power FX subset) and jumps to the selected branch.
- `GotoAction`
  - Jumps to `actionId`.
- `EndConversation`
  - Terminates execution.

## Expression support

### `{...}` placeholders

Rendered in `SendActivity.activity` and `SetTextVariable.value`:

- `{Local.SomeVar}` -> replaced with the stored variable value
- `{MessageText(Local.SomeMessagesVar)}` -> joins a list of messages

### Power FX subset for `input.messages`

The runtime supports the common pattern:

- `=UserMessage("a" & Local.Topic & "b" & MessageText(Local.ResearchNotes))`

It handles:

- string literals in double quotes
- concatenation with `&`
- variable references `Local.*`
- `MessageText(Local.*)`

### Power FX subset for `ConditionGroup`

Supported:

- `=Local.UserApproved`
- `=not(Local.UserApproved)`
- `=Local.UserApproved = true`

Anything outside this subset should be considered unsupported and may raise an error.

## Calling local tools (recommended for deterministic steps)

The generated runner can intercept a dedicated agent name and execute local Python tools instead of calling Foundry.

- Agent name: `LocalToolExecutorAgent`
- Prompt format: include a JSON object like:

  `{"tool": "write_text_file", "args": {"path": "output/demo.txt", "text": "hello"}}`

The tool registry used by the runner template is the repo-level shared registry: `shared_tools/maf_shared_tools_registry.py`.

Fallback:

- The skill-local registry `.github/skills/maf-shared-tools/examples/maf_shared_tools_registry.py` is kept as a self-contained example/shim.

## Extending to real agents

To replace manual `InvokeAzureAgent` behavior:

- Edit the generated `run.py` to pass a custom `AgentInvoker` to `DeclarativeWorkflowRunner.from_yaml(...)`.
- Implement `AgentInvoker.invoke(agent_name: str, prompt: str) -> str` to call your real agent/LLM.

### Azure AI Foundry (Agent Framework)

The generated `run.py` supports real Foundry calls via `--azure-ai`.

Typical inputs:

- `--azure-ai-project-endpoint` (or env `AZURE_AI_PROJECT_ENDPOINT`; this repo also uses `AZURE_EXISTING_AIPROJECT_ENDPOINT`)
- `--azure-ai-model-deployment-name` (or env `AZURE_AI_MODEL_DEPLOYMENT_NAME`; required by the SDK)
- Optional: `--azure-ai-agent-id` (or env `AZURE_AI_AGENT_ID` / `AZURE_EXISTING_AGENT_ID`)

Auth:

- Uses `AzureCliCredential` (so `az login` must be done in advance)

## Additional runner features

### Agent name -> ID resolution

If your workflow uses agent *names* (e.g., `ResearchAgent`) in `InvokeAzureAgent.agent`, the runner can resolve them to versioned IDs (e.g., `ResearchAgent:2`) from the Foundry project.

- Automatic (default when `--azure-ai` is enabled): resolves latest version by name.
- Manual mapping: `--azure-ai-agent-id-map ResearchAgent=ResearchAgent:2` (repeatable) or `--azure-ai-agent-id-map-json path/to/map.json`.
- Disable auto-resolve: `--no-azure-ai-auto-resolve-agent-ids`.
- Verbose resolution logs: `--azure-ai-verbose`.

### Saving final output

After the workflow finishes, the runner can persist a variable value to disk:

- `--save-markdown path/to/final.md` writes the selected variable to a file.
- `--save-var Local.EditedDraft` chooses which variable to save (default is `Local.EditedDraft`).
