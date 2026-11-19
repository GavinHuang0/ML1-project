# Full study: all 100 questions for inspection

These are the exact prompts from the existing full benchmark. Metadata appears outside each prompt. Reference answers and generator parameters are omitted. The new five-agent study regenerates all trajectories; development questions have already been inspected in earlier pilots, while validation/test model inference has not been performed.

| Partition | Questions | Structural groups |
| --- | ---: | ---: |
| Development | 20 | 12 |
| Validation | 40 | 20 |
| Test | 40 | 20 |

[Machine-readable question-only export](FULL_STUDY_QUESTIONS.json) · [Runner and frozen study procedure](FULL_EXPERIMENT.md)

Source SHA256: `96933a962d4ea778ddbe22b66dd740a4dd1d46c2a82daa14395adc8c8b3ecb62`.

## Development — 20 questions

### Reasoning — 5 questions

#### 1. full-v1-reasoning-development-01

Structural group: `full-v1-reasoning-two_red`. Probability response: yes.

```text
An urn contains 4 red and 3 blue balls. Draw 2 balls uniformly in order without replacement. What is the probability that both drawn balls are red?
```

#### 2. full-v1-reasoning-development-02

Structural group: `full-v1-reasoning-red_given_any_red`. Probability response: yes.

```text
An urn contains 4 red and 4 blue balls. Draw 3 balls uniformly in order without replacement. Given that at least one drawn ball is red, what is the probability that all three are red?
```

#### 3. full-v1-reasoning-development-03

Structural group: `full-v1-reasoning-red_given_any_red`. Probability response: yes.

```text
An urn contains 4 red and 5 blue balls. Draw 3 balls uniformly in order without replacement. Given that at least one drawn ball is red, what is the probability that all three are red?
```

#### 4. full-v1-reasoning-development-04

Structural group: `full-v1-reasoning-one_of_each`. Probability response: yes.

```text
An urn contains 5 red and 4 blue balls and 3 green balls. Draw 3 balls uniformly in order without replacement. What is the probability that the three drawn balls include exactly one ball of each color?
```

#### 5. full-v1-reasoning-development-05

Structural group: `full-v1-reasoning-one_of_each`. Probability response: yes.

```text
An urn contains 6 red and 3 blue balls and 2 green balls. Draw 3 balls uniformly in order without replacement. What is the probability that the three drawn balls include exactly one ball of each color?
```

### Evidence — 5 questions

#### 6. full-v1-evidence-development-01

Structural group: `full-v1-evidence-one_positive`. Probability response: yes.

```text
A hidden state Y is either 0 or 1. The prior probability P(Y=1) is 3/5; P(Y=0) is its complement. Distinct sensor source IDs are conditionally independent given Y. Reliability r means P(observation=Y | Y)=r for either state. A repeated source ID repeats the SAME observation and must be counted only once.
S1: observation=1, reliability=3/4
What is P(Y=1 | all the listed observations)?
```

#### 7. full-v1-evidence-development-02

Structural group: `full-v1-evidence-three_majority_positive`. Probability response: yes.

```text
A hidden state Y is either 0 or 1. The prior probability P(Y=1) is 3/10; P(Y=0) is its complement. Distinct sensor source IDs are conditionally independent given Y. Reliability r means P(observation=Y | Y)=r for either state. A repeated source ID repeats the SAME observation and must be counted only once.
S1: observation=1, reliability=4/5
S2: observation=0, reliability=3/4
S3: observation=1, reliability=4/5
What is P(Y=1 | all the listed observations)?
```

#### 8. full-v1-evidence-development-03

Structural group: `full-v1-evidence-three_majority_positive`. Probability response: yes.

```text
A hidden state Y is either 0 or 1. The prior probability P(Y=1) is 3/5; P(Y=0) is its complement. Distinct sensor source IDs are conditionally independent given Y. Reliability r means P(observation=Y | Y)=r for either state. A repeated source ID repeats the SAME observation and must be counted only once.
S1: observation=1, reliability=3/5
S2: observation=0, reliability=7/10
S3: observation=1, reliability=3/4
What is P(Y=1 | all the listed observations)?
```

#### 9. full-v1-evidence-development-04

Structural group: `full-v1-evidence-four_majority_positive_query_zero`. Probability response: yes.

```text
A hidden state Y is either 0 or 1. The prior probability P(Y=1) is 2/5; P(Y=0) is its complement. Distinct sensor source IDs are conditionally independent given Y. Reliability r means P(observation=Y | Y)=r for either state. A repeated source ID repeats the SAME observation and must be counted only once.
S1: observation=1, reliability=7/10
S2: observation=1, reliability=9/10
S3: observation=0, reliability=9/10
S4: observation=1, reliability=7/10
What is P(Y=0 | all the listed observations)?
```

