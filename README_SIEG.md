# CI/CD workshop — my run through it

This is my fork of [`vriveraq/cicd-workshop`](https://github.com/vriveraq/cicd-workshop),
a CI/CD-for-ML workshop built around a tiny churn-prediction project. The original
[`README.md`](README.md) is the author's. This file is my own: what I built, how it
works, and how to run it. The reasoning and the traps I hit are in
[`docs/technical_deep_dive.md`](docs/technical_deep_dive.md).

## What I did

I went through the five exercises, each on its own branch and its own pull request,
so every step could be reviewed and watched running in GitHub Actions. All five
went in as pull requests and are merged into `main`.

| Exercise | Branch | What it adds | Workflow |
| --- | --- | --- | --- |
| 1 | `feature/real-ci` | lint + test jobs, `test` needs `lint` | `.github/workflows/ci.yml` |
| 2 | `feature/faster-ci` | matrix (3.10/3.11/3.12), pip cache, cancel old runs, coverage artifact, least privilege | `ci.yml` |
| 3 | `feature/model-gate` | a new data rule + test, and a model quality gate (fail the PR if ROC AUC < 0.70) | `.github/workflows/model.yml` |
| 4 | `feature/docker-cd` | build the image on every PR, smoke-test it, publish to GHCR on merge | `.github/workflows/docker.yml` |
| 5 | `feature/release-gate` | tagged release through staging → production with a human approval gate | `.github/workflows/release.yml` |

The branches stack: each one is a single commit on top of the previous, so the
intended merge order is 1 → 2 → 3 → 4 → 5.

## The three safety nets this repo ends up with

- **Code is correct** — `pytest` (14 tests) and `ruff` run on every push and PR.
- **Data and model are good enough** — the data contract rejects bad rows before
  training, and the quality gate fails a PR whose model drops below ROC AUC 0.70.
- **The thing we ship actually runs** — the image is built and its `/health`
  endpoint is polled before anything is published, and production waits for a human.

## Run it locally

Python 3.10+ (I used a 3.14 virtualenv; CI tests 3.10, 3.11, 3.12).

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[serve,dev]"   # Windows path shown

pytest                      # 14 tests
ruff check . && ruff format --check .
python -m churn_workshop.train          # writes models/model.joblib + metrics.json
python scripts/check_metrics.py metrics.json --min-auc 0.70   # the quality gate
```

Docker (optional, needs Docker running):

```bash
docker build -t churn-workshop .
docker run -d --name api -p 8000:8000 churn-workshop
curl --noproxy localhost http://localhost:8000/health
# -> {"status":"ok","version":"0.1.0"}
curl --noproxy localhost -X POST http://localhost:8000/predict \
  -H 'content-type: application/json' \
  -d '{"tenure_months":3,"monthly_charges":95,"support_tickets":5,"contract":"month-to-month"}'
# -> {"churn_probability":0.9841}
```

## State and what's left (GitHub-side, by hand)

The five exercises are merged. `main` is protected by a ruleset that requires one
status check, `ci-ok` — an aggregate job that is green only when `lint` and all three
matrix test legs pass. That single stable name is what branch protection requires, so
the matrix can change shape without touching the rule (see the deep dive for the trap
this avoids).

Still by hand:

1. The Docker image is published to the repo's **Packages** on each merge to `main`
   (`ghcr.io/siegried81/cicd-workshop`).
2. For exercise 5, create the `staging` and `production` environments (production
   with required reviewers), then `git tag v0.1.0 && git push origin v0.1.0` and
   approve the run when it pauses before production.

## Numbers from my run

- 14 tests, 87% line coverage.
- ROC AUC 0.8318 on the synthetic data; gate threshold 0.70.
- Docker job on a GitHub runner: about 1m30, smoke test included.
