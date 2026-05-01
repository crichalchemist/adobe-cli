---
name: adobe-cli
description: >-
  Use when driving any Adobe desktop application from scripts or agents.
  Routes to the appropriate sub-skill: Premiere Pro 2025 (timeline, sequences,
  markers, AME export, vision), Illustrator 2026 (documents, layers, artboards,
  objects, text, swatches, export), or Acrobat DC (PDF conversion, page
  manipulation, merge, split, metadata). Each sub-skill specifies its own
  runtime requirements.
agent_guidance: >-
  Select the sub-skill that matches the target application. Each has its own
  installation, bridge requirements, and command surface. Always use --json
  for parseable output. Use absolute paths. Call `ping` first to verify the
  host application is running before issuing document commands.
---

# adobe-cli

Command-line harnesses for Adobe desktop applications. AI agents and shell
scripts can open projects, inspect timelines, manipulate documents, and trigger
exports — without touching a mouse.

## Sub-skills

| Skill | Application | Bridge |
|-------|-------------|--------|
| [cli-anything-premierepro](../premiere-pro/agent-harness/cli_anything/premierepro/skills/SKILL.md) | Adobe Premiere Pro 2025 | CEP panel → ExtendScript (HTTP on localhost:7788) |
| [cli-anything-illustrator](../illustrator/agent-harness/cli_anything/illustrator/skills/SKILL.md) | Adobe Illustrator 2026 | `osascript do javascript` + `#include` temp file |
| [cli-anything-acrobat](../acrobat/agent-harness/cli_anything/acrobat/skills/SKILL.md) | Adobe Acrobat DC | `osascript do script` → Acrobat JavaScript API |

## Choosing the Right Skill

- **Video editing, timelines, sequences, markers, AME export** → [`cli-anything-premierepro`](../premiere-pro/agent-harness/cli_anything/premierepro/skills/SKILL.md)
- **Vector artwork, layers, artboards, swatches, AI/EPS/SVG/PDF export** → [`cli-anything-illustrator`](../illustrator/agent-harness/cli_anything/illustrator/skills/SKILL.md)
- **PDF manipulation, format conversion, page operations, metadata** → [`cli-anything-acrobat`](../acrobat/agent-harness/cli_anything/acrobat/skills/SKILL.md)
