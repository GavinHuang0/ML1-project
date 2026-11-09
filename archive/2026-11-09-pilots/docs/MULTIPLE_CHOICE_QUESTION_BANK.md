# Exact-fraction multiple-choice question bank

This is the author review copy of the separate `mc-exact-v1` experiment. All sixteen questions have been used and inspected previously; neither cohort is held out. Mathematical wording and givens are preserved. Only the old instruction to return an unevaluated expression is removed where it existed.

Each block below is the exact user message sent for that question. The shared system prompt and procedure are in [the experiment design](MULTIPLE_CHOICE_EXPERIMENT.md). The [configuration](../config/multiple_choice_experiment.json) also records local answer keys, option rationales, source identifiers, and seeds; those annotations are not sent to the model.

Configuration SHA256: `c4fe818a796604087315d1df9bbfaf1f751e1695bb69b36d3713843390bf566f`.

## Model-visible questions

### 1. mc-fresh-urn-unconditional

Cohort: `syntax_reuse`; family: `reasoning`.

```text
An urn has 6 red and 9 blue balls. Draw two uniformly without replacement. What is the probability that both balls are red?

Options (exact values):
A. 15/98
B. 1/7
C. 5/23
D. 1/3
E. 6/7
F. 17/35
G. 1/8
H. 6/35
I. 2/15
J. 12/35
K. 2/5
L. 18/35
M. 4/25
N. 23/35
O. 9/35

Select exactly one option.
```

### 2. mc-fresh-urn-conditional

Cohort: `syntax_reuse`; family: `reasoning`.

```text
An urn has 7 red and 4 blue balls. Draw two uniformly without replacement. Given that at least one ball is red, what is the probability that both balls are red?

Options (exact values):
A. 42/121
B. 49/121
C. 3/5
D. 14/55
E. 7/9
F. 21/55
G. 7/11
H. 6/55
I. 21/68
J. 27/55
K. 34/55
L. 28/55
M. 49/55
N. 7/15
O. 3/7

Select exactly one option.
```

### 3. mc-fresh-sensor-01

Cohort: `syntax_reuse`; family: `evidence`.

```text
A hidden state Y is 0 or 1, each with prior probability 0.5. Each UNIQUE sensor observation is conditionally independent given Y. Reliability r means P(observation = Y | Y) = r for either state. A repeated source ID is the SAME observation, not a new independent clue. Compute P(Y=1 | these observations).
S1: observation=1, reliability=0.75
S2: observation=0, reliability=0.6
S3: observation=1, reliability=0.9

Options (exact values):
A. 3/400
B. 81/83
C. 81/200
D. 1/19
E. 1/18
F. 3/200
G. 18/19
H. 27/100
I. 1/2
J. 27/28
K. 2/3
L. 6/7
M. 27/200
N. 3/4
O. 41/60

Select exactly one option.
```

### 4. mc-fresh-sensor-02

Cohort: `syntax_reuse`; family: `evidence`.

```text
A hidden state Y is 0 or 1, each with prior probability 0.5. Each UNIQUE sensor observation is conditionally independent given Y. Reliability r means P(observation = Y | Y) = r for either state. A repeated source ID is the SAME observation, not a new independent clue. Compute P(Y=1 | these observations).
S1: observation=0, reliability=0.75
S2: observation=1, reliability=0.6
S3: observation=0, reliability=0.6

Options (exact values):
A. 1/3
B. 27/31
C. 13/20
D. 9/100
E. 9/50
F. 3/5
G. 3/4
H. 27/100
I. 2/5
J. 5/12
K. 2/11
L. 1/4
M. 1/2
N. 3/100
O. 3/50

Select exactly one option.
```

### 5. mc-fresh-algebra-01

Cohort: `syntax_reuse`; family: `algebra`.

```text
Solve 5*x + 7 = 42 for x.

Options (exact values):
A. 35/1
B. 7/5
C. 42/5
D. 13/2
E. 203/5
F. 35/4
G. 8/1
H. 15/2
I. 35/6
J. 175/1
K. 7/1
L. 49/5
M. 1/7
N. 77/5
O. 6/1

Select exactly one option.
```

