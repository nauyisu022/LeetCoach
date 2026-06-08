Use when:
- user asks why code failed
- user clicks diagnose
- current run or submission failed

Required context:
- task metadata
- current code
- concrete failed assertion, stderr, or selected failing case when available
- relevant accepted learner memories

Output contract:
- conclusion
- smallest error point
- how the failing case triggers it
- invariant to maintain
- minimal fix direction
- next avoidance cue

Restrictions:
- diagnose from current failure context when it exists
- do not replace provided failure with a guessed different error
- do not invent a failed case
- do not provide a full rewritten solution unless explicitly requested
