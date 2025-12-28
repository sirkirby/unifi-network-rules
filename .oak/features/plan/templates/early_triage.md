## Planning Source Decision

Before we begin, I need to understand what we're planning:

**Are you planning from:**

1. **A tracked issue** (Azure DevOps work item, GitHub issue, etc.)
   - You have an existing ticket/story/task to implement
   - Requirements are already documented in your issue tracker

2. **An idea or concept** (no existing issue)
   - You have an idea that needs scoping and planning
   - Requirements will be gathered through clarifying questions

**How to indicate your choice:**
- If you have an issue ID, mention it (e.g., "ADO #12345", "GitHub issue #42", or just "#123")
- If starting from an idea, describe what you want to plan

**Parse $ARGUMENTS to detect:**
- Issue ID patterns: `#\d+`, `ADO \d+`, `GitHub #\d+`, `issue \d+`
- If no issue pattern detected, assume idea-first planning
- If ambiguous, ask the user to clarify
