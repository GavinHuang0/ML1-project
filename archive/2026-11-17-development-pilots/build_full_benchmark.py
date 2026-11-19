"""Build and independently audit the synthetic, grouped full-study question bank.

No inference, downloads, or third-party packages are used. Existing files are
never overwritten: use --check, or --output with a new destination.
"""

import argparse
import ast
from collections import Counter, defaultdict
from fractions import Fraction
import itertools
import json
import math
from pathlib import Path
import random
import sys

from calculator import evaluate_expression
from multi_agent_protocol import validate_tasks


ROOT = Path(__file__).resolve().parent
DEFAULT_PATH = ROOT / "config/full_benchmark.json"
GENERATOR_VERSION = "synthetic-grouped-full-benchmark-v1"
SEED = 20261117
FAMILIES = ("reasoning", "evidence", "algebra", "units")
PARTITIONS = {
    "development": (0, 5, 9),
    "validation": (1, 3, 6, 8, 11),
    "test": (2, 4, 7, 10, 12),
}
TEMPLATES = {
    "reasoning": (
        ("two_red", "Two draws: both red", "easy"),
        ("one_red", "Two draws: exactly one red", "easy"),
        ("any_red", "Three draws: at least one red", "moderate"),
        ("same_color", "Two draws: both the same color", "moderate"),
        ("ordered_red_blue", "Two ordered draws: red then blue", "easy"),
        ("red_given_any_red", "Three draws: all red conditional on at least one red", "moderate"),
        ("first_given_last", "First draw red conditional on last draw red", "moderate"),
        ("no_red_three_colors", "Three-color urn: no red in three draws", "moderate"),
        ("majority_red", "Three draws: a strict red majority", "moderate"),
        ("one_of_each", "Three-color urn: one ball of every color", "hard"),
        ("two_red_given_first", "Three draws: exactly two red conditional on first red", "hard"),
        ("blue_given_monochrome", "Three draws: all blue conditional on monochrome", "hard"),
        ("endpoints_given_middle", "Three draws: matching endpoints conditional on blue middle", "hard"),
    ),
    "evidence": (
        ("one_positive", "One positive observation; posterior of state one", "easy"),
        ("one_negative", "One negative observation; posterior of state one", "easy"),
        ("two_positive", "Two agreeing positive sources", "moderate"),
        ("two_conflict", "Two conflicting distinct sources", "moderate"),
        ("two_negative_query_zero", "Two negative sources; posterior of state zero", "moderate"),
        ("three_majority_positive", "Three sources with positive majority", "moderate"),
        ("three_majority_negative", "Three sources with negative majority; query zero", "moderate"),
        ("duplicate_conflict", "Conflicting sources with a repeated positive source ID", "hard"),
        ("four_balanced", "Four sources with two positive and two negative observations", "hard"),
        ("four_majority_positive_query_zero", "Four sources with positive majority; query zero", "hard"),
        ("four_majority_negative", "Four sources with negative majority; query one", "hard"),
        ("four_with_duplicates", "Four conflicting sources plus two repeated IDs; query zero", "hard"),
        ("three_positive_prior_odds", "Three positive sources; prior odds given; query zero", "hard"),
    ),
    "algebra": (
        ("affine", "A coefficient and offset on one side", "easy"),
        ("both_sides", "Unknown on both sides", "moderate"),
        ("divided_unknown", "Unknown divided by a constant before an offset", "moderate"),
        ("distributed", "A coefficient multiplying a translated unknown", "moderate"),
        ("fractional_coefficient", "A fractional coefficient and additive offset", "moderate"),
        ("rectangle_perimeter", "Rectangle perimeter with related side lengths", "moderate"),
        ("three_consecutive", "Three consecutive integers with a known sum", "easy"),
        ("ticket_mix", "Two ticket prices with known count and receipts", "hard"),
        ("two_fraction_terms", "Two shifted fractions containing the unknown", "hard"),
        ("mixture", "Unknown added volume at a specified final concentration", "hard"),
        ("successive_discounts", "Original price from two successive fractional discounts", "hard"),
        ("nested_affine", "Two nested division/translation operations", "hard"),
        ("distributed_both_sides", "Translated unknowns distributed on both sides", "hard"),
    ),
    "units": (
        ("speed_minutes", "Distance from km/h and minutes", "easy"),
        ("fill_minutes", "Time from litres and litres/minute", "easy"),
        ("area_cm_to_m", "Area in square metres from centimetre side lengths", "moderate"),
        ("two_legs_mixed_units", "Total distance from two legs with different speed/time units", "moderate"),
        ("remaining_fuel", "Fuel remaining after a trip with km/litre efficiency", "moderate"),
        ("two_inflows_and_drain", "Tank filling with two inflows and one drain", "moderate"),
        ("density_mass", "Mass in kilograms from g/cm^3 and millilitres", "moderate"),
        ("worker_rate", "Team production from per-worker batch rates", "moderate"),
        ("two_leg_average_speed", "Average speed over two different-distance legs", "hard"),
        ("average_with_pause", "Overall average speed including a stationary pause", "hard"),
        ("electricity_cost", "Dollar cost from watts, minutes and cents/kWh", "hard"),
        ("dilution", "Concentration after adding water measured in millilitres", "hard"),
        ("staged_pump", "Remaining pumping time after changing flow and units", "hard"),
    ),
}


