## Flow Control & Conversation Continuity

**This workflow should be a continuous, proactive conversation.** Do NOT stop and wait after each question unless there is genuine ambiguity requiring clarification.

### Flow Control Rules

1. **Batch related questions together** - When gathering project metadata (name, author, tech stack, description), ask ALL in one message, not sequentially with pauses.

2. **Continue automatically when context is clear** - If the user has provided enough information to proceed, move forward without asking "should I continue?"

3. **Decision points are checkpoints, not stop signs** - Present options, wait for the user's selection, then IMMEDIATELY continue to the next step. Don't stop and ask "ready to continue?"

4. **Maintain momentum** - After each user response, acknowledge it briefly and move to the next logical step in the same message.

### Handling Pauses

Only pause and explicitly wait for user input when:
- You need a specific decision the user hasn't provided
- There's genuine ambiguity about requirements
- You're at a CRITICAL CHECKPOINT (marked with CHECKPOINT)
- You've completed the entire workflow and need final approval

**Anti-pattern:** "Would you like me to continue?" / "Ready for the next step?" / "Shall I proceed?"
**Better:** Just continue. If the user wants to pause, they'll tell you.
