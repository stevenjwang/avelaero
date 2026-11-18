import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


class ToolTimeout(Exception):
    pass


DEFAULT_STATE_PATH = Path(__file__).resolve().with_name("workflow-state.json")
WORKFLOW_STATUSES = {
    "NOT_STARTED",
    "START",
    "RUNNING",
    "FAILED",
    "RETRY",
    "SUCCESS",
    "PAUSED",
    "APPROVED",
    "COMPLETE",
}


class WorkflowEngine:
    def __init__(
        self,
        workflow_id="REQ-1042",
        simulate_failure=True,
        inquiry=None,
    ):
        self.workflow_id = workflow_id
        self.simulate_failure = simulate_failure
        self.inquiry = inquiry or {
            "passengers": 6,
            "route": "SFO to Teterboro",
            "date": "2026-12-05",
        }
        self.status = "NOT_STARTED"
        self.current_step = None
        self.context = {}
        self.approved = False
        self.history = []

    def record(self, status, message):
        entry = {
            "status": status,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        self.history.append(entry)
        self.status = status
        print(f"[{status}] {message}")

    def run(self):
        if self.status in ("COMPLETE", "FAILED"):
            return

        if self.status == "NOT_STARTED":
            self.record("START", f"Workflow {self.workflow_id}")

        if not self.context.get("availability_checked"):
            if not self.check_availability():
                return

        if not self.context.get("quote_prepared"):
            self.prepare_quote()

        if not self.approved:
            self.current_step = "Send approved quote"
            self.record("PAUSED", "Waiting for human approval")
            return

        self.send_quote()

    def check_availability(self):
        self.current_step = "Check aircraft availability"
        self.record("RUNNING", self.current_step)

        for attempt in (1, 2):
            try:
                if attempt == 1 and self.simulate_failure:
                    raise ToolTimeout("Temporary API timeout")

                aircraft = "Citation Latitude"
                self.context["availability_checked"] = True
                self.context["aircraft"] = aircraft
                self.record("SUCCESS", "Aircraft availability received")
                return True
            except ToolTimeout as error:
                self.record("FAILED", str(error))
                if attempt < 2:
                    self.record("RETRY", f"Attempt {attempt + 1}")

        self.record("FAILED", "Availability check exhausted retries")
        return False

    def prepare_quote(self):
        self.current_step = "Prepare quote"
        self.record("RUNNING", self.current_step)
        availability = self.context["aircraft"]
        quote = {
            "aircraft": availability,
            "route": self.inquiry["route"],
            "passengers": self.inquiry["passengers"],
            "date": self.inquiry["date"],
            "amount": "$18,500",
        }
        self.context["quote"] = quote
        self.context["quote_prepared"] = True
        self.record("SUCCESS", "Draft prepared")

    def approve(self, approver="human"):
        if self.status != "PAUSED" or not self.context.get("quote_prepared"):
            raise RuntimeError("Only a paused workflow with a prepared quote may be approved")
        self.approved = True
        self.context["approved_by"] = approver
        self.record("APPROVED", f"Human approves draft ({approver})")

    def send_quote(self):
        if not self.approved or not self.context.get("quote_prepared"):
            raise RuntimeError("Send blocked: a prepared quote and explicit approval are required")

        self.current_step = "Send approved quote"
        self.record("RUNNING", "Send quote (mock)")
        self.context["send"] = {
            "mock": True,
            "recipient": "fictional@example.com",
            "quote": self.context["quote"],
        }
        self.record("SUCCESS", "Mock send completed")
        self.record("COMPLETE", "Workflow finished")

    def to_dict(self):
        return {
            "workflow_id": self.workflow_id,
            "simulate_failure": self.simulate_failure,
            "inquiry": self.inquiry,
            "status": self.status,
            "current_step": self.current_step,
            "context": self.context,
            "approved": self.approved,
            "history": self.history,
        }

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise ValueError("Workflow state must be a JSON object")

        required_fields = {
            "workflow_id",
            "simulate_failure",
            "inquiry",
            "status",
            "current_step",
            "context",
            "approved",
            "history",
        }
        missing_fields = required_fields - data.keys()
        if missing_fields:
            raise ValueError(f"Workflow state is missing fields: {', '.join(sorted(missing_fields))}")
        if not isinstance(data["workflow_id"], str) or not data["workflow_id"]:
            raise ValueError("Workflow state workflow_id must be a non-empty string")
        if not isinstance(data["simulate_failure"], bool):
            raise ValueError("Workflow state simulate_failure must be a boolean")
        if not isinstance(data["inquiry"], dict):
            raise ValueError("Workflow state inquiry must be an object")
        if not isinstance(data["status"], str) or data["status"] not in WORKFLOW_STATUSES:
            raise ValueError(f"Workflow state has an invalid status: {data['status']!r}")
        if data["current_step"] is not None and not isinstance(data["current_step"], str):
            raise ValueError("Workflow state current_step must be a string or null")
        if not isinstance(data["context"], dict):
            raise ValueError("Workflow state context must be an object")
        if not isinstance(data["approved"], bool):
            raise ValueError("Workflow state approved must be a boolean")
        if not isinstance(data["history"], list):
            raise ValueError("Workflow state history must be an array")
        for entry in data["history"]:
            if (
                not isinstance(entry, dict)
                or not isinstance(entry.get("status"), str)
                or not isinstance(entry.get("message"), str)
                or not isinstance(entry.get("timestamp"), str)
            ):
                raise ValueError("Each workflow history entry must have string status, message, and timestamp fields")

        engine = cls(
            workflow_id=data["workflow_id"],
            simulate_failure=data["simulate_failure"],
            inquiry=data["inquiry"],
        )
        engine.status = data["status"]
        engine.current_step = data["current_step"]
        engine.context = data["context"]
        engine.approved = data["approved"]
        engine.history = data["history"]
        return engine


def load_state(path):
    if not path.exists():
        raise FileNotFoundError(f"Workflow state not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid workflow state JSON in {path}: {error.msg}") from error
    return WorkflowEngine.from_dict(data)


def save_state(path, engine):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(engine.to_dict(), indent=2), encoding="utf-8")


