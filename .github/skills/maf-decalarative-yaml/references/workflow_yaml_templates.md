# Workflow YAML templates and action snippets (MAF Declarative)

Purpose: composable building blocks for quickly assembling a `kind: Workflow` YAML.

If you want a complete end-to-end starter workflow from a natural-language requirement, use:

- `python .github/skills/maf-decalarative-yaml/scripts/generate_workflow_yaml.py --requirement "..." --out MyWorkflow.yaml`

## Contents

- Minimal workflow skeleton
- Variables and messages
- Invoke an agent (InvokeAzureAgent)
- Human input (Question)
- Branching (ConditionGroup)
- Jump (GotoAction)
- Loop (Foreach)
- End (EndConversation / EndWorkflow)

## Minimal workflow skeleton

```yaml
kind: Workflow
trigger:
  kind: OnConversationStart
  id: workflow_demo
  actions:
    - kind: SendActivity
      id: hello
      activity: "Hello from workflow"
```

Constraint: every `id` must be unique across the entire workflow.

## Variables and messages

### Capture the latest user input

Hosted runtime pattern:

```yaml
- kind: SetTextVariable
  id: set_input
  variable: Local.Input
  value: =System.LastMessage.Text
```

Local runner friendly alternatives:

1) Ask via `Question` and store into `Local.Input`.

2) Embed fixed text into a block scalar (useful when generating a runnable example workflow):

```yaml
- kind: SetTextVariable
  id: set_input
  variable: Local.Input
  value: |-
    <put the requirement here>
```

### Send a message

```yaml
- kind: SendActivity
  id: say_status
  activity: "Working..."
```

### Compose long text (prefer SetTextVariable + block scalar)

```yaml
- kind: SetTextVariable
  id: set_instructions
  variable: Local.Instructions
  value: |-
    # TASK
    {Local.Input}
```

## Invoke an agent (InvokeAzureAgent)

### Minimal messages input

```yaml
- kind: InvokeAzureAgent
  id: call_agent_1
  agent:
    name: MyAgentName
  input:
    messages: =UserMessage(Local.Input)
```

### Bind to a conversationId (multiple threads)

```yaml
- kind: CreateConversation
  id: create_status_thread
  conversationId: Local.StatusConversationId

- kind: InvokeAzureAgent
  id: call_agent_status
  conversationId: =Local.StatusConversationId
  agent:
    name: ManagerAgent
  input:
    messages: =UserMessage("Report status")
```

### Persist output into variables (messages or responseObject)

```yaml
- kind: InvokeAzureAgent
  id: call_agent_save
  agent:
    name: MyAgentName
  input:
    messages: =UserMessage("Give me a JSON summary")
  output:
    responseObject: Local.SummaryJson
```

```yaml
- kind: InvokeAzureAgent
  id: call_agent_save_msgs
  agent:
    name: MyAgentName
  input:
    messages: =UserMessage("Summarize")
  output:
    messages: Local.SummaryMessages
```

### Structured input via arguments (when the agent supports it)

```yaml
- kind: InvokeAzureAgent
  id: call_agent_args
  agent:
    name: PlannerAgent
  input:
    arguments:
      team: =Local.TeamDescription
      task: =Local.Input
  output:
    messages: Local.Plan
```

## Human input (Question)

```yaml
- kind: Question
  id: ask_confirm
  alwaysPrompt: false
  autoSend: false
  property: Local.Confirmed
  prompt:
    kind: Message
    text:
      - "CONFIRM:"
  entity:
    kind: StringPrebuiltEntity
```

Tip: for “ask until valid”, pair `ConditionGroup` with `GotoAction`.

## Branching (ConditionGroup)

```yaml
- kind: ConditionGroup
  id: branch_example
  conditions:
    - id: cond_ok
      condition: =Local.Confirmed = "yes"
      actions:
        - kind: SendActivity
          id: say_ok
          activity: "OK"
  elseActions:
    - kind: SendActivity
      id: say_retry
      activity: "Try again"
```

## Jump (GotoAction)

```yaml
- kind: GotoAction
  id: goto_ask_again
  actionId: ask_confirm
```

## Loop (Foreach)

```yaml
- kind: Foreach
  id: loop_items
  # TODO: specify the collection to iterate.
  # Field names can vary by version/implementation; confirm with official samples/source.
  actions:
    - kind: SendActivity
      id: say_one
      activity: "..."  # reference the exposed "current item" variable per your runtime
```

Note: how the "current item" is exposed may vary across versions/implementations; verify with official samples or print variables at runtime.

## End

```yaml
- kind: EndConversation
  id: end
```

Or:

```yaml
- kind: EndWorkflow
  id: end_workflow
```
