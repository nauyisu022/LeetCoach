# Claude-Code-Like Teaching Agent Runtime Design

Date: 2026-06-08
Status: Draft for user review

## Goal

Build a teaching Agent system for the LeetCode learning platform that makes the AI coach more consistent, more aware of the learner, and safer to improve over time.

The system should not be a generic chat box with saved history. It should be a small, observable teaching runtime inspired by Claude Code:

- commands for explicit user intent
- tools for real app state and database access
- hooks for lifecycle events
- skills for stable teaching workflows
- subagents for narrow expert tasks
- layered memory with user confirmation

The MVP should use the existing FastAPI + SQLite + React architecture and avoid introducing a heavy orchestration framework until the workflow complexity requires it.

## Current Project Context

The app already has the core raw materials for a learner-aware system:

- `coach_messages`: raw AI coach transcript, currently stored in the user database.
- `submissions`: formal submit history and failure summaries.
- `user_solutions`: current saved solution draft per task.
- `practice_notes`: user-editable per-problem review notes.
- `topic_memories`: longer-horizon topic-level learning summaries.
- `review_events`: spaced-review history and ratings.

After the recent DB split, catalog data and user data are separated:

- `data/catalog.db`: problem catalog and global metadata.
- `data/user.local.db`: user state, solutions, submissions, notes, memories, and coach messages.
- `data/app.db`: legacy database retained for migration/backward compatibility.

This design should keep that split: problem catalog remains read-mostly, learner state remains in the user database.

## Design Principles

1. Raw chat is not the knowledge base.
   `coach_messages` remains an audit trail and short-term conversational record. The long-term knowledge base should be extracted, summarized, reviewed, and scoped.

2. Explicit commands beat implicit guessing.
   The system should treat actions like `诊断`, `讲解`, `提示`, `生成笔记`, and `复习` as commands with defined behavior.

3. Tools read facts; agents explain.
   Agents should not guess current code, failures, notes, or memory. They should receive those through typed tool/context outputs.

4. Long-term memory needs permission.
   The system may propose a memory automatically, but writing durable learner memory should require user confirmation or an explicit policy.

5. Context should be compact and relevant.
   Do not inject full chat history by default. Use thread summaries, accepted memories, current failure context, and the last few messages.

6. Keep the first version lightweight.
   Implement the Claude-Code-like runtime directly in the backend before considering LangGraph, CrewAI, AutoGen, or another framework.

## Claude Code Concept Mapping

| Claude Code Concept | Teaching App Equivalent |
| --- | --- |
| `CLAUDE.md` / memory | learner profile and teaching policy |
| Slash commands | `/diagnose`, `/explain`, `/hint`, `/note`, `/review`, `/next` |
| Skills | repeatable teaching workflows such as diagnose failure or explain backtracking |
| MCP tools | typed app tools for judge, problems, notes, memory, submissions, recommendations |
| Hooks | `AfterRun`, `AfterSubmit`, `AfterCoachResponse`, `OnProblemSwitch`, `OnReviewRating` |
| Subagents | diagnosis, pedagogy, memory curator, review planner, test designer |
| Transcript | `coach_messages` |
| Compaction | `coach_thread_summaries` |
| Permission gates | accept/reject/edit proposed memories and notes |

## Runtime Architecture

```text
Teaching Runtime
  MainCoachAgent
    IntentRouter
    ContextBuilder
    CommandRegistry
    SkillRunner
    ToolRegistry
    HookRunner

  Tools
    ProblemTool
    JudgeTool
    SubmissionTool
    SolutionTool
    NoteTool
    MemoryTool
    RecommendationTool

  Skills
    diagnose_failure
    explain_algorithm
    give_hint
    create_review_note
    extract_learning_memory
    plan_review

  Subagents
    DiagnosisAgent
    PedagogyAgent
    MemoryCuratorAgent
    ReviewPlannerAgent
    TestDesignerAgent

  Memory Store
    coach_messages
    coach_thread_summaries
    practice_notes
    topic_memories
    user_memory_items
    learning_events
```

