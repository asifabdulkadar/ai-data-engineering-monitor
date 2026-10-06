-- ============================================
-- Monitoring Queries — Useful Ad-Hoc Queries
-- ============================================
-- These are NOT executed by the application.
-- Use them for manual investigation and debugging.

-- 1. Latest pipeline run
SELECT run_id, pipeline_name, status, rows_received, rows_processed,
       rows_rejected, start_time, end_time,
       EXTRACT(EPOCH FROM (end_time - start_time)) AS duration_seconds
FROM   pipeline_runs
ORDER  BY start_time DESC
LIMIT  1;

-- 2. All failed pipeline runs
SELECT run_id, pipeline_name, status, error_message, start_time
FROM   pipeline_runs
WHERE  status = 'FAILED'
ORDER  BY start_time DESC;

-- 3. Quality check failures for a specific run
SELECT check_name, status, severity, actual_value, expected_value, message
FROM   data_quality_results
WHERE  run_id = '<RUN_ID>'
  AND  status = 'FAIL'
ORDER  BY severity DESC;

-- 4. Anomaly summary by type
SELECT anomaly_type, severity, COUNT(*) AS occurrences
FROM   anomaly_events
GROUP  BY anomaly_type, severity
ORDER  BY occurrences DESC;

-- 5. Unresolved anomalies
SELECT ae.id, ae.anomaly_type, ae.severity, ae.description, ae.detected_at,
       pr.pipeline_name
FROM   anomaly_events ae
JOIN   pipeline_runs pr ON ae.run_id = pr.run_id
WHERE  ae.resolved = FALSE
ORDER  BY ae.detected_at DESC;

-- 6. Customer table row count
SELECT COUNT(*) AS total_customers FROM customers;

-- 7. NULL rate per column (customers)
SELECT
    'gender'           AS col, ROUND(100.0 * SUM(CASE WHEN gender           IS NULL THEN 1 ELSE 0 END) / COUNT(*), 2) AS null_pct FROM customers
UNION ALL SELECT
    'tenure'           AS col, ROUND(100.0 * SUM(CASE WHEN tenure           IS NULL THEN 1 ELSE 0 END) / COUNT(*), 2) FROM customers
UNION ALL SELECT
    'monthly_charges'  AS col, ROUND(100.0 * SUM(CASE WHEN monthly_charges  IS NULL THEN 1 ELSE 0 END) / COUNT(*), 2) FROM customers
UNION ALL SELECT
    'total_charges'    AS col, ROUND(100.0 * SUM(CASE WHEN total_charges    IS NULL THEN 1 ELSE 0 END) / COUNT(*), 2) FROM customers;

-- 8. Duplicate customer IDs
SELECT customer_id, COUNT(*) AS cnt
FROM   customers
GROUP  BY customer_id
HAVING COUNT(*) > 1;

-- 9. Pipeline run history (last 10)
SELECT run_id, pipeline_name, status, rows_received, rows_processed,
       rows_rejected, start_time, end_time
FROM   pipeline_runs
ORDER  BY start_time DESC
LIMIT  10;

-- 10. Latest incident report
SELECT ir.incident_title, ir.severity, ir.summary,
       ir.confirmed_facts, ir.possible_root_causes,
       ir.business_impact, ir.recommended_actions, ir.confidence
FROM   incident_reports ir
ORDER  BY ir.created_at DESC
LIMIT  1;
