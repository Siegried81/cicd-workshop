# Technical deep dive

The companion to [`README_SIEG.md`](../README_SIEG.md). What each workflow does, why
it is built that way, and the traps that cost real time.

## The project under test

A churn model small enough to ignore: logistic regression on synthetic data. The
point is the plumbing around it. Four source modules carry the whole story:

- `data.py` — generates reproducible synthetic data, and `validate_data()` enforces
  a contract on any dataframe that enters.
- `features.py` — one derived feature (`is_new_customer = tenure_months < 6`) and the
  preprocessor (scale numerics, one-hot the contract).
- `train.py` — `train_model()` calls `validate_data()` first, splits, fits, and
  reports `roc_auc`, `accuracy`, `n_train`, `n_test`.
- `api.py` — FastAPI with `/health` and `/predict`.

`scripts/check_metrics.py` is the quality gate: it reads `metrics.json` and exits 1
if `roc_auc` is below a threshold passed on the command line.

## Exercise 1 — the first pipeline

`ci.yml` runs on every push to `main` and every pull request. Two jobs:

- `lint` — `ruff check` and `ruff format --check`.
- `test` — `pip install -e ".[serve,dev]"` then `pytest`, with `needs: lint`.

`needs: lint` is the one real decision here: cheap checks first, so a badly formatted
PR fails in seconds instead of after the whole test suite. The two jobs run on
separate runners, which is why each installs the project itself.

**Proof it works.** Flipping `< 6` to `> 6` in `features.py` makes exactly one test
fail, `test_is_new_customer_flag`, because that test recomputes the correct formula
and compares. A lint error (an unused import) fails `lint` instead. Two different
nets, two different failures.

## Exercise 2 — faster and more reliable

Same two jobs, five changes:

- **Matrix.** `test` runs on Python 3.10, 3.11, 3.12 in parallel. `fail-fast: false`
  so one version failing doesn't cancel the others — you want to see whether a bug
  hits one version or all three.
- **`cache: pip`.** Reuses the pip download cache between runs. First run installs
  normally; later runs log "Cache restored" and are faster.
- **`concurrency`.** `group: ci-${{ github.ref }}` with `cancel-in-progress: true`
  cancels an in-flight run when a newer commit lands on the same branch. Three quick
  pushes no longer mean three full pipelines.
- **Coverage artifact.** `pytest --cov --cov-report=xml`, uploaded with
  `upload-artifact`, but only `if: matrix.python-version == '3.12'` — otherwise all
  three matrix legs upload a file with the same name and collide.
- **Least privilege.** `permissions: contents: read`. The jobs only read code.

Cost vs risk: cache and concurrency cut cost; the matrix, coverage and least
privilege cut risk. Testing one version only makes sense when you alone deploy on one
fixed interpreter (the Docker image here is 3.12). The matrix earns its keep for a
library other people install on interpreters you don't control.

### Trap: the matrix renames the required check

This one blocked a merge. Branch protection on `main` required status checks named
`lint` and `test`. In exercise 1 the test check was literally `test`, so it matched.
The moment the matrix landed, the check became three runs named `test (3.10)`,
`test (3.11)`, `test (3.12)`. Nothing is named `test` any more, so the required
check sits forever at **"Expected — Waiting for status to be reported"** — not a
failure, a wait for something that will never arrive.

Two fixes:

- **Quick:** in the ruleset, drop `test` and require `test (3.10)`, `test (3.11)`,
  `test (3.12)`. Works, but the names change if you ever change the version list.
- **Robust:** add one aggregation job with a stable name and require only that.

```yaml
  ci-ok:
    needs: [lint, test]      # waits for lint and ALL matrix legs
    if: always()
    runs-on: ubuntu-latest
    steps:
      - run: |
          [ "${{ needs.lint.result }}" = "success" ] && \
          [ "${{ needs.test.result }}" = "success" ] || exit 1
```

`needs: test` on a matrix waits for every leg; `if: always()` makes `ci-ok` run even
when a leg failed, and the script turns the aggregated results into one pass/fail.
Require `ci-ok` and the matrix can change shape without ever touching the ruleset.

## Exercise 3 — data and model quality gates

Tests protect code correctness. They do not protect model quality, and they do not
protect you from bad data. This exercise adds the two gates that do.

### The data contract

`REQUIRED_COLUMNS` at the top of `data.py` declares structure: which columns exist
and their types. That is fixed up front, and `validate_data()` reads it rather than
repeating it. But a type declaration can't express meaning — `tenure_months = 5000`
is a valid int and nonsense, `support_tickets = -3` is a valid int and impossible.
Those are business rules, and they live as explicit checks in `validate_data()`:
ranges, allowed values, non-negativity.