#### 10. full-v1-evidence-development-05

Structural group: `full-v1-evidence-four_majority_positive_query_zero`. Probability response: yes.

```text
A hidden state Y is either 0 or 1. The prior probability P(Y=1) is 7/10; P(Y=0) is its complement. Distinct sensor source IDs are conditionally independent given Y. Reliability r means P(observation=Y | Y)=r for either state. A repeated source ID repeats the SAME observation and must be counted only once.
S1: observation=1, reliability=3/5
S2: observation=1, reliability=9/10
S3: observation=0, reliability=3/4
S4: observation=1, reliability=7/10
What is P(Y=0 | all the listed observations)?
```

### Algebra — 5 questions

#### 11. full-v1-algebra-development-01

Structural group: `full-v1-algebra-affine`. Probability response: no.

```text
Solve 4*x+7 = (-13) for x. Return an unevaluated arithmetic expression for x in expression.
```

#### 12. full-v1-algebra-development-02

Structural group: `full-v1-algebra-rectangle_perimeter`. Probability response: no.

```text
A rectangle has width x metres and length x+6 metres. Its perimeter is 24 metres. Find x. Return an unevaluated arithmetic expression for x in expression.
```

#### 13. full-v1-algebra-development-03

Structural group: `full-v1-algebra-rectangle_perimeter`. Probability response: no.

```text
A rectangle has width x metres and length x+4 metres. Its perimeter is 28 metres. Find x. Return an unevaluated arithmetic expression for x in expression.
```

#### 14. full-v1-algebra-development-04

Structural group: `full-v1-algebra-mixture`. Probability response: no.

```text
Mix 4 litres of solution containing 2 grams/litre with x litres containing 8 grams/litre. Volumes add and the final concentration is 6 grams/litre. Find x. Return an unevaluated arithmetic expression for x in expression.
```

#### 15. full-v1-algebra-development-05

Structural group: `full-v1-algebra-mixture`. Probability response: no.

```text
Mix 2 litres of solution containing 3 grams/litre with x litres containing 8 grams/litre. Volumes add and the final concentration is 11/2 grams/litre. Find x. Return an unevaluated arithmetic expression for x in expression.
```

### Units — 5 questions

#### 16. full-v1-units-development-01

Structural group: `full-v1-units-speed_minutes`. Probability response: no.

```text
A cyclist maintains 71 kilometres/hour for 38 minutes. What distance in kilometres is covered?
```

#### 17. full-v1-units-development-02

Structural group: `full-v1-units-two_inflows_and_drain`. Probability response: no.

```text
An empty 128-litre tank has two constant inflows of 10 and 7 litres/minute and a simultaneous drain of 2 litres/minute. How many minutes until full?
```

#### 18. full-v1-units-development-03

Structural group: `full-v1-units-two_inflows_and_drain`. Probability response: no.

```text
An empty 293-litre tank has two constant inflows of 10 and 10 litres/minute and a simultaneous drain of 2 litres/minute. How many minutes until full?
```

#### 19. full-v1-units-development-04

Structural group: `full-v1-units-average_with_pause`. Probability response: no.

```text
A traveller covers 89 kilometres while moving at 60 kilometres/hour and also pauses for 22 minutes. What is the average speed over the entire elapsed time, including the pause, in kilometres/hour?
```

#### 20. full-v1-units-development-05

Structural group: `full-v1-units-average_with_pause`. Probability response: no.

```text
A traveller covers 60 kilometres while moving at 81 kilometres/hour and also pauses for 9 minutes. What is the average speed over the entire elapsed time, including the pause, in kilometres/hour?
```

## Validation — 40 questions

### Reasoning — 10 questions

#### 21. full-v1-reasoning-validation-01

Structural group: `full-v1-reasoning-one_red`. Probability response: yes.

```text
An urn contains 5 red and 5 blue balls. Draw 2 balls uniformly in order without replacement. What is the probability that exactly one drawn ball is red?
```

#### 22. full-v1-reasoning-validation-02

Structural group: `full-v1-reasoning-one_red`. Probability response: yes.

```text
An urn contains 5 red and 6 blue balls. Draw 2 balls uniformly in order without replacement. What is the probability that exactly one drawn ball is red?
```

#### 23. full-v1-reasoning-validation-03

Structural group: `full-v1-reasoning-same_color`. Probability response: yes.

```text
An urn contains 3 red and 6 blue balls. Draw 2 balls uniformly in order without replacement. What is the probability that the two drawn balls have the same color?
```

#### 24. full-v1-reasoning-validation-04

Structural group: `full-v1-reasoning-same_color`. Probability response: yes.

