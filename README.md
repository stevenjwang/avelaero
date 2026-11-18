# Avel Charter Workflow Engine

A small Python CLI that executes the fictional charter inquiry workflow from the Avel technical assessment.

## Run

From the project directory:

```powershell
python "Avel Technical Assessment.py" run --restart --approve
python "Avel Technical Assessment.py" status
```

To run it from another directory, use the full path to `Avel Technical Assessment.py`. By default, `workflow-state.json` is stored beside the script, regardless of the current directory. Use the same `--state PATH` with each command to choose a different location; `--state` is accepted before or after the subcommand. Starting a new workflow refuses to replace an existing state file; pass `--restart` to replace it explicitly.

For a custom state file in PowerShell, save the path once and reuse it:

```powershell
$state = ".\approval-demo.json"
python "Avel Technical Assessment.py" --state $state run --restart
python "Avel Technical Assessment.py" --state $state approve
```

To demonstrate a persistent human-approval pause:

```powershell
python "Avel Technical Assessment.py" run --restart
python "Avel Technical Assessment.py" status
python "Avel Technical Assessment.py" approve
```

The first availability attempt times out by default, then the engine retries once. Use `--no-failure` to skip the simulated timeout:

```powershell
python "Avel Technical Assessment.py" run --no-failure --restart
```

Run the test suite from the project directory:

```powershell
python -m unittest -v test_avel_engine.py
```

## Architecture

`WorkflowEngine` is an explicit state machine with four ordered phases: availability, quote preparation, approval, and mock send. State is passed through a shared context dictionary, and every status transition is appended to a timestamped history. The CLI persists the engine state as JSON so approval can happen in a separate command. Saved state is checked when loaded, and malformed or incomplete state is rejected with an error.

## Key decision

Approval is accepted only while the workflow is paused with a prepared quote, and sending checks both that the quote is prepared and that approval was explicit. This prevents the send step from running merely because it is next in the workflow.

## Limitation

The implementation stores state in a local JSON file and uses hardcoded mock services.
"# avelaero" 