def build_parser():
    parser = argparse.ArgumentParser(description="Avel charter inquiry execution engine")
    parser.add_argument("--state", default=DEFAULT_STATE_PATH, type=Path)
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Start the workflow and stop at human approval")
    run.add_argument("--state", default=argparse.SUPPRESS, type=Path)
    run.add_argument(
        "--restart",
        action="store_true",
        help="Replace an existing workflow state file and start a new workflow",
    )
    run.add_argument("--no-failure", action="store_true", help="Skip the simulated availability timeout")
    run.add_argument("--approve", action="store_true", help="Approve immediately after the pause")

    approve = sub.add_parser("approve", help="Approve a paused workflow and send it")
    approve.add_argument("--state", default=argparse.SUPPRESS, type=Path)

    status = sub.add_parser("status", help="Show workflow status and history")
    status.add_argument("--state", default=argparse.SUPPRESS, type=Path)
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "run":
        if args.state.exists() and not args.restart:
            parser.error(
                f"Workflow state already exists: {args.state}. "
                "Use --restart to replace it or choose another --state path."
            )

        engine = WorkflowEngine(simulate_failure=not args.no_failure)
        engine.run()
        save_state(args.state, engine)
        if args.approve and engine.status == "PAUSED":
            engine.approve("CLI --approve")
            engine.run()
            save_state(args.state, engine)
        return 1 if engine.status == "FAILED" else 0

    if args.command == "approve":
        engine = load_state(args.state)
        engine.approve("human")
        engine.run()
        save_state(args.state, engine)
        return 0

    engine = load_state(args.state)
    print(f"Workflow: {engine.workflow_id}")
    print(f"Status: {engine.status}")
    print("History:")
    for entry in engine.history:
        print(f"[{entry['status']}] {entry['message']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())