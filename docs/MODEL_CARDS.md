# Model Cards

These cards describe what each model is, the data it was trained on, how it was evaluated, and
where it must not be used. Treat them as living documents. Update them whenever a model changes.

---

## 1. Card fraud scorer (`fraud`)

**Version:** `fraud-hgb-isotonic/2026.11.1`
**Type:** Gradient-boosted decision trees (scikit-learn `HistGradientBoostingClassifier`) with isotonic
probability calibration (`CalibratedClassifierCV`, 3 folds).
**Output:** Probability that an authorization attempt is fraudulent. Mapped to APPROVE / REVIEW / DECLINE
by thresholds (`FRAUD_REVIEW_THRESHOLD`, default 0.30; `FRAUD_DECLINE_THRESHOLD`, default 0.70).

**Features** (`neobank/features.py`):

| Feature | Meaning |
|---|---|
| `log_amount` | log(1 + amount, minor units) |
| `log_ratio_to_30d_mean` | log(1 + amount / account's 30-day mean amount) |
| `txns_last_hour` | Prior attempts on the card in the last hour (includes declined) |
| `log_spend_last_24h` | log(1 + prior spend in 24h + current amount) |
| `new_device` | Device id not seen on this account before |
| `night_time` | Authorization between 00:00 and 05:59 UTC |
| `card_not_present` | Online channel |
| `atm` | ATM channel |
| `high_risk_mcc` | MCC 4829 (wire transfer), 6051 (quasi-cash) or 7995 (gambling) |

**Hard rules** (applied before thresholds): more than 20 attempts in an hour → DECLINE; amount above
the single-transaction policy cap (50,000.00 in minor units of 5,000,000) → DECLINE.

**Training data:** *Synthetic.* `neobank/ml/synthetic.py` draws fraud and legitimate contexts from
different distributions (fraud has higher amounts, night activity, new devices, online channel and
more attempts). The fraud rate is 2%.

**Evaluation (holdout, synthetic):** PR-AUC 0.988, ROC-AUC 0.9997, Brier 0.0014.

> **Read this before quoting any number.** These metrics describe how well the model separates
> classes produced by the generator. They say nothing about real fraud. The classes in the synthetic
> data are separated far more cleanly than real fraud is. Real performance will be much lower and
> must be measured on labelled production or historical data.

**Intended use:** Demonstrating a fraud scoring pipeline, and as a starting point for calibration
and threshold work on your own labelled data.

**Out of scope:** Any real authorization decision without retraining on your data, validation, and
a champion/challenger rollout.

**Known risks:**
- Mixed-hour and new-device signals can penalize travelers and people who change phones. Route
  declines to review where possible, and measure false-positive rate by segment.
- Velocity counts include declined attempts. A fraudster's retries can cause a legitimate customer
  to be declined later.
- MCC-based risk is a crude proxy and should be replaced by merchant-level risk data.

---

## 2. Credit scorecard (`credit`)

**Version:** `credit-logreg/2026.11.1`
**Type:** Standardized logistic regression (`StandardScaler` + `LogisticRegression`), the usual scorecard form.
**Output:** Probability of default within 12 months (synthetic target). Decision: APPROVE if
PD < 0.05, DECLINE if PD > 0.15, REFER otherwise. Approved amount is capped at 50% of annual income.

**Features** (`neobank/features.py`): log annual income, debt-to-income (monthly debt ÷ monthly income,
capped at 5), revolving utilization (0–1), late payments in 24 months, credit history in years, and
credit inquiries in 6 months.

**Deliberately excluded:** age, gender, marital status, religion, national origin, postcode, and any
other protected or proxy attribute. Excluding them does not prevent indirect discrimination through
correlated features. Test outcomes across groups before use (see the fairness section).

**Reason codes:** For each declined or referred application, the top three features by positive
contribution (`coefficient × standardized value`) become the reason codes. These are the features
that raise default risk most relative to the average applicant.

**Training data:** *Synthetic.* A logistic default model over the same features, with a base default
rate of about 11%.

**Evaluation (holdout, synthetic):** ROC-AUC 0.698, Brier 0.092.

> The low AUC is what you should expect from a logistic model fitted to noisy synthetic targets.
> It is not evidence of a good or bad production model.

**Fairness and validation checklist before any real use:**
- Calibration by segment (is a predicted 5% default rate really about 5% for each group?).
- Approval rate and error rates by protected group, using `neobank.monitoring.approval_rate_by_group`
  for the outcome view. Disparate-impact analysis needs lawful, appropriate group data.
- Reject inference. This model is trained only on the outcomes of accepted applicants in production,
  so the training sample is biased toward past decisions.
- Adverse-action notices with reason codes, as your jurisdiction requires.
- Independent model validation and documentation under your model-risk framework (for example,
  SR 11-7 in the US, or the equivalent in your jurisdiction).

---

## 3. AML alert triage (rules v1, no learned model)

**Version:** rules in `neobank/aml.py`
**Output:** A 0–1 risk score per account, from three flags: structuring, pass-through and fan-out.
**Structuring:** outgoing transfers between 90% and 100% of the 10,000.00 reporting threshold.
**Pass-through:** an inflow forwarded at 85–100% of its amount within 48 hours.
**Fan-out:** outbound transfers to 8 or more distinct accounts.

**Why rules first:** Analysts can explain every alert, and the rules define the baseline any learned
model must beat. A graph neural network is the planned upgrade. It must show a clear lift in
precision at a fixed review capacity, measured on analyst-confirmed alerts, before it replaces the rules.

**Limitations:** Thresholds and weights are not calibrated to any jurisdiction's reporting rules.
Check them with your compliance team. The score is for prioritizing review and must never be used
as the sole basis for filing a suspicious activity report or closing an account.

---

## 4. Reconciliation matcher (no learned model)

**Version:** rules in `neobank/reconciliation.py`
**Method:** A bank line matches a ledger line when the amounts are equal, the dates are within 2 days,
and the normalized descriptions have a `difflib` similarity of at least 0.5. The combined score is
`0.7 × similarity + 0.3 × date_proximity`. Matching is one-to-one and greedy by score.

**Known weakness:** Character similarity can confuse merchants with similar names. Use a learned
similarity model trained on confirmed matches once you have labelled data.

---

## Monitoring commitments for any model in production

- **Input drift:** PSI per feature, weekly. Thresholds: under 0.10 stable, 0.10–0.25 investigate,
  over 0.25 drift (`neobank.monitoring.psi`, `drift_status`).
- **Outcome performance:** PR-AUC or Gini and calibration on matured outcomes, monthly.
- **Decision mix:** approval, review and decline rates per day and per model version
  (`sql/queries/analytics.sql`).
- **Rollback:** Keep the previous artifact available. Promotion requires beating the incumbent on the
  agreed metrics over a frozen holdout.