def f(value):
    """Parenthesize an exact numeric literal or rational arithmetic constant."""
    return f"({Fraction(value)})"


def choose_expr(n, k):
    if k == 0:
        return "1"
    return "(" + "*".join(f"({n}-{i})" for i in range(k)) + f"/{math.factorial(k)})"


def urn_case(index, rng):
    red, blue = rng.randint(3, 6), rng.randint(3, 6)
    green = rng.randint(2, 4) if index in (7, 9) else 0
    n = red + blue + green
    draws = 2 if index in (0, 1, 3, 4, 6) else 3
    p = {"red": red, "blue": blue, "green": green, "draws": draws}
    opening = f"An urn contains {red} red and {blue} blue balls"
    if green:
        opening += f" and {green} green balls"
    opening += f". Draw {draws} balls uniformly in order without replacement. "
    questions = (
        "What is the probability that both drawn balls are red?",
        "What is the probability that exactly one drawn ball is red?",
        "What is the probability that at least one drawn ball is red?",
        "What is the probability that the two drawn balls have the same color?",
        "What is the probability that the first ball is red and the second is blue?",
        "Given that at least one drawn ball is red, what is the probability that all three are red?",
        "Given that the second ball is red, what is the probability that the first ball is red?",
        "What is the probability that none of the three drawn balls is red?",
        "What is the probability that strictly more than half of the three drawn balls are red?",
        "What is the probability that the three drawn balls include exactly one ball of each color?",
        "Given that the first ball is red, what is the probability that exactly two of all three drawn balls are red?",
        "Given that all three drawn balls have the same color, what is the probability that they are all blue?",
        "Given that the second ball is blue, what is the probability that the first and third balls have the same color?",
    )
    cr, cb, cn = choose_expr(red, draws), choose_expr(blue, draws), choose_expr(n, draws)
    if index == 0:
        gold, expr = Fraction(math.comb(red, 2), math.comb(n, 2)), f"{cr}/{cn}"
    elif index == 1:
        gold, expr = Fraction(red * blue, math.comb(n, 2)), f"({red}*{blue})/{cn}"
    elif index == 2:
        gold, expr = 1 - Fraction(math.comb(blue, 3), math.comb(n, 3)), f"1-{cb}/{cn}"
    elif index == 3:
        gold = Fraction(math.comb(red, 2) + math.comb(blue, 2), math.comb(n, 2))
        expr = f"({cr}+{cb})/{cn}"
    elif index == 4:
        gold, expr = Fraction(red * blue, n * (n - 1)), f"({red}/{n})*({blue}/({n}-1))"
    elif index == 5:
        gold = Fraction(math.comb(red, 3), math.comb(n, 3) - math.comb(blue, 3))
        expr = f"{cr}/({cn}-{cb})"
    elif index == 6:
        gold, expr = Fraction(red - 1, n - 1), f"({red}-1)/({n}-1)"
    elif index == 7:
        gold = Fraction(math.comb(blue + green, 3), math.comb(n, 3))
        expr = f"{choose_expr(blue + green, 3)}/{cn}"
    elif index == 8:
        gold = Fraction(math.comb(red, 2) * blue + math.comb(red, 3), math.comb(n, 3))
        expr = f"({choose_expr(red, 2)}*{blue}+{cr})/{cn}"
    elif index == 9:
        gold, expr = Fraction(red * blue * green, math.comb(n, 3)), f"({red}*{blue}*{green})/{cn}"
    elif index == 10:
        gold = Fraction((red - 1) * blue, math.comb(n - 1, 2))
        expr = f"(({red}-1)*{blue})/{choose_expr(n - 1, 2)}"
    elif index == 11:
        gold, expr = Fraction(math.comb(blue, 3), math.comb(red, 3) + math.comb(blue, 3)), f"{cb}/({cr}+{cb})"
    else:
        gold = Fraction(red * (red - 1) + (blue - 1) * (blue - 2), (n - 1) * (n - 2))
        expr = f"({red}*({red}-1)+({blue}-1)*({blue}-2))/(({n}-1)*({n}-2))"
    return opening + questions[index], p, gold, expr


