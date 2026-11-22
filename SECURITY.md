# Security Policy / 安全策略

## Reporting a Vulnerability / 漏洞反馈
Please report security issues privately via GitHub Security Advisories for `veawho/via54SciForge`.

## Built-in Safety Guarantees / 内置安全护栏
1. **AST Sandbox Enforcement**: All simulation and evolved candidate scripts pass `validate_ast_safety()` before subprocess execution, blocking `subprocess`, `socket`, `os.system`, `eval`, `exec`, and parent-directory escapes.
2. **Read-Only Sovereign KB**: Queries against `via54_kb.db` and `gold_vault_node_z.db` strictly enforce SQLite `?mode=ro` URI mode.
3. **No Embedded Credentials**: API keys are loaded strictly from runtime environment variables (`DEEPSEEK_API_KEY`, `OPENAI_API_KEY`, `GLM_API_KEY`, etc.).
