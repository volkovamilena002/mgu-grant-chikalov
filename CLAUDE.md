@AGENTS.md

## Специфика Claude Code

- Навыки вызываются как `/kickoff`, `/next`, `/research-plan`, `/collect`, `/situation`, `/options`, `/strategy`, `/verify`, `/update`, `/decisions`, `/interviews`, `/data-analysis`, `/ux-review`.
- Субагентов из `.claude/agents/` вызывай через инструмент Agent (Task). Модель каждого субагента задана в его frontmatter.
- Хуки из `.claude/settings.json`:
  - `SessionStart` показывает статус активного проекта, поэтому в новом чате ты сразу знаешь, где остановились;
  - `PreToolUse(WebFetch)` проверяет домен по спискам проекта;
  - `PostToolUse(WebFetch|WebSearch)` пишет обращение в журнал и предупреждает о подозрительных инструкциях в контенте;
  - `Stop` и `SubagentStop` считают токены и стоимость по стадиям в `costs.jsonl`.
- Ворота G1, G2, G3 оформляй вопросом пользователю через AskUserQuestion: варианты и рекомендация первой.