def sensor_case(index, rng):
    patterns = ((1,), (0,), (1, 1), (1, 0), (0, 0), (1, 0, 1), (0, 1, 0),
                (1, 0), (1, 0, 0, 1), (1, 1, 0, 1), (0, 0, 1, 0), (1, 0, 1, 0), (1, 1, 1))
    query = 0 if index in (4, 6, 9, 11, 12) else 1
    prior = rng.choice([Fraction(i, 10) for i in (2, 3, 4, 6, 7, 8)])
    observations = [{"source_id": f"S{i + 1}", "observation": bit,
                     "reliability": str(rng.choice([Fraction(3, 5), Fraction(7, 10), Fraction(3, 4), Fraction(4, 5), Fraction(9, 10)]))}
                    for i, bit in enumerate(patterns[index])]
    displayed = [dict(item) for item in observations]
    if index == 7:
        displayed.insert(1, dict(observations[0]))
    if index == 11:
        displayed += [dict(observations[1]), dict(observations[3])]
    p = {"prior_y1": str(prior), "query_state": query, "observations": displayed,
         "prior_representation": "odds" if index == 12 else "probability"}
    if index == 12:
        p["prior_odds_y1_to_y0"] = [prior.numerator, prior.denominator - prior.numerator]
        prior_text = f"Prior odds Y=1 to Y=0 are {prior.numerator}:{prior.denominator - prior.numerator}."
    else:
        prior_text = f"The prior probability P(Y=1) is {prior}; P(Y=0) is its complement."
    prompt = ("A hidden state Y is either 0 or 1. " + prior_text
              + " Distinct sensor source IDs are conditionally independent given Y. Reliability r means "
              "P(observation=Y | Y)=r for either state. A repeated source ID repeats the SAME observation "
              "and must be counted only once.\n")
    prompt += "\n".join(f"{o['source_id']}: observation={o['observation']}, reliability={o['reliability']}" for o in displayed)
    prompt += f"\nWhat is P(Y={query} | all the listed observations)?"
    terms, masses = {}, {}
    for state in (0, 1):
        mass = prior if state else 1 - prior
        factors = [f(prior) if state else f"(1-{f(prior)})"]
        for o in observations:
            r = Fraction(o["reliability"])
            mass *= r if o["observation"] == state else 1 - r
            factors.append(f(r) if o["observation"] == state else f"(1-{f(r)})")
        terms[state], masses[state] = "(" + "*".join(factors) + ")", mass
    return prompt, p, masses[query] / sum(masses.values()), f"{terms[query]}/({terms[0]}+{terms[1]})"


