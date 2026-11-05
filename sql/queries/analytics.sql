-- Analytical queries used by operations and model monitoring. PostgreSQL syntax.

-- 1. Fraud decision mix per day, for the approval-rate and alert-volume dashboard.
SELECT date_trunc('day', occurred_at) AS day,
       decision,
       COUNT(*)                        AS attempts,
       ROUND(AVG(fraud_score)::numeric, 4) AS avg_score
FROM card_transactions
WHERE occurred_at >= now() - INTERVAL '30 days'
GROUP BY 1, 2
ORDER BY 1 DESC, 2;

-- 2. Velocity feature as the model sees it: attempts per card in the trailing hour.
--    Use this exact window definition when building training data to avoid leakage.
SELECT t.id,
       t.account_id,
       t.occurred_at,
       (SELECT COUNT(*)
          FROM card_transactions p
         WHERE p.account_id = t.account_id
           AND p.occurred_at >= t.occurred_at - INTERVAL '1 hour'
           AND p.occurred_at <  t.occurred_at) AS txns_last_hour
FROM card_transactions t
ORDER BY t.occurred_at DESC
LIMIT 100;

-- 3. Structuring candidates: accounts with repeated outgoing transfers just below the 10,000.00
--    reporting threshold (amounts in minor units, so 1,000,000 = 10,000.00).
SELECT p.account_id,
       COUNT(*)                AS near_threshold_outflows,
       MIN(p.amount_minor)     AS smallest,
       MAX(p.amount_minor)     AS largest
FROM postings p
WHERE p.amount_minor < 0
  AND -p.amount_minor BETWEEN 900000 AND 999999
GROUP BY p.account_id
HAVING COUNT(*) >= 3
ORDER BY near_threshold_outflows DESC;

-- 4. Approval rate by credit decision version, for model-release comparison.
SELECT model_version,
       COUNT(*) FILTER (WHERE outcome = 'APPROVE') * 1.0 / COUNT(*) AS approval_rate,
       COUNT(*) AS decisions
FROM decision_log
WHERE kind = 'credit'
GROUP BY model_version
ORDER BY model_version;
