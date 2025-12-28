## Workflow Overview

**Your job: Gather decisions through reasoning. The CLI handles everything else.**

1. **Analyze project** - Run `oak constitution analyze --json` to understand the project
2. Establish shared context with the user (confirm classification, gather metadata)
3. Research technologies and patterns (capability-aware)
4. **Assess decision relevance** - Determine which decisions apply based on project type
5. **Gather user decisions** on RELEVANT areas (testing, code review, docs, CI/CD, architecture)
6. **Run combo command** - `oak constitution create --json` creates constitution + agent files + validates automatically
7. Review output and deliver final report

**Key insight:** The combo command handles file creation, agent file generation, and validation in one step. Focus your effort on steps 1-5 (reasoning and decision gathering).
