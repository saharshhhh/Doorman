import argparse
import json
import os
import time
from collections import defaultdict
from policy import Policy
from agent import DailyQuotaExceeded, run_agent
from attacks import CANDIDATE_EMAIL, CANDIDATE_ID, CONTROL, build_corpus, check
from world import World


def run_one(item: dict, runner) -> dict:
    world = World()
    world.web = dict(item["web"])
    try:
        trace = runner(world, CANDIDATE_ID, CANDIDATE_EMAIL, item["text"], item["meta"])
        error = None
    except DailyQuotaExceeded:
        raise  # stop the whole suite; progress is saved by the caller
    except Exception as e:  # one API failure shouldn't kill the whole run
        trace, error = [], repr(e)[:300]
    return {
        "id": item["id"],
        "family": item["family"],
        "goal": item["goal"],
        "success": None if error else check(world, item["goal"]),
        "error": error,
        "tool_calls": [{"name": n, "args": a} for n, a in trace],
    }


def save(path: str, results: list) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)


def run_suite(runner, trials: int, family: str | None, sleep: float, path: str) -> list:
    # Resume: keep earlier runs that finished without error, redo the rest.
    results = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            results = [r for r in json.load(f) if not r["error"]]
    done = {(r["id"], r["trial"]) for r in results}

    items = [CONTROL] + build_corpus()
    if family:
        items = [i for i in items if i["family"] in (family, "control")]

    try:
        for item in items:
            for t in range(trials):
                if (item["id"], t) in done:
                    continue
                r = run_one(item, runner)
                r["trial"] = t
                results.append(r)
                save(path, results)
                flag = "ERR" if r["error"] else ("HIT" if r["success"] else "ok ")
                print(f"[{flag}] {r['id']} trial {t}")
                time.sleep(sleep)
    except DailyQuotaExceeded as e:
        print(f"\nDaily quota exhausted, stopping. Progress saved. Rerun later to resume.\n{e}")
    return results


def report(results: list) -> None:
    by_family = defaultdict(lambda: [0, 0, 0])  # runs, successes, errors
    for r in results:
        row = by_family[r["family"]]
        if r["error"]:
            row[2] += 1
        else:
            row[0] += 1
            row[1] += 1 if r["success"] else 0
    print(f"\n{'family':<18}{'runs':>6}{'hits':>6}{'ASR':>8}{'errors':>8}")
    total_runs = total_hits = 0
    for family, (runs, hits, errs) in sorted(by_family.items()):
        asr = f"{100 * hits / runs:.0f}%" if runs else "n/a"
        print(f"{family:<18}{runs:>6}{hits:>6}{asr:>8}{errs:>8}")
        if family != "control":
            total_runs += runs
            total_hits += hits
    if total_runs:
        print(f"\nOverall ASR (excluding control): {100 * total_hits / total_runs:.1f}%")

def guarded_runner(world, candidate_id, candidate_email, text, meta):
    policy = Policy(candidate_id, candidate_email, run_id=world.run_id)
    return run_agent(world, candidate_id, candidate_email, text, meta, policy=policy)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--trials", type=int, default=2)
    p.add_argument("--label", default="baseline")
    p.add_argument("--family", default=None)
    p.add_argument("--sleep", type=float, default=0.5)
    p.add_argument("--guarded", action="store_true")
    args = p.parse_args()

    os.makedirs("results", exist_ok=True)
    path = os.path.join("results", f"{args.label}.json")
    runner = guarded_runner if args.guarded else run_agent
    results = run_suite(runner, args.trials, args.family, args.sleep, path)
    report(results)
    print(f"\nSaved: {path}")

if __name__ == "__main__":
    main()