```text
An urn contains 6 red and 4 blue balls. Draw 2 balls uniformly in order without replacement. What is the probability that the two drawn balls have the same color?
```

#### 25. full-v1-reasoning-validation-05

Structural group: `full-v1-reasoning-first_given_last`. Probability response: yes.

```text
An urn contains 4 red and 5 blue balls. Draw 2 balls uniformly in order without replacement. Given that the second ball is red, what is the probability that the first ball is red?
```

#### 26. full-v1-reasoning-validation-06

Structural group: `full-v1-reasoning-first_given_last`. Probability response: yes.

```text
An urn contains 4 red and 4 blue balls. Draw 2 balls uniformly in order without replacement. Given that the second ball is red, what is the probability that the first ball is red?
```

#### 27. full-v1-reasoning-validation-07

Structural group: `full-v1-reasoning-majority_red`. Probability response: yes.

```text
An urn contains 4 red and 4 blue balls. Draw 3 balls uniformly in order without replacement. What is the probability that strictly more than half of the three drawn balls are red?
```

#### 28. full-v1-reasoning-validation-08

Structural group: `full-v1-reasoning-majority_red`. Probability response: yes.

```text
An urn contains 3 red and 4 blue balls. Draw 3 balls uniformly in order without replacement. What is the probability that strictly more than half of the three drawn balls are red?
```

#### 29. full-v1-reasoning-validation-09

Structural group: `full-v1-reasoning-blue_given_monochrome`. Probability response: yes.

```text
An urn contains 3 red and 3 blue balls. Draw 3 balls uniformly in order without replacement. Given that all three drawn balls have the same color, what is the probability that they are all blue?
```

#### 30. full-v1-reasoning-validation-10

Structural group: `full-v1-reasoning-blue_given_monochrome`. Probability response: yes.

```text
An urn contains 4 red and 4 blue balls. Draw 3 balls uniformly in order without replacement. Given that all three drawn balls have the same color, what is the probability that they are all blue?
```

### Evidence — 10 questions

#### 31. full-v1-evidence-validation-01

Structural group: `full-v1-evidence-one_negative`. Probability response: yes.

```text
A hidden state Y is either 0 or 1. The prior probability P(Y=1) is 2/5; P(Y=0) is its complement. Distinct sensor source IDs are conditionally independent given Y. Reliability r means P(observation=Y | Y)=r for either state. A repeated source ID repeats the SAME observation and must be counted only once.
S1: observation=0, reliability=3/5
What is P(Y=1 | all the listed observations)?
```

#### 32. full-v1-evidence-validation-02

Structural group: `full-v1-evidence-one_negative`. Probability response: yes.

```text
A hidden state Y is either 0 or 1. The prior probability P(Y=1) is 3/10; P(Y=0) is its complement. Distinct sensor source IDs are conditionally independent given Y. Reliability r means P(observation=Y | Y)=r for either state. A repeated source ID repeats the SAME observation and must be counted only once.
S1: observation=0, reliability=3/4
What is P(Y=1 | all the listed observations)?
```

#### 33. full-v1-evidence-validation-03

Structural group: `full-v1-evidence-two_conflict`. Probability response: yes.

```text
A hidden state Y is either 0 or 1. The prior probability P(Y=1) is 3/5; P(Y=0) is its complement. Distinct sensor source IDs are conditionally independent given Y. Reliability r means P(observation=Y | Y)=r for either state. A repeated source ID repeats the SAME observation and must be counted only once.
S1: observation=1, reliability=3/4
S2: observation=0, reliability=3/4
What is P(Y=1 | all the listed observations)?
```

#### 34. full-v1-evidence-validation-04

Structural group: `full-v1-evidence-two_conflict`. Probability response: yes.

```text
A hidden state Y is either 0 or 1. The prior probability P(Y=1) is 7/10; P(Y=0) is its complement. Distinct sensor source IDs are conditionally independent given Y. Reliability r means P(observation=Y | Y)=r for either state. A repeated source ID repeats the SAME observation and must be counted only once.
S1: observation=1, reliability=3/5
S2: observation=0, reliability=4/5
What is P(Y=1 | all the listed observations)?
```

#### 35. full-v1-evidence-validation-05

Structural group: `full-v1-evidence-three_majority_negative`. Probability response: yes.

```text
A hidden state Y is either 0 or 1. The prior probability P(Y=1) is 2/5; P(Y=0) is its complement. Distinct sensor source IDs are conditionally independent given Y. Reliability r means P(observation=Y | Y)=r for either state. A repeated source ID repeats the SAME observation and must be counted only once.
S1: observation=0, reliability=7/10
S2: observation=1, reliability=9/10
S3: observation=0, reliability=7/10
What is P(Y=0 | all the listed observations)?
```

