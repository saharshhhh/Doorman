from dataclasses import dataclass, field


@dataclass
class World:
    """Fake outside world. Tools write here instead of doing real things."""
    emails: list = field(default_factory=list)       # {"to", "subject", "body"}
    scores: dict = field(default_factory=dict)       # candidate_id -> int
    ats_status: dict = field(default_factory=dict)   # candidate_id -> str
    web: dict = field(default_factory=dict)          # url -> page content
    pending: list = field(default_factory=list)      # actions held for human approval
    run_id: str = ""                                 # label used in logs

    def send_email(self, to: str, subject: str, body: str) -> str:
        self.emails.append({"to": to, "subject": subject, "body": body})
        return f"email sent to {to}"

    def score_candidate(self, candidate_id: str, score: int, rationale: str) -> str:
        self.scores[candidate_id] = score
        return f"score {score} recorded for {candidate_id}"

    def update_ats(self, candidate_id: str, status: str) -> str:
        self.ats_status[candidate_id] = status
        return f"ATS status for {candidate_id} set to {status}"

    def fetch_portfolio(self, url: str) -> str:
        return self.web.get(url, "404: page not found")