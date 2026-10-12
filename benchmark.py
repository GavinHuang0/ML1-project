"""Small reproducible pilot tasks and exact reference answers (no model calls)."""

import math
import random
from fractions import Fraction
from statistics import median


def posterior(clues):
    """Equal prior; clues are conditionally independent given the hidden state."""
    unique = {}
    for clue in clues:
        previous = unique.setdefault(clue["id"], clue)
        if previous != clue:
            raise ValueError("Conflicting observations with the same source ID")
    odds = sum((2 * clue["value"] - 1) * math.log(
        clue["reliability"] / (1 - clue["reliability"])) for clue in unique.values())
    return 1 / (1 + math.exp(-odds))


def make_tasks(count=4, seed=42):
    """Alternate reasoning and evidence tasks; never include gold answers in prompts."""
    rng = random.Random(seed)
    tasks = []
    for index in range(count):
        task_id = f"pilot-{seed}-{index:04d}"
        if index % 2 == 0:
            red, blue = rng.randint(2, 12), rng.randint(2, 12)
            total = red + blue
            both_red = Fraction(red * (red - 1), total * (total - 1))
            if (index // 2) % 2 == 0:
                answer = both_red
                event = "What is the probability that both balls are red?"
            else:
                at_least_one = 1 - Fraction(blue * (blue - 1), total * (total - 1))
                answer = both_red / at_least_one
                event = ("Given that at least one ball is red, what is the probability "
                         "that both balls are red?")
            tasks.append({"id": task_id, "family": "reasoning",
                          "prompt": f"An urn has {red} red and {blue} blue balls. "
                                    f"Draw two uniformly without replacement. {event}",
                          "gold_probability": float(answer), "gold_fraction": str(answer)})
        else:
            state = rng.randrange(2)
            clues = []
            for source in range(4):
                reliability = rng.choice([0.6, 0.75, 0.9])
                value = state if rng.random() < reliability else 1 - state
                clues.append({"id": f"S{source + 1}", "value": value,
                              "reliability": reliability})
            prompt = ("A hidden state Y is 0 or 1, each with prior probability 0.5. "
                      "Each UNIQUE sensor observation is conditionally independent given Y. "
                      "Reliability r means P(observation = Y | Y) = r for either state. "
                      "A repeated source ID is the SAME observation, not a new independent clue. "
                      "Compute P(Y=1 | these observations).\n" + clue_table(clues))
            tasks.append({"id": task_id, "family": "evidence", "prompt": prompt,
                          "clues": clues, "gold_state": state,
                          "gold_probability": posterior(clues)})
    return tasks


def clue_table(clues):
    return "\n".join(f"{c['id']}: observation={c['value']}, reliability={c['reliability']}"
                     for c in clues)


def probability(answer):
    """Require a fraction/decimal probability, not an embedded answer in prose."""
    try:
        value = float(Fraction(str(answer).strip()))
    except (ValueError, ZeroDivisionError, OverflowError, TypeError):
        return None
    return value if math.isfinite(value) and 0 <= value <= 1 else None


def correct(task, value):
    if value is None:
        return False
    if task["family"] == "evidence":
        return int(value >= 0.5) == task["gold_state"]
    return abs(value - task["gold_probability"]) <= 0.001


def ensemble(task, values):
    """Abstain on a tied plurality. Invalid answers abstain, and cannot win a vote."""
    votes = {}
    for value in values:
        if value is not None:
            vote = int(value >= 0.5) if task["family"] == "evidence" else round(value, 3)
            votes[vote] = votes.get(vote, 0) + 1
    if not votes:
        return {"answer": None, "correct": False, "abstained": True}
    highest = max(votes.values())
    winners = [vote for vote, n in votes.items() if n == highest]
    if len(winners) != 1:
        return {"answer": None, "correct": False, "abstained": True}
    winner = winners[0]
    if task["family"] == "evidence":
        answer = winner
        is_correct = winner == task["gold_state"]
    else:
        # Rounding groups equivalent votes; score their original median value.
        answer = median(value for value in values if value is not None and round(value, 3) == winner)
        is_correct = correct(task, answer)
    return {"answer": answer, "correct": is_correct, "abstained": False}