def algebra_case(index, rng):
    x = Fraction(rng.randint(-5, 18), rng.choice((1, 2, 3)))
    a, b = rng.randint(2, 7), rng.randint(1, 8)
    context = ""
    if index == 0:
        c = a * x + b
        lhs, rhs, expr = f"{a}*x+{b}", f(c), f"({f(c)}-{b})/{a}"
    elif index == 1:
        c = rng.randint(1, a - 1)
        d = (a - c) * x + b
        lhs, rhs, expr = f"{a}*x+{b}", f"{c}*x+{f(d)}", f"({f(d)}-{b})/({a}-{c})"
    elif index == 2:
        c = x / a + b
        lhs, rhs, expr = f"x/{a}+{b}", f(c), f"{a}*({f(c)}-{b})"
    elif index == 3:
        c = a * (x + b)
        lhs, rhs, expr = f"{a}*(x+{b})", f(c), f"{f(c)}/{a}-{b}"
    elif index == 4:
        c, d = rng.randint(1, 7), a * x / b + rng.randint(1, 7)
        d = a * x / b + c
        lhs, rhs, expr = f"{a}*x/{b}+{c}", f(d), f"({f(d)}-{c})*{b}/{a}"
    elif index == 5:
        x, k = Fraction(rng.randint(2, 9)), rng.randint(2, 7)
        perimeter = 4 * x + 2 * k
        context = f"A rectangle has width x metres and length x+{k} metres. Its perimeter is {perimeter} metres. "
        lhs, rhs, expr = f"2*(x+(x+{k}))", f(perimeter), f"({f(perimeter)}-2*{k})/4"
    elif index == 6:
        x = Fraction(rng.randint(-3, 15))
        total = 3 * x + 3
        context = f"Three consecutive integers are x, x+1 and x+2, with sum {total}. "
        lhs, rhs, expr = "x+(x+1)+(x+2)", f(total), f"({f(total)}-3)/3"
    elif index == 7:
        total_count, price_a, price_b = rng.randint(10, 25), rng.randint(5, 10), rng.randint(2, 4)
        x = Fraction(rng.randint(2, total_count - 2))
        receipts = price_a * x + price_b * (total_count - x)
        context = (f"A booth sells {total_count} tickets: x adult tickets at {price_a} dollars each and the rest "
                   f"child tickets at {price_b} dollars each. Total receipts are {receipts} dollars. ")
        lhs, rhs = f"{price_a}*x+{price_b}*({total_count}-x)", f(receipts)
        expr = f"({f(receipts)}-{price_b}*{total_count})/({price_a}-{price_b})"
    elif index == 8:
        c, d = rng.randint(1, 5), rng.randint(6, 9)
        e = (x - a) / b + (x + c) / d
        lhs, rhs = f"(x-{a})/{b}+(x+{c})/{d}", f(e)
        expr = f"({f(e)}*{b}*{d}+{a}*{d}-{c}*{b})/({b}+{d})"
    elif index == 9:
        c1, c2, v1 = rng.randint(2, 5), rng.randint(7, 10), rng.randint(2, 6)
        x = Fraction(rng.randint(2, 8))
        target = Fraction(c1 * v1 + c2 * x, v1 + x)
        context = (f"Mix {v1} litres of solution containing {c1} grams/litre with x litres containing "
                   f"{c2} grams/litre. Volumes add and the final concentration is {target} grams/litre. ")
        # Cross-multiply the physical balance to retain a linear verification equation.
        lhs, rhs = f"{c1}*{v1}+{c2}*x", f"{f(target)}*({v1}+x)"
        expr = f"{v1}*({f(target)}-{c1})/({c2}-{f(target)})"
    elif index == 10:
        r1, r2 = Fraction(rng.randint(1, 3), 10), Fraction(rng.randint(1, 4), 10)
        x = Fraction(rng.randint(50, 200))
        paid = x * (1 - r1) * (1 - r2)
        context = (f"An original price of x dollars receives a discount of {r1} of the current price, "
                   f"then a second discount of {r2} of the reduced price. The final price is {paid} dollars. ")
        lhs, rhs = f"x*(1-{f(r1)})*(1-{f(r2)})", f(paid)
        expr = f"{f(paid)}/((1-{f(r1)})*(1-{f(r2)}))"
    elif index == 11:
        c, d = rng.randint(2, 5), rng.randint(1, 6)
        e = (x / a + b) / c + d
        lhs, rhs = f"(x/{a}+{b})/{c}+{d}", f(e)
        expr = f"{a}*({c}*({f(e)}-{d})-{b})"
    else:
        a, b, c, d = rng.randint(2, 4), rng.randint(1, 3), rng.randint(3, 6), rng.randint(8, 12)
        x = Fraction(c * d - a * b, a + c)
        lhs, rhs = f"{a}*(x+{b})", f"{c}*({d}-x)"
        expr = f"({c}*{d}-{a}*{b})/({a}+{c})"
    visible_equation = not bool(context)
    p = {"equation_left": lhs, "equation_right": rhs, "equation_visible": visible_equation}
    instruction = (f"Solve {lhs} = {rhs} for x. " if visible_equation else "Find x. ")
    prompt = context + instruction + "Return an unevaluated arithmetic expression for x in expression."
    return prompt, p, x, expr