### 6. mc-fresh-algebra-02

Cohort: `syntax_reuse`; family: `algebra`.

```text
Solve 6*x - 4 = 2*x + 20 for x.

Options (exact values):
A. 22/3
B. 3/1
C. 1/6
D. 8/1
E. 24/1
F. 4/1
G. 5/1
H. 62/3
I. 10/3
J. 8/3
K. 96/1
L. 24/5
M. 2/1
N. 6/1
O. 1/3

Select exactly one option.
```

### 7. mc-fresh-units-01

Cohort: `syntax_reuse`; family: `units`.

```text
A vehicle travels at a constant speed of 90 kilometres per hour for 14 minutes. How many kilometres does it travel?

Options (exact values):
A. 26/15
B. 21/2
C. 14/1
D. 63/5
E. 39/2
F. 21/1
G. 630/37
H. 42/1
I. 90/1
J. 45/7
K. 126/5
L. 3/2
M. 105/2
N. 7/20
O. 45/2

Select exactly one option.
```

### 8. mc-fresh-units-02

Cohort: `syntax_reuse`; family: `units`.

```text
A vehicle travels at a constant speed of 66 kilometres per hour for 45 minutes. How many kilometres does it travel?

Options (exact values):
A. 198/7
B. 253/5
C. 45/1
D. 99/1
E. 297/10
F. 242/5
G. 66/1
H. 495/4
I. 99/2
J. 297/5
K. 33/40
L. 11/10
M. 22/15
N. 99/4
O. 37/20

Select exactly one option.
```

### 9. mc-regression-calculator-pilot-42-0000

Cohort: `pilot_reuse`; family: `reasoning`.

```text
An urn has 12 red and 3 blue balls. Draw two uniformly without replacement. What is the probability that both balls are red?

Options (exact values):
A. 6/35
B. 1/35
C. 4/5
D. 22/35
E. 11/15
F. 16/25
G. 11/20
H. 33/49
I. 13/35
J. 11/17
K. 44/75
L. 12/35
M. 23/35
N. 24/35
O. 34/35

Select exactly one option.
```

### 10. mc-regression-calculator-pilot-42-0001

Cohort: `pilot_reuse`; family: `evidence`.

```text
A hidden state Y is 0 or 1, each with prior probability 0.5. Each UNIQUE sensor observation is conditionally independent given Y. Reliability r means P(observation = Y | Y) = r for either state. A repeated source ID is the SAME observation, not a new independent clue. Compute P(Y=1 | these observations).
S1: observation=0, reliability=0.9
S2: observation=0, reliability=0.6
S3: observation=1, reliability=0.6
S4: observation=0, reliability=0.9

Options (exact values):
A. 2/245
B. 729/2500
C. 729/733
D. 243/1250
E. 1/82
F. 81/82
G. 3/4
H. 3/2500
I. 1/2
J. 3/1250
K. 1/55
L. 243/2500
M. 3/10
N. 1/10
O. 1/81

Select exactly one option.
```

### 11. mc-regression-calculator-pilot-42-0002

Cohort: `pilot_reuse`; family: `reasoning`.

```text
An urn has 8 red and 2 blue balls. Draw two uniformly without replacement. Given that at least one ball is red, what is the probability that both balls are red?

Options (exact values):
A. 29/45
B. 28/71
C. 4/5
D. 28/45
E. 16/45
F. 2/3
G. 1/45
H. 28/29
I. 14/25
J. 7/11
K. 8/45
L. 17/45
M. 44/45
N. 16/25
O. 7/9

Select exactly one option.
```

### 12. mc-regression-calculator-pilot-42-0003

Cohort: `pilot_reuse`; family: `evidence`.

