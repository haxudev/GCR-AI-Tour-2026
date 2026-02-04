#!/usr/bin/env python3

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable


class WorkflowRuntimeError(RuntimeError):
    pass


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise WorkflowRuntimeError(
            "Missing dependency: pyyaml. Install with: pip install pyyaml"
        ) from exc

    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise WorkflowRuntimeError("Root YAML must be a mapping/object")
    return doc


def _coerce_bool(value: str) -> bool:
    v = value.strip().lower()
    if v in {"true", "t", "yes", "y", "1"}:
        return True
    if v in {"false", "f", "no", "n", "0"}:
        return False
    raise ValueError(f"Not a boolean: {value!r}")


def _coerce_number(value: str) -> int | float:
    v = value.strip()
    try:
        if re.search(r"[.eE]", v):
            return float(v)
        return int(v)
    except Exception as exc:
        raise ValueError(f"Not a number: {value!r}") from exc


def _message_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if item is None:
                continue
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(str(item["text"]))
            else:
                parts.append(str(item))
        return "\n".join(parts)
    return str(value)


def _unescape_powerfx_string(s: str) -> str:
    # Handle the most common escapes used in the sample YAML.
    return (
        s.replace("\\r", "\r")
        .replace("\\n", "\n")
        .replace("\\t", "\t")
        .replace('\\"', '"')
        .replace("\\\\", "\\")
    )


def _split_top_level_concat(expr: str) -> list[str]:
    # Split Power FX concatenation expression by '&' at top-level.
    terms: list[str] = []
    buf: list[str] = []
    in_str = False
    paren = 0
    i = 0
    while i < len(expr):
        ch = expr[i]
        if ch == '"':
            # toggle string, honoring simple escapes
            if i > 0 and expr[i - 1] == "\\":
                buf.append(ch)
            else:
                in_str = not in_str
                buf.append(ch)
            i += 1
            continue

        if not in_str:
            if ch == "(":
                paren += 1
            elif ch == ")":
                paren = max(0, paren - 1)
            elif ch == "&" and paren == 0:
                term = "".join(buf).strip()
                if term:
                    terms.append(term)
                buf = []
                i += 1
                continue

        buf.append(ch)
        i += 1

    tail = "".join(buf).strip()
    if tail:
        terms.append(tail)
    return terms


def _strip_outer(s: str, prefix: str, suffix: str) -> str | None:
    s2 = s.strip()
    if not s2.startswith(prefix) or not s2.endswith(suffix):
        return None
    return s2[len(prefix) : -len(suffix)].strip()


@dataclass
class CompiledAction:
    action: dict[str, Any]
    default_next: str | None


class AgentInvoker:
    """Hook to implement InvokeAzureAgent.

    Default is manual mode: print prompt and ask user to paste output.
    """

    def __init__(self, interactive: bool = True):
        self._interactive = interactive

    def invoke(self, agent_name: str, prompt: str) -> str:
        header = f"\n=== InvokeAzureAgent: {agent_name} ===\n"
        print(header + prompt + "\n")

        if not self._interactive:
            raise WorkflowRuntimeError(
                "Non-interactive mode: InvokeAzureAgent requires an AgentInvoker implementation"
            )

        print("Paste the agent output. End with an empty line:")
        lines: list[str] = []
        while True:
            line = input()
            if line == "":
                break
            lines.append(line)
        return "\n".join(lines).strip()