def units_case(index, rng):
    if index == 0:
        v, minutes = rng.randint(35, 105), rng.randint(7, 47)
        p = {"km_per_hour": v, "minutes": minutes}
        prompt = f"A cyclist maintains {v} kilometres/hour for {minutes} minutes. What distance in kilometres is covered?"
        expr, gold = f"{v}*{minutes}/60", Fraction(v * minutes, 60)
    elif index == 1:
        volume, rate = rng.randint(17, 83), rng.randint(3, 12)
        p = {"litres": volume, "litres_per_minute": rate}
        prompt = f"An empty tank needs {volume} litres. Water enters at {rate} litres/minute with no outflow. How many minutes are needed?"
        expr, gold = f"{volume}/{rate}", Fraction(volume, rate)
    elif index == 2:
        length, width = rng.randint(45, 180), rng.randint(25, 140)
        p = {"length_cm": length, "width_cm": width}
        prompt = f"A rectangular panel is {length} centimetres long and {width} centimetres wide. What is its area in square metres?"
        expr, gold = f"({length}/100)*({width}/100)", Fraction(length * width, 10000)
    elif index == 3:
        v1, t1, v2, t2 = rng.randint(25, 85), rng.randint(8, 31), rng.randint(4, 17), rng.randint(90, 300)
        p = {"first_km_per_hour": v1, "first_minutes": t1, "second_m_per_second": v2, "second_seconds": t2}
        prompt = (f"A vehicle travels at {v1} kilometres/hour for {t1} minutes, then at {v2} metres/second "
                  f"for {t2} seconds. What total distance in kilometres does it travel?")
        expr, gold = f"{v1}*{t1}/60+{v2}*{t2}/1000", Fraction(v1 * t1, 60) + Fraction(v2 * t2, 1000)
    elif index == 4:
        initial, efficiency, distance = rng.randint(25, 50), rng.randint(8, 16), rng.randint(40, 150)
        p = {"initial_litres": initial, "km_per_litre": efficiency, "distance_km": distance}
        prompt = (f"A car starts with {initial} litres of fuel and uses fuel at an efficiency of {efficiency} "
                  f"kilometres/litre. After a {distance}-kilometre trip, how many litres remain?")
        expr, gold = f"{initial}-{distance}/{efficiency}", initial - Fraction(distance, efficiency)
    elif index == 5:
        capacity, inflow1, inflow2, drain = rng.randint(100, 350), rng.randint(7, 14), rng.randint(5, 10), rng.randint(1, 4)
        p = {"capacity_litres": capacity, "inflow1_lpm": inflow1, "inflow2_lpm": inflow2, "drain_lpm": drain}
        prompt = (f"An empty {capacity}-litre tank has two constant inflows of {inflow1} and {inflow2} "
                  f"litres/minute and a simultaneous drain of {drain} litres/minute. How many minutes until full?")
        expr, gold = f"{capacity}/({inflow1}+{inflow2}-{drain})", Fraction(capacity, inflow1 + inflow2 - drain)
    elif index == 6:
        density, volume = Fraction(rng.randint(6, 27), 10), rng.randint(150, 850)
        p = {"grams_per_cm3": str(density), "volume_ml": volume}
        prompt = (f"A liquid has density {density} grams per cubic centimetre. A sample has volume {volume} "
                  "millilitres; one millilitre equals one cubic centimetre. What is the mass in kilograms?")
        expr, gold = f"{f(density)}*{volume}/1000", density * volume / 1000
    elif index == 7:
        workers, parts, minutes, hours = rng.randint(3, 8), rng.randint(5, 15), rng.choice((5, 10, 15, 30)), rng.randint(1, 4)
        p = {"workers": workers, "parts_per_batch": parts, "batch_minutes": minutes, "hours": hours}
        prompt = (f"Each of {workers} workers produces {parts} parts every {minutes} minutes at a constant "
                  f"rate. How many parts do they produce together in {hours} hours with no breaks?")
        expr, gold = f"{workers}*{parts}*({hours}*60)/{minutes}", Fraction(workers * parts * hours * 60, minutes)
    elif index == 8:
        d1, d2, v1, v2 = rng.randint(15, 45), rng.randint(46, 95), rng.randint(25, 45), rng.randint(50, 85)
        p = {"first_km": d1, "second_km": d2, "first_kmh": v1, "second_kmh": v2}
        prompt = (f"A trip covers {d1} kilometres at {v1} kilometres/hour, then {d2} kilometres at {v2} "
                  "kilometres/hour, with no stops. What is the average speed for the whole trip in kilometres/hour?")
        expr, gold = f"({d1}+{d2})/({d1}/{v1}+{d2}/{v2})", Fraction(d1 + d2, Fraction(d1, v1) + Fraction(d2, v2))
    elif index == 9:
        distance, speed, pause = rng.randint(30, 100), rng.randint(35, 85), rng.randint(7, 29)
        p = {"distance_km": distance, "moving_kmh": speed, "pause_minutes": pause}
        prompt = (f"A traveller covers {distance} kilometres while moving at {speed} kilometres/hour and "
                  f"also pauses for {pause} minutes. What is the average speed over the entire elapsed time, "
                  "including the pause, in kilometres/hour?")
        expr, gold = f"{distance}/({distance}/{speed}+{pause}/60)", Fraction(distance, Fraction(distance, speed) + Fraction(pause, 60))
    elif index == 10:
        watts, minutes, tariff = rng.randint(4, 17) * 100, rng.randint(18, 95), rng.randint(15, 42)
        p = {"watts": watts, "minutes": minutes, "cents_per_kwh": tariff}
        prompt = (f"An appliance draws {watts} watts continuously for {minutes} minutes. Electricity costs "
                  f"{tariff} cents per kilowatt-hour. What is the electricity cost in dollars? Ignore fees.")
        expr, gold = f"({watts}/1000)*({minutes}/60)*({tariff}/100)", Fraction(watts * minutes * tariff, 1000 * 60 * 100)
    elif index == 11:
        mass, volume, water = rng.randint(12, 48), rng.randint(2, 7), rng.randint(2, 9) * 100
        p = {"solute_grams": mass, "initial_litres": volume, "water_ml": water}
        prompt = (f"A solution contains {mass} grams of solute in {volume} litres. Add {water} millilitres "
                  "of pure water, with volumes adding and no solute lost. What is the final concentration in grams/litre?")
        expr, gold = f"{mass}/({volume}+{water}/1000)", Fraction(mass, volume + Fraction(water, 1000))
    else:
        rate1, minutes, rate2 = rng.randint(3, 8), rng.randint(2, 6), rng.randint(25, 95)
        target = rate1 * minutes + rng.randint(8, 30)
        p = {"first_lpm": rate1, "first_minutes": minutes, "second_ml_per_second": rate2, "target_litres": target}
        prompt = (f"Fill an empty tank to {target} litres. First pump at {rate1} litres/minute for {minutes} "
                  f"minutes, then switch to {rate2} millilitres/second. How many seconds of second-stage pumping "
                  "are needed to reach the target? There is no outflow.")
        expr, gold = f"({target}-{rate1}*{minutes})*1000/{rate2}", Fraction((target - rate1 * minutes) * 1000, rate2)
    return prompt, p, gold, expr


