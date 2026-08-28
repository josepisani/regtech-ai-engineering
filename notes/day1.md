1) The basic unit of a language model is a token. A token can be a character, a word, or a part of a word (like -tion), depending on the model.It's the unit the model reads and writes.That makes it clear tokens aren't just an input-side concept; output is billed and generated in tokens too.

2) The context window is: The context window is the hard limit on how many tokens a model can handle in a single request — and input and output share it. A 200K window means your prompt plus the response you ask for must fit in 200K together, so a huge input directly shrinks the room left to answer in.

2,1) Temperature scales the sharpness of the probability distribution over the next token — 0 collapses it to always taking the most likely one, higher values spread the mass so less-likely tokens get picked.

Note about using Claude Code: If you let Claude Code decide what the script should do, you're reviewing someone else's design. If you decide first, you're checking work against your own spec — which is the actual job.


3a) The below is an example provided by Claude about how a well structured query should be sent to claude so that we get the output we need.
- Print a text in real time (chunk by chunk. The stream delivers text fragments as tokens are generated, and a chunk may be part of a word, a whole word, or punctuation, as oposed to printing the whole answer in a single block).
- Prints input and output tokens
- (TTFT- time-to-first-token) -> Print the time lapsep for the first token to be processed and the total latency. TTFT is responsiveness (how long until the user sees something), total is throughput (how long until it's done). A long answer can feel fast and be slow.
- Print the USD cost of the  request (The prices are taken from a cost table)
- Takes a prompt, an optional system prompt, temperature, max_tokens
- Runnable from the command line with the prompt as an argument
- Prints a human-readable summary AND returns the numbers as a dict

3,b) Why stream at all? -> streaming changes perceived latency, not real latency. Your run proves it — the user sees text at 0.936s instead of a blank screen until 1.103s. Same total time, same cost, same tokens. What streaming buys is that the wait becomes visible progress instead of dead air, which is the entire reason chat UIs feel usable. The secondary win: you can cancel mid-generation and stop paying for output you no longer want. What it does not improve: total latency, cost, or quality.

3,c) Where do input_tokens and output_tokens come from in your code, and why is it impossible to know output_tokens before the call finishes? -> stream.get_final_message().usage, which the server sends back after generation ends. You don't compute them; Anthropic counts them and reports them. That distinction matters because it means the count is authoritative for billing — you're not estimating.The model generates autoregressively, one token at a time, each conditioned on the last. It doesn't plan a length in advance. Generation ends when the model emits an end-of-turn token or hits max_tokens — so the total is only knowable once it stops. That's also why max_tokens is a ceiling, not a target.

3,d) Which single parameter most changes the cost of a call? Which most changes latency? -> Cost: "the model used" is true across models (Opus is 25× Haiku on output), but the question was about a parameter you control within one model — and there the answer is output length. Your own numbers: 16 input tokens cost $0.000016, 29 output tokens cost $0.000145. Nearly the same token count, 9× the cost. Output length is the cost lever, which is why max_tokens and "be concise" instructions are cost engineering, not style.// Latency: The model doesn't think harder about hard questions; it does the same fixed computation per token. Latency is driven by how many output tokens get generated, because each one is a separate forward pass. A 500-token easy answer takes far longer than a 50-token hard one. TTFT scales with input length (the prompt has to be processed first), and everything after TTFT scales with output length.So: output length drives both cost and latency.
3j) Refactor — request params assembled as a dict, temperature gated by model
- The request is now built as a `params` dict and passed as `client.messages.stream(**params)`. A key that is never added is unambiguously absent: no `None` to serialize as null, and no duplicated call sites for each combination of optional parameters.
- `TEMPERATURE_MODELS` is a module-level set of models that still accept sampling params. `temperature` is only inserted (via `extra_body`) when `MODEL` is in it; otherwise it is dropped with a `warnings.warn` instead of being sent and 400-ing.
- The default changed from `temperature=1.0` to `temperature=None`. Required by "warn only when explicitly passed": a plain default of 1.0 gives no way to tell an explicit 1.0 from an unset one, so the warning would fire on every call to a 5-series model and quickly be ignored. `None` means "caller said nothing"; behaviour is unchanged because 1.0 is the API's own default.
- Side effect worth noticing: the `omit` sentinel is now unused and was removed. A key never added to a dict already expresses "don't send this", so the concept had nothing left to do. `if system:` replaces it.
- Cost paid: `stream(**params)` loses static checking. With explicit keywords, `max_token=` was a local `TypeError` before any socket opened; through `**params` a bad key travels to the server and returns as a 400. Same trade already made for `extra_body`. Two free, local failures converted into paid, remote ones — acceptable here, but it is a real trade, not a free win.
- Verified all three paths against a fake client with no network call: temperature passes through on Haiku, is dropped with a warning on Opus 5, and stays silent when unset.