A schema is a promise; data arriving from outside keeps no promises. So the contract
is enforced at the door, every time, fail-closed — and `train_model()` calls
`validate_data()` on its first line, so the check runs at the start of every training
run, not once at project setup. I added `support_tickets >= 0` plus a test proving a
negative value is rejected (13 tests → 14).

In a production system these hand-written checks become a declarative schema
(pandera, pydantic, Great Expectations). Here they are explicit on purpose: zero
dependencies, nothing hidden.

### The model gate

`model.yml` runs on PRs that touch `src/`, `scripts/` or `pyproject.toml`. It trains,
writes the metrics into the job summary (`$GITHUB_STEP_SUMMARY`), then runs
`check_metrics.py --min-auc 0.70` **before** uploading the model artifact. Order
matters: gate first, so a weak model fails the PR and is never published. The artifact
is named `model-${{ github.sha }}`, so a model is always traceable to the commit that
produced it.

### Why a fixed threshold isn't enough

Three sabotages in `features.py`, and what each one proves:

| Change | Unit tests | Gate (AUC ≥ 0.70) | Lesson |
| --- | --- | --- | --- |
| `< 6` → `< 60` | fail | passes (~0.83) | the code check catches it first |
| remove `tenure_months` from `NUMERIC` | pass | **passes (~0.78)** | a fixed threshold lets a real regression through |
| `NUMERIC = ["is_new_customer"]` | pass | **fails (~0.68)** | only a metric gate catches a correct-but-worse model |

The middle row is the uncomfortable one. A fixed 0.70 is blunt: it waves through a
model that got measurably worse but stayed above the line. The real answer is a
**regression check** — compare against the model currently on `main`, not a constant
— plus checks on slices (per contract type), and a threshold that lives in version
control and changes only through review. On my run the healthy model scores 0.8318.

## Exercise 4 — containers and continuous delivery

`docker.yml` behaves differently by event:

- **On a PR:** build with `load: true`, `push: false`, then a smoke test — start the
  container and poll `/health` up to 20 times. A built image isn't a working image;
  this catches a Dockerfile that builds but serves nothing. A broken `COPY` path now
  fails the PR before merge.
- **On push to `main` or a tag:** log in to GHCR with the built-in
  `secrets.GITHUB_TOKEN` (no personal secret needed) and push.

Tags come from `docker/metadata-action`: `type=sha`, branch, and semver on a tag.
Tagging by SHA, not only `latest`, is what makes rollback possible — redeploy the
previous `sha-xxxxxxx` and you are back exactly where you were. The image trains the
model at build time, which keeps the image self-contained but couples model and code
in one artifact; the alternative is to bake code only and pull a versioned model from
a registry at start-up.

**Verified locally:** the image builds, `/health` returns
`{"status":"ok","version":"0.1.0"}`, `/predict` returns `{"churn_probability":0.9841}`.
On a GitHub runner the whole docker job is about 1m30 with the smoke test.

A production next step: scan the image for vulnerabilities, generate an SBOM, and
sign it.

## Exercise 5 — releases with an approval gate

`release.yml` triggers only on tags `v*`, with three jobs chained by `needs:`:

1. `verify` — re-run tests, re-train, re-gate on the exact tagged commit. Never
   release something CI never saw.
2. `deploy-staging` — `environment: staging`, no rules, deploys automatically.
3. `deploy-production` — `environment: production`, which pauses until a required
   reviewer approves, then `gh release create --generate-notes`.

The real deploy commands are `echo`s. The structure is the lesson: automatic to
staging, a human gate before production. That gate is a GitHub **environment** with
required reviewers, set up in Settings before the first tag — without it there is
nothing to pause on.

Rollback drill: redeploying the previous image tag is faster and leaves staging
untouched; reverting the commit and cutting `v0.1.2` is slower but leaves a cleaner
audit trail. In a bank you usually want both — fast mitigation now, clean history
after.

## How this was verified

Everything was checked locally before it went up: a virtualenv install, the full
pytest suite, ruff, a real training run through the gate, and an actual Docker build
with the container's `/health` and `/predict` polled with `curl`. Then each exercise
went up as its own branch and PR, and the GitHub Actions runs were watched to green.

### Trap: a fork sends pull requests to its parent by default

A PR opened from a fork defaults its **base repository** to the parent, not the fork.
With no default set, `gh pr create` and the GitHub PR screen both aim upstream. The
fix: `gh repo set-default <you>/<repo>` pins it, and on the web PR screen the **base
repository** dropdown at the top is the one place to check before clicking. `git push`
is safe as long as `origin` is your fork — you usually have no write access upstream
anyway; the only thing you can do to the parent is open a PR against it.