BUILDERS = {"reasoning": urn_case, "evidence": sensor_case, "algebra": algebra_case, "units": units_case}
METHODS = {
    "reasoning": "Combinatorial/conditional formula, audited by exhaustive ordered draws of individually labeled balls.",
    "evidence": "Exact likelihood normalization over unique sources, audited by exhaustive joint state/observation enumeration.",
    "algebra": "Exact construction/closed-form inverse, audited by independent affine AST reduction and substitution.",
    "units": "Exact dimensional conversion, audited by conservation equations in consistent base units.",
}


def enumerate_urn(task):
    p, index = task["parameters"], task["template_index"]
    colors = "R" * p["red"] + "B" * p["blue"] + "G" * p["green"]
    denominator = numerator = 0
    for indices in itertools.permutations(range(len(colors)), p["draws"]):
        seq = [colors[i] for i in indices]
        red = seq.count("R")
        condition = True
        if index == 0:
            event = red == 2
        elif index == 1:
            event = red == 1
        elif index == 2:
            event = red >= 1
        elif index == 3:
            event = seq[0] == seq[1]
        elif index == 4:
            event = seq == ["R", "B"]
        elif index == 5:
            condition, event = red >= 1, red == 3
        elif index == 6:
            condition, event = seq[1] == "R", seq[0] == "R"
        elif index == 7:
            event = red == 0
        elif index == 8:
            event = red >= 2
        elif index == 9:
            event = set(seq) == {"R", "B", "G"}
        elif index == 10:
            condition, event = seq[0] == "R", red == 2
        elif index == 11:
            condition, event = len(set(seq)) == 1, seq == ["B", "B", "B"]
        else:
            condition, event = seq[1] == "B", seq[0] == seq[2]
        denominator += condition
        numerator += condition and event
    return Fraction(numerator, denominator)


def enumerate_sensor(task):
    p = task["parameters"]
    unique = {}
    for o in p["observations"]:
        value = (o["observation"], Fraction(o["reliability"]))
        if o["source_id"] in unique and unique[o["source_id"]] != value:
            raise ValueError("Contradictory observations for the same sensor ID")
        unique[o["source_id"]] = value
    prior = Fraction(p["prior_y1"])
    if p["prior_representation"] == "odds":
        one, zero = p["prior_odds_y1_to_y0"]
        if prior != Fraction(one, one + zero):
            raise ValueError("Prior probability and odds disagree")
    joint_evidence = query_evidence = Fraction(0)
    for state in (0, 1):
        for readings in itertools.product((0, 1), repeat=len(unique)):
            mass = prior if state else 1 - prior
            for reading, (_, reliability) in zip(readings, unique.values()):
                mass *= reliability if reading == state else 1 - reliability
            if readings == tuple(value for value, _ in unique.values()):
                joint_evidence += mass
                if state == p["query_state"]:
                    query_evidence += mass
    return query_evidence / joint_evidence