## Main Coach Agent

The Main Coach Agent is the orchestrator. It should not directly contain every teaching behavior.

Responsibilities:

- classify user intent
- normalize UI actions into commands
- build scoped context
- choose the right skill/subagent
- stream the response
- save raw transcript
- run post-response hooks

Inputs:

- `user_id`
- `task_id`
- command or free-form user message
- current code
- selected run/submission result
- selected custom case when available

Outputs:

- streamed assistant text
- saved `coach_messages`
- optional proposed memory items
- optional note draft
- optional review recommendation

## Commands

The UI buttons and chat commands should map to the same backend command registry.

Initial commands:

```text
/diagnose
  Diagnose the current code or current failure. Must use concrete failure context when available.

/explain
  Explain the problem and solution pattern. Does not need a failure.

/hint
  Give a bounded hint without revealing the full solution unless requested.

/code-review
  Review current code for logic issues, style, edge cases, and complexity.

/note
  Draft a review note from the current solution, failures, and discussion.

/memory
  Extract proposed learner memories from recent activity.

/review
  Generate a review plan for the current problem/topic.

/next
  Recommend the next practice problem.
```

Button mapping:

```text
讲解 -> /explain
诊断 -> /diagnose
AI 草稿 -> /note
复习 -> /review
下一题 -> /next
chat input -> routed free-form command
```

## Tools

Tools should return typed data. They should not produce prose.

### ProblemTool

Reads catalog data:

- problem title
- difficulty
- tags/topics
- prompt
- examples
- starter code
- known test metadata

### JudgeTool

Reads recent execution state:

- latest run result
- selected custom case result
- failed assertion
- stderr
- runtime
- pass/fail count

For `/diagnose`, current screen failure should override latest formal submission.

### SubmissionTool

Reads formal submission history and summarized failure patterns.

### SolutionTool

Reads current saved draft and optionally previous accepted code.

### NoteTool

Reads and writes user-reviewable `practice_notes`.

Writes should remain explicit: draft generation should not overwrite saved notes without confirmation.

### MemoryTool

Reads relevant memory and writes proposed or accepted memory.

It should support:

- fetch relevant task memories
- fetch relevant topic memories
- fetch learner profile items
- create proposed memory
- accept/reject/edit proposed memory
- archive stale memory

### RecommendationTool

Reads practice insights and recommends next tasks based on weak topics, review windows, and same-topic progression.

## Skills

Skills are stable prompt/workflow files checked into the repo. They should behave like local Claude Code skills: clear trigger conditions, required context, output format, and restrictions.

Proposed location:

```text
backend/app/agent_runtime/skills/
  diagnose_failure.md
  explain_algorithm.md
  give_hint.md
  create_review_note.md
  extract_learning_memory.md
  plan_review.md
```

Example `diagnose_failure` contract:

```text
Use when:
- user clicks /diagnose
- user asks why code is wrong
- latest run/submission failed

Required context:
- task
- code
- failure assertion or selected failing case when available
- relevant learner memories

Output:
- conclusion
- smallest error point
- how the failing case triggers it
- invariant to maintain
- minimal fix direction

Restrictions:
- do not give a full rewritten solution unless explicitly requested
- do not diagnose from old submission if current failure context exists
- do not invent a failed case
```

## Subagents

Subagents are narrow roles invoked by the Main Coach Agent or hooks.

### DiagnosisAgent

Purpose: identify the smallest code mistake and connect it to a concrete failing case.

Inputs:

- problem
- current code
- failed assertion/custom case
- recent submissions
- relevant learner memory

Output:

- structured diagnosis
- optional candidate learning event

### PedagogyAgent

Purpose: explain concepts in the user's preferred style.

Inputs:

- problem
- topic memories
- learner preferences
- requested depth

Output:

- teaching explanation
- examples
- recognition signals for future problems

### MemoryCuratorAgent

