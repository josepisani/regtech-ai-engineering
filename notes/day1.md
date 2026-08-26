1) A token is: The basic unit of a language model is token. A token can be a character, a word, or a part of a word (like -tion), depending on the model.It's the unit the model reads and writes.That makes it clear tokens aren't just an input-side concept; output is billed and generated in tokens too.

2) The context window is: The context window is the hard limit on how many tokens a model can handle in a single request — and input and output share it. A 200K window means your prompt plus the response you ask for must fit in 200K together, so a huge input directly shrinks the room left to answer in.

3) Temperature scales the sharpness of the probability distribution over the next token — 0 collapses it to always taking the most likely one, higher values spread the mass so less-likely tokens get picked.

## Handoff → Mac, evening 2026-08-26
Done: Blocks 0, 1, 2. Gate item 1 complete (token, context window,
temperature all defined). Scratch files deleted.
Next: Block 3 — build src/llm_probe.py (95m). Spec it myself first (3a),
then Claude Code builds while I read each piece. Then blocks 4, 5, 6.
Note: Windows uses `py` and `.venv\Scripts\activate`; Mac uses
`python` and `source .venv/bin/activate`.