def affine(text):
    """Independently reduce a linear expression to coefficient*x + constant."""
    def visit(node):
        if isinstance(node, ast.Constant) and type(node.value) is int:
            return Fraction(0), Fraction(node.value)
        if isinstance(node, ast.Name) and node.id == "x":
            return Fraction(1), Fraction(0)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            a, b = visit(node.operand)
            return (-a, -b) if isinstance(node.op, ast.USub) else (a, b)
        if not isinstance(node, ast.BinOp):
            raise ValueError("Unsupported reference equation syntax")
        a, b = visit(node.left)
        c, d = visit(node.right)
        if isinstance(node.op, ast.Add):
            return a + c, b + d
        if isinstance(node.op, ast.Sub):
            return a - c, b - d
        if isinstance(node.op, ast.Mult):
            if a and c:
                raise ValueError("Nonlinear equation")
            return a * d + b * c, b * d
        if isinstance(node.op, ast.Div) and not c and d:
            return a / d, b / d
        raise ValueError("Unsupported nonlinear or undefined equation")
    return visit(ast.parse(text, mode="eval").body)


def verify_units(task, value):
    """Verify a proposed answer against an independent physical balance."""
    p, i = task["parameters"], task["template_index"]
    if i == 0:
        left, right = value * 1000, Fraction(p["km_per_hour"] * 1000, 3600) * p["minutes"] * 60
    elif i == 1:
        left, right = value * 60 * Fraction(p["litres_per_minute"], 60), p["litres"]
    elif i == 2:
        left, right = value, Fraction(p["length_cm"], 100) * Fraction(p["width_cm"], 100)
    elif i == 3:
        left = value * 1000
        right = Fraction(p["first_km_per_hour"] * 1000, 3600) * p["first_minutes"] * 60 + p["second_m_per_second"] * p["second_seconds"]
    elif i == 4:
        left, right = (p["initial_litres"] - value) * p["km_per_litre"], p["distance_km"]
    elif i == 5:
        left, right = value * (p["inflow1_lpm"] + p["inflow2_lpm"] - p["drain_lpm"]), p["capacity_litres"]
    elif i == 6:
        left, right = value * 1000, Fraction(p["grams_per_cm3"]) * p["volume_ml"]
    elif i == 7:
        left = value / (p["workers"] * p["hours"] * 3600)
        right = Fraction(p["parts_per_batch"], p["batch_minutes"] * 60)
    elif i == 8:
        left = value * (Fraction(p["first_km"], p["first_kmh"]) + Fraction(p["second_km"], p["second_kmh"]))
        right = p["first_km"] + p["second_km"]
    elif i == 9:
        left = value * (Fraction(p["distance_km"], p["moving_kmh"]) * 3600 + p["pause_minutes"] * 60)
        right = p["distance_km"] * 3600
    elif i == 10:
        joules = p["watts"] * p["minutes"] * 60
        left, right = value * 100, Fraction(joules, 3600000) * p["cents_per_kwh"]
    elif i == 11:
        left, right = value * (p["initial_litres"] * 1000 + p["water_ml"]), p["solute_grams"] * 1000
    else:
        left = p["first_lpm"] * p["first_minutes"] * 1000 + value * p["second_ml_per_second"]
        right = p["target_litres"] * 1000
    if left != right:
        raise ValueError(f"Dimensional/conservation reference mismatch for {task['id']}")


def verify_reference(task):
    gold = Fraction(task["gold_fraction"])
    family, p = task["family"], task["parameters"]
    if family == "reasoning" and enumerate_urn(task) != gold:
        raise ValueError("Urn enumeration disagrees with the reference")
    if family == "evidence" and enumerate_sensor(task) != gold:
        raise ValueError("Exhaustive joint sensor model disagrees with the reference")
    if family == "algebra":
        a, b = affine(p["equation_left"])
        c, d = affine(p["equation_right"])
        if a == c or gold != (d - b) / (a - c) or a * gold + b != c * gold + d:
            raise ValueError("Algebra reference fails independent solve/substitution")
        if p["equation_visible"] and f"Solve {p['equation_left']} = {p['equation_right']} for x." not in task["prompt"]:
            raise ValueError("Prompt and independently checked equation disagree")
    if family == "units":
        verify_units(task, gold)
    if evaluate_expression(p["reference_expression"]) != gold:
        raise ValueError("Reference cannot be realized by the declared calculator grammar")
    return gold