class DeclarativeWorkflowRunner:
    def __init__(
        self,
        doc: dict[str, Any],
        *,
        interactive: bool = True,
        agent_invoker: AgentInvoker | None = None,
        initial_vars: dict[str, Any] | None = None,
    ) -> None:
        self._doc = doc
        self._interactive = interactive
        self._agent_invoker = agent_invoker or AgentInvoker(interactive=interactive)

        self._vars: dict[str, Any] = dict(initial_vars or {})
        self._compiled: dict[str, CompiledAction] = {}
        self._start_action_id: str | None = None

        self._compile()

    @classmethod
    def from_yaml(
        cls,
        path: Path,
        *,
        interactive: bool = True,
        agent_invoker: AgentInvoker | None = None,
        initial_vars: dict[str, Any] | None = None,
    ) -> "DeclarativeWorkflowRunner":
        return cls(
            _load_yaml(path),
            interactive=interactive,
            agent_invoker=agent_invoker,
            initial_vars=initial_vars,
        )

    def set_var(self, key: str, value: Any) -> None:
        self._vars[key] = value

    def get_var(self, key: str, default: Any = None) -> Any:
        return self._vars.get(key, default)

    def vars_snapshot(self) -> dict[str, Any]:
        return dict(self._vars)

    def run(self) -> None:
        if not self._start_action_id:
            raise WorkflowRuntimeError("No start action found")

        current = self._start_action_id
        steps = 0
        max_steps = 10_000

        while current is not None:
            steps += 1
            if steps > max_steps:
                raise WorkflowRuntimeError("Exceeded max steps; possible infinite loop")

            compiled = self._compiled.get(current)
            if not compiled:
                raise WorkflowRuntimeError(f"Unknown action id: {current}")

            action = compiled.action
            kind = action.get("kind")
            if not isinstance(kind, str):
                raise WorkflowRuntimeError(f"Action {current} missing kind")

            next_id = self._execute_action(action, compiled.default_next)
            current = next_id

    # ----------------- compilation -----------------

    def _compile(self) -> None:
        if self._doc.get("kind") != "Workflow":
            raise WorkflowRuntimeError("Root kind must be 'Workflow'")

        trigger = self._doc.get("trigger")
        if not isinstance(trigger, dict):
            raise WorkflowRuntimeError("Missing trigger")

        actions = trigger.get("actions")
        if not isinstance(actions, list):
            raise WorkflowRuntimeError("trigger.actions must be a list")

        # Compile the top-level action sequence.
        self._start_action_id = self._compile_sequence(actions, next_id=None)

    def _compile_sequence(self, actions: list[Any], *, next_id: str | None) -> str | None:
        # Compile a list of actions into a simple state machine.
        # Returns the first action id in this sequence.
        next_action_id = next_id

        for node in reversed(actions):
            if not isinstance(node, dict):
                raise WorkflowRuntimeError("Each action must be a mapping/object")
            node_id = node.get("id")
            if not isinstance(node_id, str) or not node_id:
                raise WorkflowRuntimeError("Each action requires a non-empty id")
            if node_id in self._compiled:
                raise WorkflowRuntimeError(f"Duplicate action id: {node_id}")

            kind = node.get("kind")
            if not isinstance(kind, str) or not kind:
                raise WorkflowRuntimeError(f"Action {node_id} missing kind")

            if kind == "ConditionGroup":
                # Compile branch sequences so that they rejoin at next_action_id.
                conditions = node.get("conditions")
                if not isinstance(conditions, list) or not conditions:
                    raise WorkflowRuntimeError(f"ConditionGroup {node_id} requires conditions[]")

                for cond in conditions:
                    if not isinstance(cond, dict):
                        raise WorkflowRuntimeError(f"ConditionGroup {node_id} invalid condition entry")
                    cond_actions = cond.get("actions")
                    if isinstance(cond_actions, list) and cond_actions:
                        self._compile_sequence(cond_actions, next_id=next_action_id)

                else_actions = node.get("elseActions")
                if isinstance(else_actions, list) and else_actions:
                    self._compile_sequence(else_actions, next_id=next_action_id)

            self._compiled[node_id] = CompiledAction(action=node, default_next=next_action_id)
            next_action_id = node_id

        return next_action_id

    # ----------------- execution -----------------

    def _execute_action(self, action: dict[str, Any], default_next: str | None) -> str | None:
        kind = str(action.get("kind"))
        action_id = str(action.get("id"))

        match kind:
            case "SendActivity":
                activity = action.get("activity")
                if not isinstance(activity, str):
                    raise WorkflowRuntimeError(f"SendActivity {action_id} requires 'activity' string")
                print(self._render_template(activity))
                return default_next

            case "Question":
                property_path = action.get("property")
                if not isinstance(property_path, str) or not property_path:
                    raise WorkflowRuntimeError(f"Question {action_id} requires 'property'")

                always_prompt = bool(action.get("alwaysPrompt", False))
                if (not always_prompt) and (property_path in self._vars):
                    return default_next

                prompt = action.get("prompt")
                question = self._extract_question_text(prompt)

                entity = action.get("entity")
                entity_kind = None
                if isinstance(entity, dict):
                    entity_kind = entity.get("kind")

                value = self._prompt_user(question, entity_kind)
                self._vars[property_path] = value
                return default_next

            case "SetTextVariable":
                variable = action.get("variable")
                value = action.get("value")
                if not isinstance(variable, str) or not variable:
                    raise WorkflowRuntimeError(f"SetTextVariable {action_id} requires 'variable'")
                if not isinstance(value, str):
                    raise WorkflowRuntimeError(f"SetTextVariable {action_id} requires 'value' string")
                self._vars[variable] = self._render_template(value)
                return default_next

            case "SetVariable":
                # More general variable assignment than SetTextVariable.
                # - Supports non-string values as-is.
                # - For strings:
                #   - If value starts with '=', evaluate a minimal Power FX subset.
                #   - Else, treat as template text and render {Local.*} placeholders.
                variable = action.get("variable")
                value = action.get("value")
                if not isinstance(variable, str) or not variable:
                    raise WorkflowRuntimeError(f"SetVariable {action_id} requires 'variable'")
                self._vars[variable] = self._eval_set_variable_value(value)
                return default_next

            case "InvokeAzureAgent":
                agent = action.get("agent")
                if not (isinstance(agent, dict) and isinstance(agent.get("name"), str) and agent.get("name")):
                    raise WorkflowRuntimeError(f"InvokeAzureAgent {action_id} requires agent.name")
                agent_name = str(agent["name"])

                input_obj = action.get("input")
                if not isinstance(input_obj, dict) or not isinstance(input_obj.get("messages"), str):
                    raise WorkflowRuntimeError(f"InvokeAzureAgent {action_id} requires input.messages string")

                prompt = self._eval_messages_expr(str(input_obj["messages"]))
                response = self._agent_invoker.invoke(agent_name, prompt)

                output_obj = action.get("output")
                if isinstance(output_obj, dict) and isinstance(output_obj.get("messages"), str):
                    out_var = str(output_obj["messages"])
                    # Store as list of messages to match MessageText(Local.X) usage.
                    self._vars[out_var] = [response]
                return default_next

            case "ConditionGroup":
                conditions = action.get("conditions")
                if not isinstance(conditions, list) or not conditions:
                    raise WorkflowRuntimeError(f"ConditionGroup {action_id} requires conditions[]")

                for cond in conditions:
                    if not isinstance(cond, dict):
                        continue
                    cond_expr = cond.get("condition")
                    if not isinstance(cond_expr, str):
                        continue
                    if self._eval_condition(cond_expr):
                        cond_actions = cond.get("actions")
                        entry = None
                        if isinstance(cond_actions, list) and cond_actions:
                            entry = self._first_action_id(cond_actions)
                        return entry or default_next

                else_actions = action.get("elseActions")
                if isinstance(else_actions, list) and else_actions:
                    entry = self._first_action_id(else_actions)
                    return entry or default_next

                return default_next

            case "GotoAction":
                target = action.get("actionId")
                if not isinstance(target, str) or not target:
                    raise WorkflowRuntimeError(f"GotoAction {action_id} requires actionId")
                if target not in self._compiled:
                    raise WorkflowRuntimeError(f"GotoAction {action_id} targets unknown id: {target}")
                return target

            case "EndConversation":
                return None

            case _:
                raise WorkflowRuntimeError(f"Unsupported action kind: {kind} (action id: {action_id})")

    # ----------------- helpers -----------------

    def _first_action_id(self, actions: list[Any]) -> str | None:
        for node in actions:
            if isinstance(node, dict) and isinstance(node.get("id"), str) and node.get("id"):
                return str(node["id"])
        return None

    def _extract_question_text(self, prompt: Any) -> str:
        if not isinstance(prompt, dict):
            return ""
        if prompt.get("kind") != "Message":
            return ""
        text = prompt.get("text")
        if isinstance(text, list) and text and isinstance(text[0], str):
            return str(text[0])
        if isinstance(text, str):
            return text
        return ""

    def _prompt_user(self, question: str, entity_kind: Any) -> Any:
        if not self._interactive:
            raise WorkflowRuntimeError("Non-interactive mode: Question requires input")

        raw = input((question.strip() + " ") if question else "> ")
        if entity_kind == "NumberPrebuiltEntity":
            return _coerce_number(raw)
        if entity_kind == "BooleanPrebuiltEntity":
            return _coerce_bool(raw)
        # Default: string
        return raw

    def _render_template(self, text: str) -> str:
        # Replace {Local.X}, {MessageText(Local.Y)} and {JsonEscape(...)} placeholders.

        def _json_escape(value: Any) -> str:
            # Return a string that is safe to embed inside JSON string literals.
            s = _message_text(value)
            dumped = json.dumps(s, ensure_ascii=False)
            # json.dumps returns a quoted string, strip outer quotes.
            return dumped[1:-1] if len(dumped) >= 2 else ""

        def repl(match: re.Match[str]) -> str:
            inner = match.group(1).strip()
            if inner.startswith("MessageText(") and inner.endswith(")"):
                arg = inner[len("MessageText(") : -1].strip()
                return _message_text(self._vars.get(arg))
            if inner.startswith("JsonEscape(") and inner.endswith(")"):
                arg = inner[len("JsonEscape(") : -1].strip()
                if arg.startswith("MessageText(") and arg.endswith(")"):
                    inner_arg = arg[len("MessageText(") : -1].strip()
                    return _json_escape(self._vars.get(inner_arg))
                return _json_escape(self._vars.get(arg, ""))
            return str(self._vars.get(inner, ""))

        return re.sub(r"\{([^{}]+)\}", repl, text)

    def _eval_condition(self, expr: str) -> bool:
        # Minimal Power FX subset for common patterns in sample workflows.
        e = expr.strip()
        if e.startswith("="):
            e = e[1:].strip()

        # not(x)
        m = re.match(r"(?i)^not\((.+)\)$", e)
        if m:
            return not self._eval_condition(m.group(1).strip())

        # x = true/false
        m = re.match(r"^(.+?)\s*=\s*(true|false)\s*$", e, flags=re.IGNORECASE)
        if m:
            left = m.group(1).strip()
            right = m.group(2).strip().lower() == "true"
            return bool(self._resolve_value(left)) == right

        return bool(self._resolve_value(e))

    def _resolve_value(self, token: str) -> Any:
        t = token.strip()
        if t in self._vars:
            return self._vars[t]
        if t.startswith("Local."):
            return self._vars.get(t)
        if t.startswith("System."):
            return None
        if t.startswith('"') and t.endswith('"'):
            return _unescape_powerfx_string(t[1:-1])
        if t.lower() in {"true", "false"}:
            return t.lower() == "true"
        return None

    def _eval_messages_expr(self, text: str) -> str:
        s = text.strip()
        if s.startswith("="):
            s = s[1:].strip()

        inner = _strip_outer(s, "UserMessage(", ")")
        if inner is not None:
            return self._eval_powerfx_concat(inner)

        # Plain variable reference: e.g. UserMessage(Local.DraftPrompt) is handled above.
        # If it's just Local.X, resolve it.
        if re.fullmatch(r"[A-Za-z]+\.[A-Za-z0-9_]+", s):
            return str(self._vars.get(s, ""))

        return self._render_template(text)

    def _eval_set_variable_value(self, value: Any) -> Any:
        if isinstance(value, str):
            s = value.strip()
            if s.startswith("="):
                expr = s[1:].strip()
                # Common patterns:
                # - =Local.X
                # - ="literal"
                # - ="a" & Local.X & "b" & MessageText(Local.Messages)
                if "&" in expr:
                    return self._eval_powerfx_concat(expr)
                return self._resolve_value(expr)

            return self._render_template(value)

        # Preserve YAML-native types (bool/number/object/list).
        return value

    def _eval_powerfx_concat(self, expr: str) -> str:
        parts = _split_top_level_concat(expr)
        out: list[str] = []
        for part in parts:
            out.append(self._eval_powerfx_term(part))
        return "".join(out)

    def _eval_powerfx_term(self, term: str) -> str:
        t = term.strip()
        if not t:
            return ""

        if t.startswith('"') and t.endswith('"'):
            return _unescape_powerfx_string(t[1:-1])

        # MessageText(Local.X)
        m = re.match(r"^MessageText\((.+)\)$", t)
        if m:
            arg = m.group(1).strip()
            return _message_text(self._vars.get(arg))

        # JsonEscape(MessageText(Local.X)) / JsonEscape(Local.X)
        m = re.match(r"^JsonEscape\((.+)\)$", t)
        if m:
            arg = m.group(1).strip()
            if arg.startswith("MessageText(") and arg.endswith(")"):
                inner_arg = arg[len("MessageText(") : -1].strip()
                dumped = json.dumps(_message_text(self._vars.get(inner_arg)), ensure_ascii=False)
                return dumped[1:-1] if len(dumped) >= 2 else ""
            dumped = json.dumps(str(self._vars.get(arg, "")), ensure_ascii=False)
            return dumped[1:-1] if len(dumped) >= 2 else ""

        # Local.X
        if re.fullmatch(r"Local\.[A-Za-z0-9_]+", t):
            return str(self._vars.get(t, ""))

        # Fall back: treat as template or unknown.
        return self._render_template(t)
