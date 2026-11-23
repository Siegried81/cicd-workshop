# CI/CD for Data & AI Engineers: Hands-on Workshop


In this workshop, you will **fork this repo** and build a real CI/CD pipeline around a small churn-prediction project containing 4 main steps.
(data validation → training → quality gate → Docker image → gated deployment).
No cloud account needed, only a free GitHub account.

The latest slides: [CI/CD Workshop 2026](https://docs.google.com/presentation/d/1vL3XFQwlAnl-TT3MHyd8Zzo2E3H-JKcY/edit?usp=sharing&rtpof=true&sd=true)

## What you'll learn

- Why CI/CD matters, and what is *different* for data/ML projects
- Writing GitHub Actions workflows (triggers, jobs, matrix, caching, artifacts, secrets, environments)
- Automating tests, linting, **data validation** and **model quality gates**
- Packaging a model service in Docker and publishing it to a registry
- Safe deployments with approvals, tags and releases
- Shift-left tooling: pre-commit, Dependabot, dependency audits

Stuck? Reference workflows are in [`solutions/`](solutions/).
Cheat sheet: [docs/cheatsheet.md](docs/cheatsheet.md).


## The problem: “how do I run your code?"

You don't need much to imagine this scenario:

```Vanessa’s laptop has pandas 2.2. Louis’s has pandas 1.5. A function works for Vanessa and crashes for Louis. Nobody wrote down which version the project needs, so they lose an afternoon. Later, Louis’s code is formatted with tabs and Vanessa’s with spaces, so every pull request shows hundreds of changed lines that mean nothing. A pipeline that has to build the project from scratch would hit the same issues, with no human to ask. ```

In this workshop, while the structure of the repo looks complicated, organizing it this way ensures we can put best practices in continues integration and development. We will discuss the role of each file below.

## Repository structure

```
.
├── README.md                     You are here
├── pyproject.toml                Package metadata, dependencies, ruff/pytest/coverage config
├── Dockerfile                    Builds a self-contained image that serves the model
├── .dockerignore                 Files excluded from the Docker build context
├── .gitignore                    Ignores caches, venvs, trained models, metrics.json
├── .pre-commit-config.yaml       Local git hooks (ruff, whitespace, YAML checks)
├── .github/
│   ├── workflows/
│   │   ├── ci.yml                STARTER workflow: you extend this in the exercises
│   │   ├── model.yml             Model quality gate on PRs that touch the model
│   │   ├── docker.yml            Builds and publishes the image on main and on tags
│   │   └── release.yml           Cuts a release when a v* tag is pushed
│   └── dependabot.yml            Weekly dependency update PRs (pip + GitHub Actions)
├── src/churn_workshop/           The Python package (the "application")
│   ├── __init__.py
│   ├── data.py
│   ├── features.py
│   ├── train.py
│   └── api.py
├── scripts/
│   └── check_metrics.py          Model quality gate
├── tests/
│   ├── test_data.py
│   ├── test_features.py
│   ├── test_train.py
│   └── test_api.py
├── docs/                         Workshop material (theory, exercises, cheat sheet)
└── solutions/                    Reference workflows for each exercise
```

Files generated at runtime (`models/model.joblib`, `metrics.json`, `coverage.xml`) are git-ignored.


## Understanding the repo structure
Below you will find a brief introduction to some files and tools that can make our projects more production ready. These files make our configurations easy to read for both human and machines.
### pyproject.toml
TOML is a simple configuration format (key = value, grouped in [sections]).Our `pyproject.toml` file fixes all of it by writing the answers down once, in a place both people and machines read.  This file answers to several questions:

- Which Python version does it need?
- Which libraries, and which versions of them?
- How do I run the tests?
- What code style does the team follow?

Without a shared file, the answers live in your head, a chat message or an outdated README. Every person ends up with a slightly different setup, which is exactly how “it works on my machine” happens. CI has the same problem, because a CI runner is a brand-new computer that knows nothing about your project. It needs the same written instructions.

What it answers, in plain terms

- What is this project called, and which Python does it need?	[project]
- Which libraries does it need to run?	dependencies
- Which extra tools do developers need?	the dev extra
- Which extra libraries are needed only to serve the model?	the serve extra
- How should the code be checked and formatted?	[tool.ruff]
- Where are the tests?	[tool.pytest.ini_options]

In the setup section below, the workshop’s core command,   `pip install -e ".[serve,dev]"`, works because of this file. pip reads it and installs everything listed. Locally and in CI, one command produces the same setup. **That’s why it’s central to CI/CD: the pipeline can rebuild your environment from a file instead of from someone’s memory.**

### Introducing the tools it configures

- **Linting:** An automatic proofreader for code. A linter scans your code without running it and flags likely mistakes, such as an unused variable, a missing import or a typo in a name. It’s like spell-check, but for programming.
- **Formatting:** Automatically laying code out in a consistent style (spacing, line length, quotes), so reviews are about logic and not about whitespace.
- **Ruff:** A tool that does both linting and formatting, and does it very fast. We use it because one tool replaces several older ones (flake8, isort, black).
- **pytest:** The tool that finds and runs our tests. A test is a small piece of code that checks that other code does what it should.
- **Coverage:** A measurement of how much of the code the tests actually run.

All of these tools have options, such as the line length, which checks to turn on or which folder holds the tests. They read those options from pyproject.toml. **That’s the second job of the file: it makes the team’s rules explicit, so the same rules apply on every laptop and in CI.**


### YAML files

YAML, which stands for “YAML Ain't Markup Language” (originally “Yet Another Markup Language”), is a flexible and accessible data serialization language often used in configuration files, data exchanges, and automated workflows. Its minimalist style and structure make it easily readable for humans (like developers and system administrators) while still being structured enough for machine processing.

**What is a YAML file?**
YAML files are plain text files that store data using YAML’s indentation-based structure. Because YAML mimics natural language and uses structured whitespace, these files often look like organized lists or outlines.

## Covarage
Code coverage is a software testing metric that measures the percentage of your application's source code executed when your automated test suite runs.

It acts as a diagnostic tool to show which parts of your codebase have been exercised by tests and, more importantly, which parts remain completely untested.

We will us the command  `pytest --cov --cov-report=term-missing`, to diagnose our code

--cov: Activates the pytest-cov plugin (a wrapper around coverage.py). It tracks which statements, branches, and functions in your source code are actually executed during the test run.

--cov-report=term-missing: Controls how and where the coverage report is presented:

term: Displays the summary table directly in the terminal/console stdout instead of generating an external file (like HTML or XML).

-missing: Adds a Missing column to that terminal table, listing the exact line numbers (or line ranges) that were never executed.

### What is pre-commit?

pre-commit is a small tool that runs checks automatically on your machine every time you run git commit. If a check fails, the commit is blocked until you fix the problem, and many fixes are applied for you.

Our .pre-commit-config.yaml runs these checks:

- ruff lints the code and auto-fixes what it can (such as unused imports and import order).
- ruff-format reformats the code to a consistent style.
- end-of-file-fixer and trailing-whitespace clean up whitespace.
- check-yaml catches broken YAML, which is useful when you’re writing workflows.
- check-added-large-files blocks accidental commits of files over 500 KB, such as datasets or models.

This was you no longer need to fear commiting issues!

Now, let's try it!

## Setup (10 min)

1. **Fork** this repository (button top-right), then clone *your fork*:
   ```bash
   git clone https://github.com/<your-user>/<repo>.git && cd <repo>
   ```
2. In your fork: **Actions tab → "I understand my workflows, go ahead and enable them"**.
3. Local environment (Python ≥ 3.10):
   ```bash
   python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate or create it on VS Code
   pip install -e ".[serve,dev]" && pre-commit install  # On windows swapp && with ; to run both commands in a single line

   # verify everything passes locally (same steps CI will run), run them one by one so you can see what happens in each step
   ruff check . && ruff format --check .                        ## On windows swapp && with ; to run both commands in a single line
   pytest --cov --cov-report=term-missing
   python -m churn_workshop.train
   python scripts/check_metrics.py metrics.json --min-auc 0.70
   ```
4. Docker is optional locally (CI builds the images for you).


### Application code: `src/churn_workshop/`

A small churn-prediction project. It is deliberately simple so the focus stays on CI/CD, not on modelling.

| File | Purpose |
|------|---------|
| `data.py` | Generates a reproducible **synthetic** customer dataset (no downloads) and `validate_data()`, the **data contract**: required columns, no nulls, valid ranges and categories. Raises `DataValidationError` on violations. Used in Exercise 3. |
| `features.py` | Feature engineering (`add_features`) and the scikit-learn preprocessing pipeline (scaling and one-hot encoding). Defines which columns are features and which is the target. |
| `train.py` | Validates data, trains a logistic-regression pipeline, and writes `models/model.joblib` plus `metrics.json` (ROC AUC, accuracy). Run with `python -m churn_workshop.train`. This is what CI runs to produce the model. |
| `api.py` | FastAPI service exposing `GET /health` and `POST /predict`. This is what the Docker image runs and what the container smoke test calls (Exercise 4). |
| `__init__.py` | Package marker and version number. |

### Quality tooling

| File | Purpose |
|------|---------|
| `scripts/check_metrics.py` | The **quality gate**. Reads `metrics.json` and exits with code 1 if ROC AUC is below the threshold (default 0.70), which makes the CI job fail. Used in Exercises 3 and 5. |
| `tests/test_data.py` | Checks that data generation is reproducible and that each validation rule rejects bad data. |
| `tests/test_features.py` | Checks feature functions behave correctly and never mutate their input. |
| `tests/test_train.py` | Checks training returns metrics in a valid range and is deterministic for a fixed seed. |
| `tests/test_api.py` | Trains a tiny model into a temp folder and tests `/health`, `/predict` and input validation with FastAPI's test client. |
| `.pre-commit-config.yaml` | Runs ruff and basic file hygiene checks on every local commit ("shift left": catch problems before CI). |
| `pyproject.toml` | Single config file: dependencies (`serve` and `dev` extras), ruff lint rules, pytest and coverage settings. |


### Packaging and automation

| File | Purpose |
|------|---------|
| `.github/workflows/ci.yml` | **Starter workflow.** It only echoes a message at first. You turn it into a real pipeline in Exercises 1 and 2. You will also add your own `model.yml`, `docker.yml` and `release.yml` here. |
| `.github/dependabot.yml` | Opens weekly PRs for outdated Python packages and GitHub Actions versions (enable Dependabot in repo settings). |
| `Dockerfile` | Installs the package, trains the model at build time so the image is self-contained, and starts the API with uvicorn on port 8000. |
| `.dockerignore` | Keeps tests, docs, `.git` and local models out of the image build. |
| `.gitignore` | Keeps generated artifacts and caches out of git. |

### Workshop material: `docs/`

| File | Purpose |
|------|---------|
| `theory.md` | Theory part: CI vs. CD, what is different for data/ML, test pyramid, GitHub Actions concepts, anti-patterns. |
| `exercise-1-first-pipeline.md` | Lint and test on every push and PR, break it on purpose, protect `main`. |
| `exercise-2-matrix-cache.md` | Python version matrix, dependency caching, concurrency, coverage artifacts, least-privilege permissions. |
| `exercise-3-model-gate.md` | Data validation rule, train in CI, metrics in the job summary, quality gate, sabotage the model. |
| `exercise-4-docker-cd.md` | Build and smoke-test the image, publish to GitHub Container Registry. |
| `exercise-5-release.md` | Tag-triggered release with staging, a manual approval gate and a GitHub Release. |
| `bonus.md` | Ten extra challenges (regression gate, drift check, PR comment bot, ...). |
| `cheatsheet.md` | GitHub Actions syntax and debugging tips. |

### Reference solutions: `solutions/`

These sit **outside** `.github/workflows/`, so they never run by accident. Try the exercise first, then compare.

| File | Matches |
|------|---------|
| `01-ci.yml` | Exercises 1 and 2: lint, test matrix, caching, coverage artifact |
| `02-model-gate.yml` | Exercise 3: train, metrics summary, quality gate, model artifact |
| `03-docker-publish.yml` | Exercise 4: build, smoke test, publish to GHCR |
| `04-release-deploy.yml` | Exercise 5: tag release with staging, approval and production |
| `05-scheduled-retrain-and-security.yml` | Bonus: nightly retraining and `pip-audit` |


## Ground rules

- Work on **branches and pull requests** in your fork, not directly on `main`, once Exercise 1 is done.
- Make CI **red on purpose** at least once. Seeing failures is how you learn to trust the pipeline.
- Peek at `solutions/` only after trying for a while.


## Are you ready?

![ready?](https://media1.giphy.com/media/v1.Y2lkPTc5MGI3NjExc2djeGsyMDRlOXVhdmdlNjJqbWg4bzRoZmJqb2F1c3Ywc2Fzb2xuYSZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/CjmvTCZf2U3p09Cn0h/giphy.gif)
