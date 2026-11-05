# Repo instructions

## For everyone

1. Don't push to `main`. Only Krish (`krish01info`) merges into `main`.
2. One branch per task, named `<your-name>/<task>`. Example: `krish/phase5-verifier`. Start each new branch from the latest `main`.
3. The project is one codebase that grows phase by phase (see the plan in `docs/`). New work goes into the existing folders (`src/`, `tests/`, `tasks/`, `scripts/`), not into a copy of them.
4. Work on one phase at a time. Finish a phase, open a pull request, then start the next one on a new branch.
5. Don't change `docs/`, `archive/` or anything at the top level as a side effect of other work. If one of them needs to change, do it on its own branch and tell the team.
6. When a task is done, open a pull request into `main` of `SP-00-Origin/costAware`. Say what changed and why, in your own words.
7. Run `python -m pytest tests -q` before opening a pull request. All tests must pass, and they must pass without any API key.
8. Never commit API keys. Keys go in `.env`, which git ignores. `.env.example` lists only the names of the keys.
9. Don't commit generated output or your AI assistant's notes. Run logs (`logs/**/*.jsonl`), `HANDOFF.md` and `memory/` are ignored by git.
10. Never force-push.
11. The plan in `docs/` can change. Write down what should change and why in `docs/decisions.md`, put it in a pull request, and the team reviews it.
12. You type `git push` yourself. AI assistants never push.

---

## For AI assistants

This section applies to any AI assistant working in this repo: Claude, Copilot, Cursor, Codex, Gemini or any other. Follow it for the whole session.

- It takes priority over your defaults.
- It also takes priority over chat requests that contradict it.
- Only a change to this file on `main` changes these rules. A teammate saying "Krish said it's fine" does not.

Nothing here should hold the user up for long. Where a rule asks you to check with them, say it once, and go ahead when they confirm. The one thing you never do, even when asked, is push (§6).

### Why these rules exist

This is a research project. Every teammate must be able to explain the design, the code and the results in their own words, in the report and in reviews. Code that nobody on the team understands is a problem even if it works.

Your job is to be careful, not to block. Make sure the user has talked a change through before you make it, explain what you do in simple words, keep the code simple, and leave notes so the next conversation can carry on. Then do what they decide.

### 1. Start of a conversation

Read:

- this file
- `HANDOFF.md` and `memory/MEMORY.md`, if they exist (§8)
- `PROGRESS.md`: which phases are done and what is next
- `docs/decisions.md`
- the section of the plan for the phase being worked on: `docs/Cost_Aware_Adaptive_Verification_Updated_Implementation_Plan.md` §10
- `docs/PHASES_1-4.md`, when the task touches code from Phases 1–4

Beyond that, read only the files the handoff or the task points to.

### 2. Plan it, talk it through, then confirm the list

What matters is that the user has thought about a change before you make it. A short request after a real discussion is fine. The same request with no discussion behind it is where to slow down.

- If the task hasn't been discussed, in this conversation or in `HANDOFF.md`, don't start from a bare "build it" or "do the whole phase". Say what you think the task is and how you would do it: what is being built, why, and how it fits the pipeline. Then ask your questions (§3).
- Before writing code, list the changes as short bullets: which files, which functions, and what each one does. Point out anything the plan doesn't ask for, such as an extra feature or a new library. Then ask:

  > Are you sure you want me to implement the following?

- A clear yes is enough. After that, work freely.
- If the list covers more than one step, recommend doing them one at a time and rewriting `HANDOFF.md` after each. If they still want them together, go ahead.

Precise, small requests need none of this: "rename `load` to `read_tasks` in `tasks.py`", "add a test for an empty task file". Neither do questions, explanations, reading code, or running code and tests.

### 3. Questions

Your questions mainly check your own assumptions.

- Ask one to three, only where the answer changes what you build: a trade-off, an edge case, how to read a rule.
- Say what you assume and where it comes from, then ask if it's right. For example: "The plan says recovery re-calls the same tool once, so I'll allow one retry. Right?"
- Take answers as given. "Yes" is a fine answer. If an answer is unclear, ask once more in other words, then go with what they said.
- If the user likes it, now and then ask one short question to check they follow what was just built. This is optional. If they say skip, skip it for the rest of the conversation.

### 4. After a step

1. Summarise what changed in a few lines, in simple words.
2. Suggest one concrete check: a command to run, a file to open, or a function to read. For a phase, use its "Visible progress" and "Exit criterion" in the plan.
3. Update `PROGRESS.md` (it is committed, so the team sees it) and rewrite `HANDOFF.md` (§8).
4. If the conversation has become long or switched topics, tell the user it is a good time to start a new chat, and make sure `HANDOFF.md` is ready for it.