def generate_manifest():
    rng = random.Random(SEED)
    tasks, inventory, prompts = [], [], set()
    for family in FAMILIES:
        for split, indices in PARTITIONS.items():
            split_index = 0
            for position, index in enumerate(indices):
                slug, description, difficulty = TEMPLATES[family][index]
                group = f"full-v1-{family}-{slug}"
                count = 1 if split == "development" and position == 0 else 2
                inventory.append({"group_id": group, "family": family, "split": split,
                                  "template_index": index, "description": description,
                                  "planned_difficulty": difficulty, "variants": count})
                for variant in range(count):
                    for _ in range(100):
                        prompt, parameters, gold, expression = BUILDERS[family](index, rng)
                        if prompt not in prompts:
                            break
                    else:
                        raise ValueError("Could not construct unique deterministic question")
                    prompts.add(prompt)
                    split_index += 1
                    parameters["reference_expression"] = expression
                    tasks.append({"id": f"full-v1-{family}-{split}-{split_index:02d}",
                                  "group_id": group, "template_id": slug, "template_index": index,
                                  "split": split, "family": family, "prompt": prompt,
                                  "probability": family in ("reasoning", "evidence"),
                                  "gold_fraction": str(gold), "parameters": parameters,
                                  "difficulty": difficulty, "reference_method": METHODS[family]})
    manifest = {
        "schema_version": 1,
        "manifest_id": "full-benchmark-v1",
        "source": {
            "generator": "build_full_benchmark.py", "generator_version": GENERATOR_VERSION,
            "seed": SEED, "kind": "new synthetic questions; no model feedback or external dataset",
            "split_policy": "Semantic structures are assigned to one partition before numeric sampling; all variants retain the same group_id.",
            "difficulty_policy": "Planned from operation/conditioning structure, never model outcomes; difficulty is descriptive, not a measured label.",
            "reference_policy": "Exact rational answers with independent enumerative, symbolic, or dimensional checks; reference expressions and parameters stay private.",
            "inference_policy": "No inference has been performed by this generator. The 100 tasks comprise 20 development, 40 validation, and 40 test questions.",
            "uncertainty_unit": "group_id semantic template: 12 development, 20 validation and 20 test clusters; paired numeric variants are not independent questions.",
            "template_inventory": inventory,
        },
        "tasks": tasks,
    }
    validate_manifest(manifest)
    return manifest


def validate_manifest(manifest):
    tasks = manifest["tasks"]
    validate_tasks(tasks)
    if len(tasks) != 100 or len({t["prompt"] for t in tasks}) != 100:
        raise ValueError("The full bank needs exactly 100 unique questions")
    expected = Counter({(family, split): (5 if split == "development" else 10)
                        for family in FAMILIES for split in PARTITIONS})
    if Counter((t["family"], t["split"]) for t in tasks) != expected:
        raise ValueError("Unexpected full-bank family/split allocation")
    groups = defaultdict(list)
    for task in tasks:
        groups[task["group_id"]].append(task)
        verify_reference(task)
    if len(groups) != 52:
        raise ValueError("The full bank needs 52 structural template groups")
    for family in FAMILIES:
        seen = {}
        for split, indices in PARTITIONS.items():
            actual = {t["template_index"] for t in tasks if t["family"] == family and t["split"] == split}
            if actual != set(indices):
                raise ValueError("A structural template crossed its declared split")
            for index in actual:
                if index in seen:
                    raise ValueError("Semantic template leakage between partitions")
                seen[index] = split
        if set(seen) != set(range(13)):
            raise ValueError("Each family needs thirteen distinct structural templates")
    return manifest


def manifest_bytes(manifest):
    return (json.dumps(manifest, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="Audit references and compare committed manifest bytes without writes")
    mode.add_argument("--output", type=Path, help="Write a newly generated manifest to a new file, exclusively")
    args = parser.parse_args(argv)
    try:
        data = manifest_bytes(generate_manifest())
        if args.check:
            if DEFAULT_PATH.read_bytes() != data:
                raise ValueError("Committed full benchmark differs from deterministic generation")
            print("Full benchmark verified: 100 questions, 52 groups, 20/40/40 development/validation/test; exact references audited.")
        else:
            with args.output.open("xb") as output:
                output.write(data)
            print(f"Wrote {args.output}: 100 questions; existing files are never overwritten.")
        return 0
    except (OSError, ValueError, KeyError, TypeError, ZeroDivisionError) as exc:
        print(f"Benchmark generation/check failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