- Longer output costs both — dollars and latency, because every output token is a separate forward pass. Input length affects TTFT; output length affects everything after it. Model tier multiplies both.

---

WHAT SURPRISED ME (day 1 — for blog draft #1)

I was planning to run the AI Act classifier at `temperature=0` for consistency. On the models I would actually deploy, that parameter does not exist: sampling was removed from Opus 5, Sonnet 5 and Fable 5, and sending `temperature` returns a 400. The reflex I brought with me — "set temperature to 0 when you need a deterministic answer" — is not available on the current lineup, and the SDK doesn't even expose it as a keyword any more.

The deeper point is that `temperature=0` was never the guarantee it felt like. It only sharpens the token distribution toward the most likely token; it does not promise the same bytes twice. Floating-point non-associativity, server-side batching and routing, and any model update underneath a stable id all move the output. So a pipeline whose reliability rests on a sampling parameter is resting on a soft guarantee that happens to be *invisible* when it fails — the output still looks fine, it is just different from last time.

Which is why the classifier's determinism has to come from structure rather than sampling: a declared output schema, validation on the way out, and retry-on-invalid when validation fails. Those are hard constraints — the response either satisfies the schema or it is rejected and retried — and they keep working regardless of which model is behind the endpoint or what parameters that model accepts. Project 1 was already designed this way (tool calling + Pydantic + retry-on-invalid). Today I found the empirical reason that design is right instead of accepting it on faith: I wrote `temperature=1.0` into a probe, it raised a local `TypeError` on a parameter the SDK no longer has, and the whole assumption fell out from there.

Blog angle: "the parameter I reached for first didn't exist, and that was the lesson." Reliability that depends on a knob is only as durable as the knob. Reliability that depends on validating the output survives the knob being removed.

Sharpest framing for the post (use this line): the story is not "they took away my determinism knob" — it is "the knob was always a soft guarantee, and its removal just made the softness impossible to ignore."
Why this framing and not the complaint version: any reader who knows LLMs will object "temperature 0 was never deterministic either" inside one paragraph. Conceding that first is what turns the piece from a complaint into an argument. The real contrast is failure mode, not availability — reliability resting on a sampling parameter fails *invisibly* (the output still looks fine, it is just different from last time), while reliability resting on schema validation fails *loudly*, and a loud failure is one you can retry. Same principle as the MODEL/PRICING guard written the same day: put the check where the failure would otherwise be silent.

RUNNING LOG — day 1 (2026-08-27/28)
- Reached for `temperature=0` out of habit and it does not exist: anthropic 1.x removed sampling parameters from the typed method signature, because Opus 5 / Sonnet 5 / Fable 5 reject them. The failure was a local TypeError, not an API error — the SDK surface and the API surface are two different things, and the SDK one decides whether the code runs at all.
- Consequence for Project 1: the classifier's consistency cannot rest on a sampling knob that may not exist on the model I deploy. It has to come from a schema, validation and retry-on-invalid — which was already the plan, now with a reason behind it instead of faith.
- Output tokens cost 5x input across the whole lineup (Haiku 1/5, Sonnet 5 2/10, Opus 5 5/25, Fable 5 10/50 $/MTok). Read off the price table, not yet measured on a real call — the probe has only been exercised against import checks and a fake client so far. First real run is the thing that turns this line into evidence.
- Where a check belongs is decided by whether the failure is silent: a bad model id 404s loudly and needs no guard, a MODEL/PRICING mismatch prints a plausible wrong number forever and gets one at import. hello_claude.py is the live proof — still pricing Sonnet 5 at Sonnet 4.6 rates, ~50% high, never once complained.