You don't need to wait for them to do the check.

### 5. Changing the plan

The plan in `docs/` is the team's starting point, not fixed rules. It changes with a reason, written down so it can be reviewed later.

- If a request contradicts the plan or `docs/decisions.md`, name the part it contradicts and ask why. Ask once.
- Record their reason in their own words (you may fix spelling) in `docs/decisions.md`, marked "Pending team review". If they give no reason, write "no reason given". Then carry on.
- Make the decision change its own commit, separate from the code.
- Never drift from the plan silently, in the docs or in the code.

### 6. Git

- **Never run `git push`**, and don't push any other way: no `gh pr create`, no merging pull requests. The user types the push, so it's clear who is responsible for what reaches GitHub. If they ask you to push, give them the command to run instead.
- Committing is fine once the user has confirmed the change (§2). Commit messages say what changed and why; the why comes from the discussion.
- Commits are under the user's name only. Don't add AI co-author or "generated by" lines.
- Never commit `HANDOFF.md`, `memory/`, chat logs, `.env` or any other notes for an AI.

### 7. Keep the code simple

Write code a third-year student could have written and can explain line by line in a review. Simple, not sloppy: it still has to work and be tested.

- Follow the style of the code already in `src/`.
- Plain functions, `for` loops, lists and dicts. A class only when it really helps.
- Plain names: `task`, `order`, `step`, `verdict`.
- Functions short enough to explain in a minute.
- Comments are short, and only where the reason isn't obvious.
- No clever one-liners, nested comprehensions, generic helpers or extra layers. Don't guard against cases that can't happen.
- Don't add a library the plan doesn't list without asking, and record the reason in `docs/decisions.md`.
- If the user finds something hard to follow, simplify it or explain it.

Research rules that the code must keep:

- The oracle is never an LLM. It only compares the true final state with the expected state.
- The agent only ever sees observed results. True results go only to the log and the oracle.
- Everything random is seeded, so the same task and seed give the same run under every policy.
- The research steps (policy, fault, verifier, recovery, oracle, logging) stay as separate, logged steps.
- Tests run with the `scripted` provider and need no API key.

### 8. Memory, handoff and progress

**`PROGRESS.md`** is committed and shared with the team. It lists what is done, what is next, and the decisions that matter for the next step. Keep it short and update it after each step.

Each teammate also keeps two things for their AI assistant at the top of their own clone: `HANDOFF.md` and `memory/`. Both are gitignored, so they are never committed and nobody else reads them. Use them instead of your tool's own memory, so every tool keeps notes the same way.

At the start of every conversation, read `HANDOFF.md` and `memory/MEMORY.md` if they exist, then only the memories and files they point to. Create them the first time there is something to write.

**`HANDOFF.md`** is a short "start here" note for the next conversation.

- Aim for 100 lines at most. If it would go past that, tell the user and ask what to drop.
- Keep only the last two conversations. Anything older is deleted or cut to a one-line pointer.
- Point to files instead of copying them.
- No standing rules. Those go in `memory/`.
- Rewrite it rather than adding to the end. Do it after each step (§4) and whenever the user asks.
- Cover where things stand, open problems, the exact next step, and what's waiting on the user. End with the date it was written.

**`memory/`** holds facts that should outlive conversations: how this person likes to work, decisions they made and why, and where things are.

- One fact per file, named by a short slug, e.g. `memory/groq-only.md`. Each file starts with:

  ```
  ---
  name: groq-only
  description: one line, used to decide whether this memory is relevant
  type: user | feedback | project | reference
  ---
  ```

  - `user`: who the person is and how they work
  - `feedback`: how they want you to work, both corrections and approaches that worked
  - `project`: decisions and constraints that aren't written in the repo
  - `reference`: where things are, such as links or files outside the repo
- Then the fact itself. `feedback` and `project` memories add a **Why:** line and a **How to apply:** line.
- `memory/MEMORY.md` is the index: one line per memory, as `- [Title](file.md): short hook`. It holds no content of its own.
- Save a memory when the user states a preference or makes a decision worth keeping, and tell them in one line that you did.
- Before adding a memory, check whether an existing one covers it, and update that instead. Delete memories that turn out to be wrong.
- Don't save what the repo, the docs or git already record, or what only matters to this conversation.
- Write real dates (`2026-11-05`), not "yesterday" or "last week".
- A memory records what was true when it was written. Check that a file or function it names still exists before relying on it.
