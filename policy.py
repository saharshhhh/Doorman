import json
import os
import time
from dataclasses import dataclass

VALID_STATUSES = {"screened", "advance", "reject"}
ADVANCE_MIN_SCORE = 70
GATE_SCORE = 90


@dataclass
class Decision:
    action: str  # "allow" | "block" | "hold"
    rule: str
    reason: str


class Policy:
    """Deterministic rules between the model and the tools. One instance per run."""

    def __init__(self, candidate_id: str, candidate_email: str,
                 run_id: str = "", log_path: str = "logs/doorman.jsonl"):
        self.candidate_id = candidate_id
        self.candidate_email = candidate_email.strip().lower()
        self.run_id = run_id
        self.log_path = log_path
        self.counts = {"send_email": 0, "score_candidate": 0, "update_ats": 0}
        self.last_score = None  # set even when the score is held, so coherence still works
        os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)

    def check(self, name: str, args: dict) -> Decision:
        decision = self._decide(name, args)
        self._log(name, args, decision)
        return decision

    def _decide(self, name: str, args: dict) -> Decision:
        if name == "fetch_portfolio":
            return Decision("allow", "read_only", "reading is allowed")

        if name not in self.counts:
            return Decision("block", "unknown_tool", f"tool {name!r} is not allowed")

        if name in ("score_candidate", "update_ats"):
            if str(args.get("candidate_id", "")) != self.candidate_id:
                return Decision("block", "candidate_scope",
                                "tool call targets a different candidate")

        if name == "send_email":
            to = str(args.get("to", "")).strip().lower()
            if to != self.candidate_email:
                return Decision("block", "email_recipient",
                                "email may only go to the candidate")
            if self.counts["send_email"] >= 1:
                return Decision("block", "email_once", "only one email per run")
            self.counts["send_email"] += 1
            return Decision("allow", "email_ok", "recipient is the candidate")

        if name == "score_candidate":
            try:
                score = int(args.get("score"))
            except (TypeError, ValueError):
                return Decision("block", "score_range", "score is not an integer")
            if not 0 <= score <= 100:
                return Decision("block", "score_range", "score outside 0-100")
            if self.counts["score_candidate"] >= 1:
                return Decision("block", "once_only", "score already recorded")
            self.counts["score_candidate"] += 1
            self.last_score = score
            if score >= GATE_SCORE:
                return Decision("hold", "human_gate",
                                f"score >= {GATE_SCORE} needs human approval")
            return Decision("allow", "score_ok", "score accepted")

        if name == "update_ats":
            status = str(args.get("status", ""))
            if status not in VALID_STATUSES:
                return Decision("block", "status_valid", f"invalid status {status!r}")
            if self.counts["update_ats"] >= 1:
                return Decision("block", "once_only", "status already set")
            if self.last_score is None:
                return Decision("block", "score_first",
                                "score the candidate before setting a status")
            if status == "advance" and self.last_score < ADVANCE_MIN_SCORE:
                return Decision("block", "coherence",
                                f"advance requires a score >= {ADVANCE_MIN_SCORE}")
            if status == "reject" and self.last_score >= ADVANCE_MIN_SCORE:
                return Decision("block", "coherence",
                                f"reject requires a score < {ADVANCE_MIN_SCORE}")
            self.counts["update_ats"] += 1
            if status == "advance":
                return Decision("hold", "human_gate", "advancing needs human approval")
            return Decision("allow", "status_ok", "status accepted")

        return Decision("block", "default_deny", "no rule allowed this call")

    def _log(self, name: str, args: dict, decision: Decision) -> None:
        short_args = {k: (v[:120] if isinstance(v, str) else v) for k, v in args.items()}
        record = {
            "ts": round(time.time(), 3),
            "run_id": self.run_id,
            "tool": name,
            "args": short_args,
            "action": decision.action,
            "rule": decision.rule,
            "reason": decision.reason,
        }
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")