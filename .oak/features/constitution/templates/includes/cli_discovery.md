## CLI Help & Command Discovery

When you need to discover available CLI commands or their options:

```bash
oak --help                          # List all OAK commands
oak constitution --help             # List constitution subcommands
oak constitution create --help      # Get help for specific command
oak constitution analyze --help     # Get help for analyze command
```

**Key commands for this workflow:**
- `oak constitution analyze --json` - Analyze project, get classification
- `oak constitution create --json` - **PRIMARY COMMAND** - Creates constitution AND agent files automatically
- `oak constitution validate --json` - Validate constitution (optional, included in create)