#### 36. full-v1-evidence-validation-06

Structural group: `full-v1-evidence-three_majority_negative`. Probability response: yes.

```text
A hidden state Y is either 0 or 1. The prior probability P(Y=1) is 3/5; P(Y=0) is its complement. Distinct sensor source IDs are conditionally independent given Y. Reliability r means P(observation=Y | Y)=r for either state. A repeated source ID repeats the SAME observation and must be counted only once.
S1: observation=0, reliability=9/10
S2: observation=1, reliability=4/5
S3: observation=0, reliability=3/5
What is P(Y=0 | all the listed observations)?
```

#### 37. full-v1-evidence-validation-07

Structural group: `full-v1-evidence-four_balanced`. Probability response: yes.

```text
A hidden state Y is either 0 or 1. The prior probability P(Y=1) is 3/5; P(Y=0) is its complement. Distinct sensor source IDs are conditionally independent given Y. Reliability r means P(observation=Y | Y)=r for either state. A repeated source ID repeats the SAME observation and must be counted only once.
S1: observation=1, reliability=9/10
S2: observation=0, reliability=7/10
S3: observation=0, reliability=7/10
S4: observation=1, reliability=7/10
What is P(Y=1 | all the listed observations)?
```

#### 38. full-v1-evidence-validation-08

Structural group: `full-v1-evidence-four_balanced`. Probability response: yes.

```text
A hidden state Y is either 0 or 1. The prior probability P(Y=1) is 1/5; P(Y=0) is its complement. Distinct sensor source IDs are conditionally independent given Y. Reliability r means P(observation=Y | Y)=r for either state. A repeated source ID repeats the SAME observation and must be counted only once.
S1: observation=1, reliability=4/5
S2: observation=0, reliability=3/4
S3: observation=0, reliability=4/5
S4: observation=1, reliability=4/5
What is P(Y=1 | all the listed observations)?
```

#### 39. full-v1-evidence-validation-09

Structural group: `full-v1-evidence-four_with_duplicates`. Probability response: yes.

```text
A hidden state Y is either 0 or 1. The prior probability P(Y=1) is 3/5; P(Y=0) is its complement. Distinct sensor source IDs are conditionally independent given Y. Reliability r means P(observation=Y | Y)=r for either state. A repeated source ID repeats the SAME observation and must be counted only once.
S1: observation=1, reliability=9/10
S2: observation=0, reliability=3/4
S3: observation=1, reliability=3/5
S4: observation=0, reliability=7/10
S2: observation=0, reliability=3/4
S4: observation=0, reliability=7/10
What is P(Y=0 | all the listed observations)?
```

#### 40. full-v1-evidence-validation-10

Structural group: `full-v1-evidence-four_with_duplicates`. Probability response: yes.

```text
A hidden state Y is either 0 or 1. The prior probability P(Y=1) is 2/5; P(Y=0) is its complement. Distinct sensor source IDs are conditionally independent given Y. Reliability r means P(observation=Y | Y)=r for either state. A repeated source ID repeats the SAME observation and must be counted only once.
S1: observation=1, reliability=4/5
S2: observation=0, reliability=7/10
S3: observation=1, reliability=3/5
S4: observation=0, reliability=7/10
S2: observation=0, reliability=7/10
S4: observation=0, reliability=7/10
What is P(Y=0 | all the listed observations)?
```

### Algebra — 10 questions

#### 41. full-v1-algebra-validation-01

Structural group: `full-v1-algebra-both_sides`. Probability response: no.

```text
Solve 5*x+1 = 1*x+(47/3) for x. Return an unevaluated arithmetic expression for x in expression.
```

#### 42. full-v1-algebra-validation-02

Structural group: `full-v1-algebra-both_sides`. Probability response: no.

```text
Solve 6*x+2 = 4*x+(4/3) for x. Return an unevaluated arithmetic expression for x in expression.
```

#### 43. full-v1-algebra-validation-03

Structural group: `full-v1-algebra-distributed`. Probability response: no.

```text
Solve 5*(x+4) = (85) for x. Return an unevaluated arithmetic expression for x in expression.
```

#### 44. full-v1-algebra-validation-04

Structural group: `full-v1-algebra-distributed`. Probability response: no.

```text
Solve 4*(x+5) = (22) for x. Return an unevaluated arithmetic expression for x in expression.
```

#### 45. full-v1-algebra-validation-05

Structural group: `full-v1-algebra-three_consecutive`. Probability response: no.

```text
Three consecutive integers are x, x+1 and x+2, with sum 18. Find x. Return an unevaluated arithmetic expression for x in expression.
```

