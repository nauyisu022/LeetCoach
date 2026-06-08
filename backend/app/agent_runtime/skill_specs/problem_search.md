Use when:
- user asks for related, classic, similar, next, or practice problems
- problem search tool returned local catalog candidates

Required context:
- current task metadata
- local problem search tool result
- current topics and learner progress when available

Output contract:
- list relevant local catalog problems
- explain why each one is related
- recommend an order to practice
- ask whether the user wants one selected problem explained

Restrictions:
- prefer tool results over model memory
- do not invent problems not present in tool results
- if tool results are empty, say local catalog did not find matches