Purpose: extract durable learning signals from transcripts and submissions.

Inputs:

- latest user/assistant turn
- task metadata
- code/failure result
- existing memories

Output:

- proposed `learning_events`
- proposed `user_memory_items`
- suggested updates to `topic_memories`

### ReviewPlannerAgent

Purpose: decide what the user should review next.

Inputs:

- topic memories
- review events
- recent failures
- current queue

Output:

- review tasks
- reason
- suggested review time

### TestDesignerAgent

Purpose: create targeted custom cases that reveal the user's current bug.

Inputs:

- problem
- current code
- suspected bug

Output:

- custom cases
- expected outputs
- reason each case matters

## Hooks

Hooks run around app lifecycle events. They should be small and auditable.

### AfterRun

Triggered after `/api/runs`.

Actions:

- store run event if needed
- if failed, create a lightweight `learning_event` candidate
- make the failure available to `/diagnose`

### AfterSubmit

Triggered after formal submission.

Actions:

- update user problem state
- if failed, summarize failure pattern
- if passed, optionally identify solved pattern
- schedule memory extraction if the interaction is meaningful

### AfterCoachResponse

Triggered after streamed AI response completes.

Actions:

- save raw transcript
- run `MemoryCuratorAgent`
- create proposed memory items
- optionally update thread summary

### OnProblemSwitch

Triggered when user changes tasks.

Actions:

- compact current problem transcript into `coach_thread_summaries`
- persist dirty solution draft

### OnReviewRating

Triggered after user rates a review.

Actions:

- update review events
- adjust topic memory confidence
- update next review recommendation

## Memory Model

### Raw Transcript

Existing table:

```text
coach_messages
```

Use:

- audit trail
- UI transcript restoration
- short-term context for the current thread

Do not use:

- direct long-term knowledge base
- full prompt injection for every answer

### Thread Summary

New table:

```text
coach_thread_summaries
  id
  user_id
  task_id
  summary
  last_message_id
  created_at
  updated_at
```

Use:

- compact per-problem conversation context
- avoid sending many raw chat messages

### Learning Events

New table:

```text
learning_events
  id
  user_id
  task_id
  topic
  event_type
  content
  evidence_message_ids
  confidence
  created_at
```

Event types:

- `mistake`
- `insight`
- `confusion`
- `preference`
- `mastery`
- `review_need`

Use:

- structured evidence extracted from raw activity
- source material for memory and review planning

### User Memory Items

New table:

```text
user_memory_items
  id
  user_id
  memory_type
  scope
  topic
  task_id
  content
  source
  confidence
  status
  created_at
  updated_at
```

Memory types:

- `preference`
- `weakness`
- `strength`
- `habit`
- `goal`
- `strategy`

Scopes:

- `global`
- `topic`
- `task`

Statuses:

- `proposed`
- `accepted`
- `rejected`
- `archived`

Only `accepted` memories should be injected into future prompts by default.

## Context Building

The Context Builder should produce a bounded context package for each command.

For `/diagnose`:

```text
current problem
current code
current run/custom-case failure if available
latest formal submission failure only as fallback
task thread summary
accepted task/topic memories
learner preferences
last 2-4 raw chat messages
```

For `/explain`:

```text
current problem
topic memories
learner preferences
practice progress for the same topics
task note summary if available
```

For `/note`:

```text
current problem
current code
recent diagnosis
accepted memories
existing practice note
```

Context limits:

- prefer summaries over raw logs
- cap raw history to recent messages
- do not include rejected/archived memories
- include evidence IDs for traceability where possible

## Permission And Safety

Automatic:

- read problem/catalog data
- read current code
- read current failure
- save raw transcript
- create proposed memory
- update thread summary

Requires user confirmation:

- accept long-term user memory
- overwrite saved practice note
- mark a topic mastered
- modify code
- change review schedule manually

The UI should show proposed memory with accept/edit/reject controls.

## API Shape

Initial endpoints:

```text
POST /api/agent/command/stream
GET  /api/agent/memories?status=proposed
POST /api/agent/memories/{id}/accept
POST /api/agent/memories/{id}/reject
PUT  /api/agent/memories/{id}
GET  /api/agent/thread-summary/{task_id}
```

Existing `/api/coach/*/stream` endpoints can remain as compatibility wrappers, but internally they should call the command runtime:

```text
/api/coach/diagnose/stream -> /api/agent/command/stream command=/diagnose
/api/coach/explain/stream  -> /api/agent/command/stream command=/explain
/api/coach/chat/stream     -> /api/agent/command/stream command=auto
```

## Frontend Shape

Right learning panel should evolve from two tabs to three:

```text
AI 教练
Notes
Memory
```

AI 教练:

- existing chat stream
- command buttons
- optional command chips

Notes:

- existing practice note editor
- AI note draft remains explicit and user-controlled

Memory:

- proposed memories
- accepted memories
- source/evidence link
- accept/edit/reject/archive actions

## MVP Scope

The first implementation should be intentionally narrow:

1. Add command runtime for `/diagnose`, `/explain`, and free-form chat.
2. Add `learning_events`, `user_memory_items`, and `coach_thread_summaries`.
3. Add `AfterCoachResponse` hook.
4. Add `MemoryCuratorAgent` that extracts proposed memory from a completed coach turn.
5. Add a Memory tab for proposed/accepted memories.
6. Inject only accepted memories into future responses.
7. Keep `practice_notes` writes explicit and user-controlled.

Out of scope for MVP:

- autonomous multi-step study planning
- code modification by AI
- vector database
- external framework migration
- fully automatic long-term memory acceptance
- multi-user auth

## Implementation Phases

### Phase 1: Runtime Skeleton

- create `backend/app/agent_runtime/`
- define command schemas
- route `/api/agent/command/stream`
- adapt existing coach stream endpoints to use the command runtime
- keep behavior equivalent to current UI

### Phase 2: Memory Tables

- add `learning_events`
- add `user_memory_items`
- add `coach_thread_summaries`
- add migration/init logic in the user database
- add tests for schema creation and basic CRUD

### Phase 3: Memory Extraction Hook

- implement `AfterCoachResponse`
- run `MemoryCuratorAgent` after each completed stream
- create proposed memories only
- store evidence message IDs

### Phase 4: Memory UI

- add Memory tab
- show proposed and accepted memories
- support accept/edit/reject/archive
- display source task/topic when available

### Phase 5: Context Injection

- update Context Builder to include accepted memories
- cap injected memories by relevance and count
- add tests that rejected memories are not injected

### Phase 6: Thread Summaries

- summarize long raw threads
- use summary plus recent messages instead of the last 12 raw messages
- keep raw transcript available for inspection

## Testing Strategy

Backend:

- schema tests for new tables
- command routing tests
- context builder tests
- memory CRUD tests
- hook tests with mocked model output
- verify stream endpoints stay streaming
- verify rejected memories are excluded

Frontend:

- build test
- Memory tab renders proposed memories
- accept/edit/reject flows update state
- existing coach buttons still stream

Manual:

- fail a run, ask `/diagnose`, verify concrete failure context is used
- ask follow-up, verify accepted memory changes the answer
- reject a memory, verify it does not reappear in prompt context
- switch problem, verify thread summary updates

## Open Questions

1. Should proposed memories be created after every AI response, or only after diagnostic/note/review commands?
2. Should accepted task-level memories automatically update `practice_notes`, or stay separate?
3. Should memory extraction use the same model/provider as the coach, or a cheaper/faster model?
4. Should the Memory tab be a separate tab or integrated into Notes?
5. How aggressive should thread summarization be before it hides useful details?

## Recommendation

Start with the smallest useful loop:

```text
coach response -> proposed memory -> user accepts -> accepted memory affects next answer
```

This creates the core feedback loop that makes the AI more learner-aware without risking silent memory pollution.
