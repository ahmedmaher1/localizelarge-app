"""Measure a fuzzy lookup in a large translation memory.

    python tools/bench_tm.py            100,000 units
    python tools/bench_tm.py 20000      another size

Builds a throwaway database of made-up English→French units in a temporary folder,
then times `search_fuzzy_matches` for a set of queries that each have a near match in
the memory. Prints the median and the slowest lookup, and how many queries found their
near match. The figures for the release are recorded in docs/PERFORMANCE.md.
"""
import os
import random
import statistics
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SUBJECTS = ["The operator", "The administrator", "Every user", "The technician", "A supervisor",
            "The customer", "The system", "The device", "This module", "The controller",
            "The service engineer", "Your manager", "The application", "The installer"]
VERBS = ["must check", "should replace", "can configure", "has to restart", "will update",
         "may remove", "needs to clean", "must not open", "should inspect", "can export",
         "has to calibrate", "will reset", "must confirm", "should record"]
OBJECTS = ["the main valve", "the power supply", "the user profile", "the safety cover",
           "the network settings", "the oil filter", "the backup file", "the pressure sensor",
           "the access rights", "the control panel", "the cooling unit", "the licence key",
           "the report template", "the conveyor belt", "the emergency switch", "the log files"]
TIMES = ["before each shift", "after the update", "once a week", "every 500 hours",
         "when the light is red", "during maintenance", "at the end of the day",
         "if the alarm sounds", "before starting the engine", "after every delivery",
         "within 24 hours", "as soon as possible", "in the first month", "on request"]
EXTRAS = ["Follow the instructions in the manual.", "Wear protective gloves.",
          "Record the result in the logbook.", "Contact support if the problem remains.",
          "Do not use force.", "Keep the area clean.", "Use only approved parts.",
          "Wait until the indicator turns green.", "Check the serial number first.", ""]


def sentence(rng):
    text = f"{rng.choice(SUBJECTS)} {rng.choice(VERBS)} {rng.choice(OBJECTS)} {rng.choice(TIMES)}."
    extra = rng.choice(EXTRAS)
    if extra:
        text += " " + extra
    if rng.random() < 0.3:
        text += f" See section {rng.randint(1, 400)}.{rng.randint(1, 9)}."
    return text


def main():
    size = int(sys.argv[1]) if len(sys.argv) > 1 else 100_000
    rng = random.Random(1)
    from modules.database_manager import DatabaseManager

    folder = tempfile.mkdtemp(prefix="ll-bench-")
    db = DatabaseManager(os.path.join(folder, "bench.db"))
    db.connect()

    db.cursor.execute(
        "INSERT INTO translation_memories (name, source_lang, target_lang, tm_id, read_only) "
        "VALUES ('Benchmark', 'en', 'fr', 'bench', 0)")
    db.connection.commit()

    seen = set()
    entries = []
    while len(entries) < size:
        source = sentence(rng) + f" Item {len(entries)}." if rng.random() < 0.5 else sentence(rng)
        if source in seen:
            source += f" Ref {len(entries)}."
        seen.add(source)
        entries.append((source, "FR: " + source))
    started = time.perf_counter()
    for i in range(0, size, 5000):
        db.add_translation_units_batch(entries[i:i + 5000], "en", "fr", "bench")
    print(f"built {size:,} units in {time.perf_counter() - started:.1f} s")

    # Queries: a unit of the memory with one word changed.
    queries = []
    for source, _ in rng.sample(entries, 50):
        words = source.split()
        words[2] = "certainly" if words[2] != "certainly" else "surely"
        queries.append((" ".join(words), source))

    if os.environ.get("BENCH_PROFILE"):
        import cProfile
        import pstats
        profiler = cProfile.Profile()
        profiler.enable()
        for query, _ in queries[:10]:
            db.search_fuzzy_matches(query, ["bench"], threshold=0.75, max_results=5,
                                    source_lang="en", target_lang="fr")
        profiler.disable()
        pstats.Stats(profiler).sort_stats("cumulative").print_stats(14)

    timings, found = [], 0
    for query, original in queries:
        started = time.perf_counter()
        matches = db.search_fuzzy_matches(query, ["bench"], threshold=0.75, max_results=5,
                                          source_lang="en", target_lang="fr")
        timings.append((time.perf_counter() - started) * 1000)
        if any(m["source_text"] == original for m in matches):
            found += 1
    timings.sort()
    print(f"lookups: {len(timings)}  median {statistics.median(timings):.0f} ms  "
          f"slowest {timings[-1]:.0f} ms  near match found {found}/{len(queries)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