#### 46. full-v1-algebra-validation-06

Structural group: `full-v1-algebra-three_consecutive`. Probability response: no.

```text
Three consecutive integers are x, x+1 and x+2, with sum 24. Find x. Return an unevaluated arithmetic expression for x in expression.
```

#### 47. full-v1-algebra-validation-07

Structural group: `full-v1-algebra-two_fraction_terms`. Probability response: no.

```text
Solve (x-4)/4+(x+3)/9 = (31/12) for x. Return an unevaluated arithmetic expression for x in expression.
```

#### 48. full-v1-algebra-validation-08

Structural group: `full-v1-algebra-two_fraction_terms`. Probability response: no.

```text
Solve (x-7)/8+(x+3)/6 = (1/16) for x. Return an unevaluated arithmetic expression for x in expression.
```

#### 49. full-v1-algebra-validation-09

Structural group: `full-v1-algebra-nested_affine`. Probability response: no.

```text
Solve (x/4+1)/2+2 = (47/16) for x. Return an unevaluated arithmetic expression for x in expression.
```

#### 50. full-v1-algebra-validation-10

Structural group: `full-v1-algebra-nested_affine`. Probability response: no.

```text
Solve (x/6+6)/2+6 = (109/12) for x. Return an unevaluated arithmetic expression for x in expression.
```

### Units — 10 questions

#### 51. full-v1-units-validation-01

Structural group: `full-v1-units-fill_minutes`. Probability response: no.

```text
An empty tank needs 51 litres. Water enters at 4 litres/minute with no outflow. How many minutes are needed?
```

#### 52. full-v1-units-validation-02

Structural group: `full-v1-units-fill_minutes`. Probability response: no.

```text
An empty tank needs 79 litres. Water enters at 11 litres/minute with no outflow. How many minutes are needed?
```

#### 53. full-v1-units-validation-03

Structural group: `full-v1-units-two_legs_mixed_units`. Probability response: no.

```text
A vehicle travels at 55 kilometres/hour for 16 minutes, then at 12 metres/second for 100 seconds. What total distance in kilometres does it travel?
```

#### 54. full-v1-units-validation-04

Structural group: `full-v1-units-two_legs_mixed_units`. Probability response: no.

```text
A vehicle travels at 25 kilometres/hour for 14 minutes, then at 10 metres/second for 189 seconds. What total distance in kilometres does it travel?
```

#### 55. full-v1-units-validation-05

Structural group: `full-v1-units-density_mass`. Probability response: no.

```text
A liquid has density 21/10 grams per cubic centimetre. A sample has volume 593 millilitres; one millilitre equals one cubic centimetre. What is the mass in kilograms?
```

#### 56. full-v1-units-validation-06

Structural group: `full-v1-units-density_mass`. Probability response: no.

```text
A liquid has density 27/10 grams per cubic centimetre. A sample has volume 845 millilitres; one millilitre equals one cubic centimetre. What is the mass in kilograms?
```

#### 57. full-v1-units-validation-07

Structural group: `full-v1-units-two_leg_average_speed`. Probability response: no.

```text
A trip covers 43 kilometres at 39 kilometres/hour, then 49 kilometres at 79 kilometres/hour, with no stops. What is the average speed for the whole trip in kilometres/hour?
```

#### 58. full-v1-units-validation-08

Structural group: `full-v1-units-two_leg_average_speed`. Probability response: no.

```text
A trip covers 41 kilometres at 38 kilometres/hour, then 49 kilometres at 81 kilometres/hour, with no stops. What is the average speed for the whole trip in kilometres/hour?
```

#### 59. full-v1-units-validation-09

Structural group: `full-v1-units-dilution`. Probability response: no.

```text
A solution contains 18 grams of solute in 3 litres. Add 700 millilitres of pure water, with volumes adding and no solute lost. What is the final concentration in grams/litre?
```

#### 60. full-v1-units-validation-10

Structural group: `full-v1-units-dilution`. Probability response: no.

```text
A solution contains 44 grams of solute in 5 litres. Add 800 millilitres of pure water, with volumes adding and no solute lost. What is the final concentration in grams/litre?
```

## Test — 40 questions

### Reasoning — 10 questions

#### 61. full-v1-reasoning-test-01

Structural group: `full-v1-reasoning-any_red`. Probability response: yes.

```text
An urn contains 3 red and 5 blue balls. Draw 3 balls uniformly in order without replacement. What is the probability that at least one drawn ball is red?
```

#### 62. full-v1-reasoning-test-02

Structural group: `full-v1-reasoning-any_red`. Probability response: yes.

```text
An urn contains 4 red and 5 blue balls. Draw 3 balls uniformly in order without replacement. What is the probability that at least one drawn ball is red?
```

