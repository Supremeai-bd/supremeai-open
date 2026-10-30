# Elicitation protocol (asking other AIs)

## Principles
- Ask for **checkable output**, not private reasoning. Request a brief rationale and evidence, never hidden chain-of-thought.
- Give every source the **same question text** so differences reflect the source, not the wording. Do not reveal another source's answer first (anchoring); compare afterwards.
- Include the context the answer depends on (stack, constraints, goal). Missing context produces confident but irrelevant answers.
- Prefer one clear question per request. Split compound questions.

## Standard prompt (paste to any AI)
```
Question: {question}
Context: {context, constraints, goal}

Please answer in this structure:
1. Answer (max 5 sentences)
2. Short rationale (why this answer; no step-by-step private reasoning needed)
3. Evidence: sources, documentation, data, or "none, from general knowledge"
4. Confidence: 0-100% and what would change it
5. Assumptions you made
6. Limitations and when this does NOT apply
7. Strongest counterargument or alternative approach
8. How I can verify this myself (a test, a command, a document)
Mark clearly if any claim is a guess or if you are unsure about recent facts.
```

## Variants
- **Decision question**: add "What are the risks of doing this, the risks of not doing it, and what happens if we wait?"
- **Failure/lesson question**: add "What was the root cause, what evidence supports it versus other explanations, and what would we do differently?"
- **Human-behavior question**: add "What evidence supports this about people in general, and how much varies by individual or culture?"
- **Second-round challenge** (Deep tier): show a *different* source's disagreeing claim and ask "Which parts of this do you accept or reject, and why?" Record the revised answer as a new record from the same source.

## Handling replies
- Quote or paraphrase faithfully; do not improve the claim while recording it.
- Record the source name, model/version if stated, method (`copy_paste`, `api`, `mcp`, `agent`), and time.
- Unsupported specifics (invented citations, exact numbers without a source, URLs you did not open) lower confidence and are listed in `limitations`. Check a cited source before treating it as evidence.
- A refusal or "I don't know" is valid data; record it, do not pressure the source into guessing.
