# Hosted Agent YAML templates (MAF)

Purpose: a reusable skeleton for hosted agents (name/description/tags/protocols/env vars/model resources).

## Minimal template

```yaml
name: MyHostedAgent
displayName: "My Hosted Agent"
description: >
  One paragraph description.
metadata:
  authors:
    - Your Team
  tags:
    - Microsoft Agent Framework
    - Hosted

template:
  kind: hosted
  name: MyHostedAgent
  protocols:
    - protocol: responses
      version: v1
  environment_variables:
    - name: AZURE_OPENAI_ENDPOINT
      value: ${AZURE_OPENAI_ENDPOINT}
    - name: AZURE_OPENAI_DEPLOYMENT_NAME
      value: ${AZURE_OPENAI_DEPLOYMENT_NAME}

resources:
  - name: "gpt-5"
    kind: model
    id: gpt-5
```

## Conventions and tips

- `name`: stable unique identifier (commonly PascalCase, no spaces).
- `displayName`: human-friendly name.
- `description`: prefer `>` for multi-line folded text.
- `template.protocols`: commonly `responses` / `v1` (follow official samples).
- `environment_variables`: use `${ENV}` to reference externally injected environment variables.
- `resources`: declare at least one `kind: model` resource and keep names consistent with runtime configuration.