#### 63. full-v1-reasoning-test-03

Structural group: `full-v1-reasoning-ordered_red_blue`. Probability response: yes.

```text
An urn contains 5 red and 3 blue balls. Draw 2 balls uniformly in order without replacement. What is the probability that the first ball is red and the second is blue?
```

#### 64. full-v1-reasoning-test-04

Structural group: `full-v1-reasoning-ordered_red_blue`. Probability response: yes.

```text
An urn contains 3 red and 4 blue balls. Draw 2 balls uniformly in order without replacement. What is the probability that the first ball is red and the second is blue?
```

#### 65. full-v1-reasoning-test-05

Structural group: `full-v1-reasoning-no_red_three_colors`. Probability response: yes.

```text
An urn contains 5 red and 5 blue balls and 2 green balls. Draw 3 balls uniformly in order without replacement. What is the probability that none of the three drawn balls is red?
```

#### 66. full-v1-reasoning-test-06

Structural group: `full-v1-reasoning-no_red_three_colors`. Probability response: yes.

```text
An urn contains 5 red and 6 blue balls and 3 green balls. Draw 3 balls uniformly in order without replacement. What is the probability that none of the three drawn balls is red?
```

#### 67. full-v1-reasoning-test-07

Structural group: `full-v1-reasoning-two_red_given_first`. Probability response: yes.

```text
An urn contains 3 red and 4 blue balls. Draw 3 balls uniformly in order without replacement. Given that the first ball is red, what is the probability that exactly two of all three drawn balls are red?
```

#### 68. full-v1-reasoning-test-08

Structural group: `full-v1-reasoning-two_red_given_first`. Probability response: yes.

```text
An urn contains 6 red and 5 blue balls. Draw 3 balls uniformly in order without replacement. Given that the first ball is red, what is the probability that exactly two of all three drawn balls are red?
```

#### 69. full-v1-reasoning-test-09

Structural group: `full-v1-reasoning-endpoints_given_middle`. Probability response: yes.

```text
An urn contains 6 red and 4 blue balls. Draw 3 balls uniformly in order without replacement. Given that the second ball is blue, what is the probability that the first and third balls have the same color?
```

#### 70. full-v1-reasoning-test-10

Structural group: `full-v1-reasoning-endpoints_given_middle`. Probability response: yes.

```text
An urn contains 5 red and 3 blue balls. Draw 3 balls uniformly in order without replacement. Given that the second ball is blue, what is the probability that the first and third balls have the same color?
```

### Evidence — 10 questions

#### 71. full-v1-evidence-test-01

Structural group: `full-v1-evidence-two_positive`. Probability response: yes.

```text
A hidden state Y is either 0 or 1. The prior probability P(Y=1) is 1/5; P(Y=0) is its complement. Distinct sensor source IDs are conditionally independent given Y. Reliability r means P(observation=Y | Y)=r for either state. A repeated source ID repeats the SAME observation and must be counted only once.
S1: observation=1, reliability=3/5
S2: observation=1, reliability=7/10
What is P(Y=1 | all the listed observations)?
```

#### 72. full-v1-evidence-test-02

Structural group: `full-v1-evidence-two_positive`. Probability response: yes.

```text
A hidden state Y is either 0 or 1. The prior probability P(Y=1) is 2/5; P(Y=0) is its complement. Distinct sensor source IDs are conditionally independent given Y. Reliability r means P(observation=Y | Y)=r for either state. A repeated source ID repeats the SAME observation and must be counted only once.
S1: observation=1, reliability=4/5
S2: observation=1, reliability=3/4
What is P(Y=1 | all the listed observations)?
```

#### 73. full-v1-evidence-test-03

Structural group: `full-v1-evidence-two_negative_query_zero`. Probability response: yes.

```text
A hidden state Y is either 0 or 1. The prior probability P(Y=1) is 1/5; P(Y=0) is its complement. Distinct sensor source IDs are conditionally independent given Y. Reliability r means P(observation=Y | Y)=r for either state. A repeated source ID repeats the SAME observation and must be counted only once.
S1: observation=0, reliability=4/5
S2: observation=0, reliability=4/5
What is P(Y=0 | all the listed observations)?
```

#### 74. full-v1-evidence-test-04

Structural group: `full-v1-evidence-two_negative_query_zero`. Probability response: yes.

```text
A hidden state Y is either 0 or 1. The prior probability P(Y=1) is 3/10; P(Y=0) is its complement. Distinct sensor source IDs are conditionally independent given Y. Reliability r means P(observation=Y | Y)=r for either state. A repeated source ID repeats the SAME observation and must be counted only once.
S1: observation=0, reliability=4/5
S2: observation=0, reliability=4/5
What is P(Y=0 | all the listed observations)?
```

