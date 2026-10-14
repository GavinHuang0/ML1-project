# Question selection

The [full protocol](../protocol.md) defines the task families and scoring. The generator is [`llm_debate/benchmark.py`](../../../llm_debate/benchmark.py).

## Current selection rule

`make_tasks(count, seed)` uses one seeded Python random generator. All generated questions are included in their generated order; selection does not depend on model answers.

| Positions (one-based) | Task | Random parameters |
| --- | --- | --- |
| Odd | Draw two balls from an urn without replacement | Red and blue counts independently uniform from 2 through 12 |
| Even | Infer a hidden state from four sensors | State uniform in {0,1}; reliability independently sampled from {0.6,0.75,0.9}; observation equals the state with that reliability |

Successive urn tasks alternate between unconditional probability and probability given at least one red draw. Sensor IDs S1 through S4 refer to four distinct conditionally independent sources within a task. The prior is 0.5. Reference answers are computed in Python and retained only for scoring.

The generator has no difficulty screen, question deduplication, hidden-state balancing, or implemented split assignment. With an odd question count, reasoning has one extra task. The seed-42 four-question example has hidden state 0 on both evidence tasks and should be treated as a wiring check.

## Save and verify the set

For a new run, replace the tutorial count and seed with the protocol's agreed values:

```sh
python3 -m experiments.communication_pilot.run --dry-run --questions 4 --seed 42 > experiments/communication_pilot/question-selection/tutorial-seed42-q4.json
```

The dry run makes no model calls. Its JSON contains task IDs, prompts, references, conditions, and expected calls per question. The filename above identifies a tutorial example, not the completed pilot's actual question set. Synthetic question manifests can be tracked in Git.

For the already-generated pilot, the `task` object in each original question record is the authoritative question artifact. Recover its actual settings from metadata and compare saved task objects across model runs. The runner currently regenerates tasks from count/seed; it does not load a frozen manifest. A saved manifest is a reviewable record, not an input option.

## Pilot versus held-out evaluation

Increasing the count while keeping the seed preserves the initial question prefix. Changing the seed can still repeat the finite urn templates. Neither operation alone establishes a held-out split. A future evaluation must implement grouped splitting and keep all parameter-equivalent questions and their variants together, then record assignments here before evaluation.

The existing `--seed` also sets response sampling seeds. Varying it changes both question instances and sampling; repeating responses on fixed questions needs a separate sampling-seed control or frozen-task input, which is not implemented yet.
