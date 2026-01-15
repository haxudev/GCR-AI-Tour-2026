# Power FX quick reference (MAF Declarative Workflows)

Purpose: help you write correct `=` expressions, variable paths, and common functions so workflows behave as expected.

## Core conventions

- Power FX expressions start with `=` (e.g., `=System.ConversationId`).
- Workflow-scope variables: `Local.*`
- System variables: `System.*`
- Convert a messages collection to text with `MessageText(<messagesVar>)`.

## Common system variables

- `=System.ConversationId`
- `=System.LastMessage.Text`
- `=System.LastMessageText` (some samples parse it via `Value()`)

## Common functions/patterns

- Create a user message: `=UserMessage("hello")`, `=UserMessage(Local.InputTask)`
- Extract text from messages: `=MessageText(Local.SomeMessages)`
- Parse numeric input: `=Value(System.LastMessageText)`
- Mod check: `=Mod(Local.TestValue, 2) = 0`
- Logic: `=Not(Local.Flag)`, `=A || B`, `=A && B`

## Collections and lookup (common in complex orchestration)

- Build a bullet list description:
  - `=Concat(ForAll(Local.AvailableAgents, "- " & name & ": " & description), Value, "\n")`
- Search:
  - `=Search(Local.AvailableAgents, Local.TargetName, name)`
- Count / first item:
  - `=CountRows(Local.Matches) = 1`
  - `=First(Local.Matches).name`

## Practical tips inside YAML

- If the expression contains `:`, `#`, or newlines, use quoting or a block scalar:
  - `value: "=Concat(...)"`
  - `value: |-
      =UserMessage(
        "..."
      )`
- Avoid accidentally turning an expression into a plain string. If you write `"=System.ConversationId"`, some fields/parsers may treat it as a literal string instead of an expression.