#### 75. full-v1-evidence-test-05

Structural group: `full-v1-evidence-duplicate_conflict`. Probability response: yes.

```text
A hidden state Y is either 0 or 1. The prior probability P(Y=1) is 4/5; P(Y=0) is its complement. Distinct sensor source IDs are conditionally independent given Y. Reliability r means P(observation=Y | Y)=r for either state. A repeated source ID repeats the SAME observation and must be counted only once.
S1: observation=1, reliability=4/5
S1: observation=1, reliability=4/5
S2: observation=0, reliability=4/5
What is P(Y=1 | all the listed observations)?
```

#### 76. full-v1-evidence-test-06

Structural group: `full-v1-evidence-duplicate_conflict`. Probability response: yes.

```text
A hidden state Y is either 0 or 1. The prior probability P(Y=1) is 7/10; P(Y=0) is its complement. Distinct sensor source IDs are conditionally independent given Y. Reliability r means P(observation=Y | Y)=r for either state. A repeated source ID repeats the SAME observation and must be counted only once.
S1: observation=1, reliability=4/5
S1: observation=1, reliability=4/5
S2: observation=0, reliability=4/5
What is P(Y=1 | all the listed observations)?
```

#### 77. full-v1-evidence-test-07

Structural group: `full-v1-evidence-four_majority_negative`. Probability response: yes.

```text
A hidden state Y is either 0 or 1. The prior probability P(Y=1) is 1/5; P(Y=0) is its complement. Distinct sensor source IDs are conditionally independent given Y. Reliability r means P(observation=Y | Y)=r for either state. A repeated source ID repeats the SAME observation and must be counted only once.
S1: observation=0, reliability=7/10
S2: observation=0, reliability=9/10
S3: observation=1, reliability=9/10
S4: observation=0, reliability=3/5
What is P(Y=1 | all the listed observations)?
```

#### 78. full-v1-evidence-test-08

Structural group: `full-v1-evidence-four_majority_negative`. Probability response: yes.

```text
A hidden state Y is either 0 or 1. The prior probability P(Y=1) is 1/5; P(Y=0) is its complement. Distinct sensor source IDs are conditionally independent given Y. Reliability r means P(observation=Y | Y)=r for either state. A repeated source ID repeats the SAME observation and must be counted only once.
S1: observation=0, reliability=3/5
S2: observation=0, reliability=3/4
S3: observation=1, reliability=9/10
S4: observation=0, reliability=7/10
What is P(Y=1 | all the listed observations)?
```

#### 79. full-v1-evidence-test-09

Structural group: `full-v1-evidence-three_positive_prior_odds`. Probability response: yes.

```text
A hidden state Y is either 0 or 1. Prior odds Y=1 to Y=0 are 2:3. Distinct sensor source IDs are conditionally independent given Y. Reliability r means P(observation=Y | Y)=r for either state. A repeated source ID repeats the SAME observation and must be counted only once.
S1: observation=1, reliability=7/10
S2: observation=1, reliability=3/4
S3: observation=1, reliability=9/10
What is P(Y=0 | all the listed observations)?
```

#### 80. full-v1-evidence-test-10

Structural group: `full-v1-evidence-three_positive_prior_odds`. Probability response: yes.

```text
A hidden state Y is either 0 or 1. Prior odds Y=1 to Y=0 are 7:3. Distinct sensor source IDs are conditionally independent given Y. Reliability r means P(observation=Y | Y)=r for either state. A repeated source ID repeats the SAME observation and must be counted only once.
S1: observation=1, reliability=7/10
S2: observation=1, reliability=3/4
S3: observation=1, reliability=9/10
What is P(Y=0 | all the listed observations)?
```

### Algebra — 10 questions

#### 81. full-v1-algebra-test-01

Structural group: `full-v1-algebra-divided_unknown`. Probability response: no.

```text
Solve x/7+4 = (32/7) for x. Return an unevaluated arithmetic expression for x in expression.
```

#### 82. full-v1-algebra-test-02

Structural group: `full-v1-algebra-divided_unknown`. Probability response: no.

```text
Solve x/2+4 = (11/3) for x. Return an unevaluated arithmetic expression for x in expression.
```

#### 83. full-v1-algebra-test-03

Structural group: `full-v1-algebra-fractional_coefficient`. Probability response: no.

```text
Solve 6*x/8+7 = (107/8) for x. Return an unevaluated arithmetic expression for x in expression.
```

#### 84. full-v1-algebra-test-04

Structural group: `full-v1-algebra-fractional_coefficient`. Probability response: no.