```text
A hidden state Y is 0 or 1, each with prior probability 0.5. Each UNIQUE sensor observation is conditionally independent given Y. Reliability r means P(observation = Y | Y) = r for either state. A repeated source ID is the SAME observation, not a new independent clue. Compute P(Y=1 | these observations).
S1: observation=0, reliability=0.6
S2: observation=0, reliability=0.9
S3: observation=0, reliability=0.9
S4: observation=0, reliability=0.9

Options (exact values):
A. 7/40
B. 1/2
C. 2/2189
D. 1/10
E. 1/487
F. 2187/5000
G. 33/40
H. 2187/2189
I. 2/5
J. 1/2500
K. 2187/10000
L. 1/5000
M. 2/2187
N. 2/245
O. 1/730

Select exactly one option.
```

### 13. mc-regression-calculator-algebra-01

Cohort: `pilot_reuse`; family: `algebra`.

```text
Solve 4*x - 11 = 21 for x.

Options (exact values):
A. 8/1
B. 5/2
C. 10/1
D. 1/8
E. 7/1
F. 32/3
G. 65/4
H. 9/1
I. 95/4
J. 21/4
K. 15/2
L. 17/2
M. 128/1
N. 32/5
O. 32/1

Select exactly one option.
```

### 14. mc-regression-calculator-algebra-02

Cohort: `pilot_reuse`; family: `algebra`.

```text
Solve 3*x + 5 = 2*x + 14 for x.

Options (exact values):
A. 9/1
B. 14/1
C. 10/1
D. 19/3
E. 1/9
F. 3/2
G. 14/3
H. 5/9
I. 19/1
J. 9/2
K. 19/5
L. 3/1
M. 9/5
N. 37/3
O. 29/3

Select exactly one option.
```

### 15. mc-regression-calculator-units-01

Cohort: `pilot_reuse`; family: `units`.

```text
A vehicle travels at a constant speed of 84 kilometres per hour for 35 minutes. How many kilometres does it travel?

Options (exact values):
A. 238/5
B. 119/60
C. 294/5
D. 35/1
E. 12/5
F. 252/5
G. 49/60
H. 49/1
I. 84/1
J. 588/19
K. 49/2
L. 98/1
M. 147/5
N. 245/2
O. 7/5

Select exactly one option.
```

### 16. mc-regression-calculator-units-02

Cohort: `pilot_reuse`; family: `units`.

```text
A vehicle travels at a constant speed of 96 kilometres per hour for 18 minutes. How many kilometres does it travel?

Options (exact values):
A. 288/5
B. 72/5
C. 432/25
D. 18/1
E. 16/3
F. 8/5
G. 12/25
H. 72/1
I. 96/1
J. 864/25
K. 136/5
L. 19/10
M. 144/5
N. 152/5
O. 288/13

Select exactly one option.
```

## Author answer key

This section is for review and scoring only. It is not part of any model message.

| # | Question ID | Correct choice | Exact value |
| --- | --- | --- | --- |
| 1 | `mc-fresh-urn-unconditional` | B | `1/7` |
| 2 | `mc-fresh-urn-conditional` | O | `3/7` |
| 3 | `mc-fresh-sensor-01` | G | `18/19` |
| 4 | `mc-fresh-sensor-02` | L | `1/4` |
| 5 | `mc-fresh-algebra-01` | K | `7/1` |
| 6 | `mc-fresh-algebra-02` | N | `6/1` |
| 7 | `mc-fresh-units-01` | F | `21/1` |
| 8 | `mc-fresh-units-02` | I | `99/2` |
| 9 | `mc-regression-calculator-pilot-42-0000` | D | `22/35` |
| 10 | `mc-regression-calculator-pilot-42-0001` | E | `1/82` |
| 11 | `mc-regression-calculator-pilot-42-0002` | J | `7/11` |
| 12 | `mc-regression-calculator-pilot-42-0003` | C | `2/2189` |
| 13 | `mc-regression-calculator-algebra-01` | A | `8/1` |
| 14 | `mc-regression-calculator-algebra-02` | A | `9/1` |
| 15 | `mc-regression-calculator-units-01` | H | `49/1` |
| 16 | `mc-regression-calculator-units-02` | M | `144/5` |

All options use reduced `n/d` notation, including integers such as `7/1`. Within each question the fifteen numeric values are distinct. Across the sixteen questions, A is correct twice and every other label is correct once. Wrong-choice rationales describe how the values were authored; they do not establish why a model chose them.