```text
Solve 2*x/7+1 = (29/7) for x. Return an unevaluated arithmetic expression for x in expression.
```

#### 85. full-v1-algebra-test-05

Structural group: `full-v1-algebra-ticket_mix`. Probability response: no.

```text
A booth sells 25 tickets: x adult tickets at 10 dollars each and the rest child tickets at 2 dollars each. Total receipts are 130 dollars. Find x. Return an unevaluated arithmetic expression for x in expression.
```

#### 86. full-v1-algebra-test-06

Structural group: `full-v1-algebra-ticket_mix`. Probability response: no.

```text
A booth sells 18 tickets: x adult tickets at 6 dollars each and the rest child tickets at 2 dollars each. Total receipts are 52 dollars. Find x. Return an unevaluated arithmetic expression for x in expression.
```

#### 87. full-v1-algebra-test-07

Structural group: `full-v1-algebra-successive_discounts`. Probability response: no.

```text
An original price of x dollars receives a discount of 3/10 of the current price, then a second discount of 1/5 of the reduced price. The final price is 1456/25 dollars. Find x. Return an unevaluated arithmetic expression for x in expression.
```

#### 88. full-v1-algebra-test-08

Structural group: `full-v1-algebra-successive_discounts`. Probability response: no.

```text
An original price of x dollars receives a discount of 3/10 of the current price, then a second discount of 2/5 of the reduced price. The final price is 1827/25 dollars. Find x. Return an unevaluated arithmetic expression for x in expression.
```

#### 89. full-v1-algebra-test-09

Structural group: `full-v1-algebra-distributed_both_sides`. Probability response: no.

```text
Solve 3*(x+1) = 3*(11-x) for x. Return an unevaluated arithmetic expression for x in expression.
```

#### 90. full-v1-algebra-test-10

Structural group: `full-v1-algebra-distributed_both_sides`. Probability response: no.

```text
Solve 3*(x+1) = 4*(10-x) for x. Return an unevaluated arithmetic expression for x in expression.
```

### Units — 10 questions

#### 91. full-v1-units-test-01

Structural group: `full-v1-units-area_cm_to_m`. Probability response: no.

```text
A rectangular panel is 149 centimetres long and 75 centimetres wide. What is its area in square metres?
```

#### 92. full-v1-units-test-02

Structural group: `full-v1-units-area_cm_to_m`. Probability response: no.

```text
A rectangular panel is 71 centimetres long and 113 centimetres wide. What is its area in square metres?
```

#### 93. full-v1-units-test-03

Structural group: `full-v1-units-remaining_fuel`. Probability response: no.

```text
A car starts with 41 litres of fuel and uses fuel at an efficiency of 9 kilometres/litre. After a 119-kilometre trip, how many litres remain?
```

#### 94. full-v1-units-test-04

Structural group: `full-v1-units-remaining_fuel`. Probability response: no.

```text
A car starts with 48 litres of fuel and uses fuel at an efficiency of 8 kilometres/litre. After a 62-kilometre trip, how many litres remain?
```

#### 95. full-v1-units-test-05

Structural group: `full-v1-units-worker_rate`. Probability response: no.

```text
Each of 5 workers produces 7 parts every 30 minutes at a constant rate. How many parts do they produce together in 3 hours with no breaks?
```

#### 96. full-v1-units-test-06

Structural group: `full-v1-units-worker_rate`. Probability response: no.

```text
Each of 4 workers produces 10 parts every 15 minutes at a constant rate. How many parts do they produce together in 4 hours with no breaks?
```

#### 97. full-v1-units-test-07

Structural group: `full-v1-units-electricity_cost`. Probability response: no.

```text
An appliance draws 500 watts continuously for 31 minutes. Electricity costs 19 cents per kilowatt-hour. What is the electricity cost in dollars? Ignore fees.
```

#### 98. full-v1-units-test-08

Structural group: `full-v1-units-electricity_cost`. Probability response: no.

```text
An appliance draws 1200 watts continuously for 27 minutes. Electricity costs 30 cents per kilowatt-hour. What is the electricity cost in dollars? Ignore fees.
```

#### 99. full-v1-units-test-09

Structural group: `full-v1-units-staged_pump`. Probability response: no.

```text
Fill an empty tank to 33 litres. First pump at 8 litres/minute for 3 minutes, then switch to 40 millilitres/second. How many seconds of second-stage pumping are needed to reach the target? There is no outflow.
```

#### 100. full-v1-units-test-10

Structural group: `full-v1-units-staged_pump`. Probability response: no.

```text
Fill an empty tank to 70 litres. First pump at 8 litres/minute for 6 minutes, then switch to 47 millilitres/second. How many seconds of second-stage pumping are needed to reach the target? There is no outflow.
```
