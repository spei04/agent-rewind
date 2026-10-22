"""Bounded original-source and graph keyset statements."""

# Fixed fragments share identical predicates; no input becomes SQL syntax.

_SQLITE_ALL_GRAPH_PAGE_GATE_API_KEYS_FIRST_VALID = (
    ' (typeof(t."id")=\'text\' AND length(t."id")=32 AND length(CAST(t."id" AS '
    'BLOB))=32 AND t."id" NOT GLOB \'*[^0-9a-f]*\' AND (t."revoked" IS NULL OR '
    "(typeof(t.\"revoked\") IN ('integer','real') AND t.\"revoked\" IN (0,1))) "
    "AND typeof(t.\"expires\") IN ('integer','real') AND t.\"expires\" BETWEEN "
    "-1.7976931348623157e308 AND 1.7976931348623157e308) AND (s.resource_id "
    "IS NOT NULL AND (typeof(s.resource_id)='text' AND "
    "length(s.resource_id)=32 AND length(CAST(s.resource_id AS BLOB))=32 AND "
    "s.resource_id NOT GLOB '*[^0-9a-f]*') AND (typeof(s.project_id)='text' "
    "AND length(s.project_id)=32 AND length(CAST(s.project_id AS BLOB))=32 "
    "AND s.project_id NOT GLOB '*[^0-9a-f]*') AND p.id=s.project_id AND "
    "p.organization_id=:installation_org) "
)


_SQLITE_ALL_GRAPH_PAGE_GATE_JOBS_FIRST_VALID = (
    ' (typeof(t."id")=\'text\' AND length(t."id")=32 AND length(CAST(t."id" AS '
    'BLOB))=32 AND t."id" NOT GLOB \'*[^0-9a-f]*\' AND t."kind" IN '
    "('run','branch','study','investigate')) AND (s.resource_id IS NOT NULL "
    "AND (typeof(s.resource_id)='text' AND length(s.resource_id)=32 AND "
    "length(CAST(s.resource_id AS BLOB))=32 AND s.resource_id NOT GLOB "
    "'*[^0-9a-f]*') AND (typeof(s.project_id)='text' AND "
    "length(s.project_id)=32 AND length(CAST(s.project_id AS BLOB))=32 AND "
    "s.project_id NOT GLOB '*[^0-9a-f]*') AND p.id=s.project_id AND "
    "p.organization_id=:installation_org) "
)


_SQLITE_ALL_GRAPH_PAGE_GATE_RECORDS_FIRST_VALID = (
    ' (typeof(t."id")=\'text\' AND length(t."id")=32 AND length(CAST(t."id" AS '
    'BLOB))=32 AND t."id" NOT GLOB \'*[^0-9a-f]*\' AND t."kind" IN '
    "('run','study')) AND (s.resource_id IS NOT NULL AND "
    "(typeof(s.resource_id)='text' AND length(s.resource_id)=32 AND "
    "length(CAST(s.resource_id AS BLOB))=32 AND s.resource_id NOT GLOB "
    "'*[^0-9a-f]*') AND (typeof(s.project_id)='text' AND "
    "length(s.project_id)=32 AND length(CAST(s.project_id AS BLOB))=32 AND "
    "s.project_id NOT GLOB '*[^0-9a-f]*') AND p.id=s.project_id AND "
    "p.organization_id=:installation_org) "
)


_POSTGRESQL_ALL_GRAPH_PAGE_GATE_API_KEYS_FIRST_VALID = (
    ' (octet_length(t."id")=32 AND t."id" ~ \'^[0-9a-f]{32}$\' AND '
    '(t."revoked" IS NULL OR t."revoked" IN (FALSE,TRUE)) AND t."expires" IS '
    "NOT NULL AND t.\"expires\" NOT IN ('NaN'::double "
    "precision,'Infinity'::double precision,'-Infinity'::double precision)) "
    "AND (s.resource_id IS NOT NULL AND (octet_length(s.resource_id)=32 AND "
    "s.resource_id ~ '^[0-9a-f]{32}$') AND (octet_length(s.project_id)=32 "
    "AND s.project_id ~ '^[0-9a-f]{32}$') AND p.id=s.project_id AND "
    "p.organization_id=:installation_org) "
)


_POSTGRESQL_ALL_GRAPH_PAGE_GATE_JOBS_FIRST_VALID = (
    ' (octet_length(t."id")=32 AND t."id" ~ \'^[0-9a-f]{32}$\' AND t."kind" IN '
    "('run','branch','study','investigate')) AND (s.resource_id IS NOT NULL "
    "AND (octet_length(s.resource_id)=32 AND s.resource_id ~ "
    "'^[0-9a-f]{32}$') AND (octet_length(s.project_id)=32 AND s.project_id ~ "
    "'^[0-9a-f]{32}$') AND p.id=s.project_id AND "
    "p.organization_id=:installation_org) "
)


_POSTGRESQL_ALL_GRAPH_PAGE_GATE_RECORDS_FIRST_VALID = (
    ' (octet_length(t."id")=32 AND t."id" ~ \'^[0-9a-f]{32}$\' AND t."kind" IN '
    "('run','study')) AND (s.resource_id IS NOT NULL AND "
    "(octet_length(s.resource_id)=32 AND s.resource_id ~ '^[0-9a-f]{32}$') "
    "AND (octet_length(s.project_id)=32 AND s.project_id ~ '^[0-9a-f]{32}$') "
    "AND p.id=s.project_id AND p.organization_id=:installation_org) "
)


_SQLITE_ALL_GRAPH_PAGE_GATE_EVENTS_FIRST_VALID = (
    ' (typeof(t."run_id")=\'text\' AND length(t."run_id")=32 AND '
    'length(CAST(t."run_id" AS BLOB))=32 AND t."run_id" NOT GLOB '
    "'*[^0-9a-f]*' AND typeof(t.\"step\")='integer' AND t.\"step\" >= 1) AND "
    "(1=1) "
)


_POSTGRESQL_ALL_GRAPH_PAGE_GATE_EVENTS_FIRST_VALID = (
    ' (octet_length(t."run_id")=32 AND t."run_id" ~ \'^[0-9a-f]{32}$\' AND '
    't."step" IS NOT NULL AND t."step" >= 1) AND (1=1) '
)


_SQLITE_ALL_SOURCE_COUNT_API_KEYS_PROJECTION = (
    'SELECT count(*) AS candidate_rows FROM (SELECT 1 FROM "api_keys" ORDER '
    'BY "id" LIMIT :remaining_rows_plus_one) AS bounded\n'
)


_SQLITE_ALL_SOURCE_COUNT_AUDIT_PROJECTION = (
    'SELECT count(*) AS candidate_rows FROM (SELECT 1 FROM "audit" ORDER BY '
    '"id" LIMIT :remaining_rows_plus_one) AS bounded\n'
)


_SQLITE_ALL_SOURCE_COUNT_EVENTS_PROJECTION = (
    'SELECT count(*) AS candidate_rows FROM (SELECT 1 FROM "events" ORDER BY '
    '"run_id","step" LIMIT :remaining_rows_plus_one) AS bounded\n'
)


_SQLITE_ALL_SOURCE_COUNT_JOBS_PROJECTION = (
    'SELECT count(*) AS candidate_rows FROM (SELECT 1 FROM "jobs" ORDER BY '
    '"id" LIMIT :remaining_rows_plus_one) AS bounded\n'
)


_SQLITE_ALL_SOURCE_COUNT_RECORDS_PROJECTION = (
    'SELECT count(*) AS candidate_rows FROM (SELECT 1 FROM "records" ORDER '
    'BY "id" LIMIT :remaining_rows_plus_one) AS bounded\n'
)


_SQLITE_ALL_GRAPH_PAGE_GATE_JOBS_FIRST_RANKED = (
    ", ranked AS MATERIALIZED (SELECT *, sum(native_bytes) OVER (ORDER BY "
    '"id" ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS prefix_bytes '
    "FROM candidate) "
)


_SQLITE_ALL_GRAPH_PAGE_GATE_JOBS_FIRST_PROJECTION = (
    "SELECT count(*) AS candidates, coalesce(sum(invalid),0) AS "
    "invalid_candidates, coalesce(sum(CASE WHEN prefix_bytes<=16777216 THEN "
    "1 ELSE 0 END),0) AS accepted_rows, coalesce(max(CASE WHEN "
    "prefix_bytes<=16777216 THEN prefix_bytes END),0) AS "
    'accepted_original_native_bytes,(SELECT "id" FROM ranked WHERE '
    'prefix_bytes<=16777216 ORDER BY "id" DESC LIMIT 1) AS end_id FROM '
    "ranked\n"
)


_SQLITE_ALL_GRAPH_PAGE_GATE_EVENTS_FIRST_RANKED = (
    ", ranked AS MATERIALIZED (SELECT *, sum(native_bytes) OVER (ORDER BY "
    '"run_id","step" ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS '
    "prefix_bytes FROM candidate) "
)


_SQLITE_ALL_GRAPH_PAGE_GATE_EVENTS_FIRST_PROJECTION = (
    "SELECT count(*) AS candidates, coalesce(sum(invalid),0) AS "
    "invalid_candidates, coalesce(sum(CASE WHEN prefix_bytes<=16777216 THEN "
    "1 ELSE 0 END),0) AS accepted_rows, coalesce(max(CASE WHEN "
    "prefix_bytes<=16777216 THEN prefix_bytes END),0) AS "
    'accepted_original_native_bytes,(SELECT "run_id" FROM ranked WHERE '
    'prefix_bytes<=16777216 ORDER BY "run_id" DESC,"step" DESC LIMIT 1) AS '
    'end_run_id,(SELECT "step" FROM ranked WHERE prefix_bytes<=16777216 '
    'ORDER BY "run_id" DESC,"step" DESC LIMIT 1) AS end_step FROM ranked\n'
)


_SQLITE_ALL_SCOPE_COMPLETE_COUNT_PROJECTION = (
    "SELECT count(*) AS scope_candidates FROM (SELECT 1 FROM resource_scopes "
    "ORDER BY resource_kind,resource_id LIMIT :expected_scopes_plus_one) AS "
    "bounded\n"
)


SQL: dict[tuple[str, str, str], str] = {
    ("all", "sqlite", "source_count_api_keys"): "".join(
        (_SQLITE_ALL_SOURCE_COUNT_API_KEYS_PROJECTION,)
    ),
    ("all", "sqlite", "source_stats_api_keys"): (
        "SELECT count(*) AS observed_rows, coalesce(sum(CASE WHEN "
        '(typeof(t."id")=\'text\' AND length(t."id")=32 AND length(CAST(t."id" AS '
        'BLOB))=32 AND t."id" NOT GLOB \'*[^0-9a-f]*\' AND (t."revoked" IS NULL OR '
        "(typeof(t.\"revoked\") IN ('integer','real') AND t.\"revoked\" IN (0,1))) "
        "AND typeof(t.\"expires\") IN ('integer','real') AND t.\"expires\" BETWEEN "
        "-1.7976931348623157e308 AND 1.7976931348623157e308) THEN 0 ELSE 1 "
        'END),0) AS graph_invalid_rows, coalesce(max((coalesce(length(CAST(t."id"'
        ' AS BLOB)),0)+coalesce(length(CAST(t."hash" AS '
        'BLOB)),0)+coalesce(length(CAST(t."role" AS '
        'BLOB)),0)+coalesce(length(CAST(t."name" AS '
        'BLOB)),0)+coalesce(length(CAST(t."expires" AS '
        'BLOB)),0)+coalesce(length(CAST(t."revoked" AS BLOB)),0))),0) AS '
        'max_original_native_bytes, coalesce(sum((coalesce(length(CAST(t."id" AS '
        'BLOB)),0)+coalesce(length(CAST(t."hash" AS '
        'BLOB)),0)+coalesce(length(CAST(t."role" AS '
        'BLOB)),0)+coalesce(length(CAST(t."name" AS '
        'BLOB)),0)+coalesce(length(CAST(t."expires" AS '
        'BLOB)),0)+coalesce(length(CAST(t."revoked" AS BLOB)),0))),0) AS '
        'original_native_bytes FROM "api_keys" AS t\n'
    ),
    ("all", "sqlite", "source_count_audit"): "".join((_SQLITE_ALL_SOURCE_COUNT_AUDIT_PROJECTION,)),
    ("all", "sqlite", "source_stats_audit"): (
        "SELECT count(*) AS observed_rows, coalesce(sum(CASE WHEN (1=1) THEN 0 "
        "ELSE 1 END),0) AS graph_invalid_rows, "
        'coalesce(max((coalesce(length(CAST(t."id" AS '
        'BLOB)),0)+coalesce(length(CAST(t."created" AS '
        'BLOB)),0)+coalesce(length(CAST(t."actor" AS '
        'BLOB)),0)+coalesce(length(CAST(t."action" AS '
        'BLOB)),0)+coalesce(length(CAST(t."target" AS BLOB)),0))),0) AS '
        'max_original_native_bytes, coalesce(sum((coalesce(length(CAST(t."id" AS '
        'BLOB)),0)+coalesce(length(CAST(t."created" AS '
        'BLOB)),0)+coalesce(length(CAST(t."actor" AS '
        'BLOB)),0)+coalesce(length(CAST(t."action" AS '
        'BLOB)),0)+coalesce(length(CAST(t."target" AS BLOB)),0))),0) AS '
        'original_native_bytes FROM "audit" AS t\n'
    ),
    ("all", "sqlite", "source_count_events"): "".join(
        (_SQLITE_ALL_SOURCE_COUNT_EVENTS_PROJECTION,)
    ),
    ("all", "sqlite", "source_stats_events"): (
        "SELECT count(*) AS observed_rows, coalesce(sum(CASE WHEN "
        '(typeof(t."run_id")=\'text\' AND length(t."run_id")=32 AND '
        'length(CAST(t."run_id" AS BLOB))=32 AND t."run_id" NOT GLOB '
        "'*[^0-9a-f]*' AND typeof(t.\"step\")='integer' AND t.\"step\" >= 1) THEN 0 "
        "ELSE 1 END),0) AS graph_invalid_rows, "
        'coalesce(max((coalesce(length(CAST(t."run_id" AS '
        'BLOB)),0)+coalesce(length(CAST(t."step" AS '
        'BLOB)),0)+coalesce(length(CAST(t."artifact" AS '
        'BLOB)),0)+coalesce(length(CAST(t."hash" AS BLOB)),0))),0) AS '
        'max_original_native_bytes, coalesce(sum((coalesce(length(CAST(t."run_id"'
        ' AS BLOB)),0)+coalesce(length(CAST(t."step" AS '
        'BLOB)),0)+coalesce(length(CAST(t."artifact" AS '
        'BLOB)),0)+coalesce(length(CAST(t."hash" AS BLOB)),0))),0) AS '
        'original_native_bytes FROM "events" AS t\n'
    ),
    ("all", "sqlite", "source_count_jobs"): "".join((_SQLITE_ALL_SOURCE_COUNT_JOBS_PROJECTION,)),
    ("all", "sqlite", "source_stats_jobs"): (
        "SELECT count(*) AS observed_rows, coalesce(sum(CASE WHEN "
        '(typeof(t."id")=\'text\' AND length(t."id")=32 AND length(CAST(t."id" AS '
        'BLOB))=32 AND t."id" NOT GLOB \'*[^0-9a-f]*\' AND t."kind" IN '
        "('run','branch','study','investigate')) THEN 0 ELSE 1 END),0) AS "
        'graph_invalid_rows, coalesce(max((coalesce(length(CAST(t."id" AS '
        'BLOB)),0)+coalesce(length(CAST(t."kind" AS '
        'BLOB)),0)+coalesce(length(CAST(t."created" AS '
        'BLOB)),0)+coalesce(length(CAST(t."payload" AS '
        'BLOB)),0)+coalesce(length(CAST(t."status" AS '
        'BLOB)),0)+coalesce(length(CAST(t."owner" AS '
        'BLOB)),0)+coalesce(length(CAST(t."lease_until" AS '
        'BLOB)),0)+coalesce(length(CAST(t."cancel" AS '
        'BLOB)),0)+coalesce(length(CAST(t."budget" AS '
        'BLOB)),0)+coalesce(length(CAST(t."reserved" AS '
        'BLOB)),0)+coalesce(length(CAST(t."result" AS '
        'BLOB)),0)+coalesce(length(CAST(t."error" AS '
        'BLOB)),0)+coalesce(length(CAST(t."actor" AS BLOB)),0))),0) AS '
        'max_original_native_bytes, coalesce(sum((coalesce(length(CAST(t."id" AS '
        'BLOB)),0)+coalesce(length(CAST(t."kind" AS '
        'BLOB)),0)+coalesce(length(CAST(t."created" AS '
        'BLOB)),0)+coalesce(length(CAST(t."payload" AS '
        'BLOB)),0)+coalesce(length(CAST(t."status" AS '
        'BLOB)),0)+coalesce(length(CAST(t."owner" AS '
        'BLOB)),0)+coalesce(length(CAST(t."lease_until" AS '
        'BLOB)),0)+coalesce(length(CAST(t."cancel" AS '
        'BLOB)),0)+coalesce(length(CAST(t."budget" AS '
        'BLOB)),0)+coalesce(length(CAST(t."reserved" AS '
        'BLOB)),0)+coalesce(length(CAST(t."result" AS '
        'BLOB)),0)+coalesce(length(CAST(t."error" AS '
        'BLOB)),0)+coalesce(length(CAST(t."actor" AS BLOB)),0))),0) AS '
        'original_native_bytes FROM "jobs" AS t\n'
    ),
    ("all", "sqlite", "source_count_records"): "".join(
        (_SQLITE_ALL_SOURCE_COUNT_RECORDS_PROJECTION,)
    ),
    ("all", "sqlite", "source_stats_records"): (
        "SELECT count(*) AS observed_rows, coalesce(sum(CASE WHEN "
        '(typeof(t."id")=\'text\' AND length(t."id")=32 AND length(CAST(t."id" AS '
        'BLOB))=32 AND t."id" NOT GLOB \'*[^0-9a-f]*\' AND t."kind" IN '
        "('run','study')) THEN 0 ELSE 1 END),0) AS graph_invalid_rows, "
        'coalesce(max((coalesce(length(CAST(t."id" AS '
        'BLOB)),0)+coalesce(length(CAST(t."kind" AS '
        'BLOB)),0)+coalesce(length(CAST(t."created" AS '
        'BLOB)),0)+coalesce(length(CAST(t."data" AS BLOB)),0))),0) AS '
        'max_original_native_bytes, coalesce(sum((coalesce(length(CAST(t."id" AS '
        'BLOB)),0)+coalesce(length(CAST(t."kind" AS '
        'BLOB)),0)+coalesce(length(CAST(t."created" AS '
        'BLOB)),0)+coalesce(length(CAST(t."data" AS BLOB)),0))),0) AS '
        'original_native_bytes FROM "records" AS t\n'
    ),
    ("all", "sqlite", "graph_page_gate_jobs_first"): "".join(
        (
            (
                "WITH candidate AS MATERIALIZED (SELECT "
                't."id",(coalesce(length(CAST(t."id" AS '
                'BLOB)),0)+coalesce(length(CAST(t."kind" AS '
                'BLOB)),0)+coalesce(length(CAST(t."created" AS '
                'BLOB)),0)+coalesce(length(CAST(t."payload" AS '
                'BLOB)),0)+coalesce(length(CAST(t."status" AS '
                'BLOB)),0)+coalesce(length(CAST(t."owner" AS '
                'BLOB)),0)+coalesce(length(CAST(t."lease_until" AS '
                'BLOB)),0)+coalesce(length(CAST(t."cancel" AS '
                'BLOB)),0)+coalesce(length(CAST(t."budget" AS '
                'BLOB)),0)+coalesce(length(CAST(t."reserved" AS '
                'BLOB)),0)+coalesce(length(CAST(t."result" AS '
                'BLOB)),0)+coalesce(length(CAST(t."error" AS '
                'BLOB)),0)+coalesce(length(CAST(t."actor" AS BLOB)),0)) AS '
                "native_bytes, CASE WHEN"
            ),
            _SQLITE_ALL_GRAPH_PAGE_GATE_JOBS_FIRST_VALID,
            (
                'THEN 0 ELSE 1 END AS invalid FROM "jobs" AS t LEFT JOIN '
                "resource_scopes AS s ON s.resource_kind='job' AND "
                "s.resource_id=t.id LEFT JOIN projects AS p ON p.id=s.project_id "
                'ORDER BY t."id" LIMIT 4096)'
            ),
            _SQLITE_ALL_GRAPH_PAGE_GATE_JOBS_FIRST_RANKED,
            _SQLITE_ALL_GRAPH_PAGE_GATE_JOBS_FIRST_PROJECTION,
        )
    ),
    ("all", "sqlite", "graph_page_body_jobs_first"): "".join(
        (
            ("SELECT CASE WHEN"),
            _SQLITE_ALL_GRAPH_PAGE_GATE_JOBS_FIRST_VALID,
            ('THEN t."id" END AS "id",CASE WHEN'),
            _SQLITE_ALL_GRAPH_PAGE_GATE_JOBS_FIRST_VALID,
            ('THEN t."kind" END AS "kind",CASE WHEN'),
            _SQLITE_ALL_GRAPH_PAGE_GATE_JOBS_FIRST_VALID,
            ("THEN s.project_id END AS scope_project_id,CASE WHEN"),
            _SQLITE_ALL_GRAPH_PAGE_GATE_JOBS_FIRST_VALID,
            (
                'THEN 0 ELSE 1 END AS invalid FROM "jobs" AS t LEFT JOIN '
                "resource_scopes AS s ON s.resource_kind='job' AND "
                "s.resource_id=t.id LEFT JOIN projects AS p ON p.id=s.project_id "
                'WHERE t."id" <= :through_id ORDER BY t."id" LIMIT 4097\n'
            ),
        )
    ),
    ("all", "sqlite", "graph_page_gate_jobs_next"): "".join(
        (
            (
                "WITH candidate AS MATERIALIZED (SELECT "
                't."id",(coalesce(length(CAST(t."id" AS '
                'BLOB)),0)+coalesce(length(CAST(t."kind" AS '
                'BLOB)),0)+coalesce(length(CAST(t."created" AS '
                'BLOB)),0)+coalesce(length(CAST(t."payload" AS '
                'BLOB)),0)+coalesce(length(CAST(t."status" AS '
                'BLOB)),0)+coalesce(length(CAST(t."owner" AS '
                'BLOB)),0)+coalesce(length(CAST(t."lease_until" AS '
                'BLOB)),0)+coalesce(length(CAST(t."cancel" AS '
                'BLOB)),0)+coalesce(length(CAST(t."budget" AS '
                'BLOB)),0)+coalesce(length(CAST(t."reserved" AS '
                'BLOB)),0)+coalesce(length(CAST(t."result" AS '
                'BLOB)),0)+coalesce(length(CAST(t."error" AS '
                'BLOB)),0)+coalesce(length(CAST(t."actor" AS BLOB)),0)) AS '
                "native_bytes, CASE WHEN"
            ),
            _SQLITE_ALL_GRAPH_PAGE_GATE_JOBS_FIRST_VALID,
            (
                'THEN 0 ELSE 1 END AS invalid FROM "jobs" AS t LEFT JOIN '
                "resource_scopes AS s ON s.resource_kind='job' AND "
                "s.resource_id=t.id LEFT JOIN projects AS p ON p.id=s.project_id "
                'WHERE t."id" > :after_id ORDER BY t."id" LIMIT 4096)'
            ),
            _SQLITE_ALL_GRAPH_PAGE_GATE_JOBS_FIRST_RANKED,
            _SQLITE_ALL_GRAPH_PAGE_GATE_JOBS_FIRST_PROJECTION,
        )
    ),
    ("all", "sqlite", "graph_page_body_jobs_next"): "".join(
        (
            ("SELECT CASE WHEN"),
            _SQLITE_ALL_GRAPH_PAGE_GATE_JOBS_FIRST_VALID,
            ('THEN t."id" END AS "id",CASE WHEN'),
            _SQLITE_ALL_GRAPH_PAGE_GATE_JOBS_FIRST_VALID,
            ('THEN t."kind" END AS "kind",CASE WHEN'),
            _SQLITE_ALL_GRAPH_PAGE_GATE_JOBS_FIRST_VALID,
            ("THEN s.project_id END AS scope_project_id,CASE WHEN"),
            _SQLITE_ALL_GRAPH_PAGE_GATE_JOBS_FIRST_VALID,
            (
                'THEN 0 ELSE 1 END AS invalid FROM "jobs" AS t LEFT JOIN '
                "resource_scopes AS s ON s.resource_kind='job' AND "
                "s.resource_id=t.id LEFT JOIN projects AS p ON p.id=s.project_id "
                'WHERE t."id" > :after_id AND t."id" <= :through_id ORDER BY t."id" '
                "LIMIT 4097\n"
            ),
        )
    ),
    ("all", "sqlite", "graph_page_gate_api_keys_first"): "".join(
        (
            (
                "WITH candidate AS MATERIALIZED (SELECT "
                't."id",(coalesce(length(CAST(t."id" AS '
                'BLOB)),0)+coalesce(length(CAST(t."hash" AS '
                'BLOB)),0)+coalesce(length(CAST(t."role" AS '
                'BLOB)),0)+coalesce(length(CAST(t."name" AS '
                'BLOB)),0)+coalesce(length(CAST(t."expires" AS '
                'BLOB)),0)+coalesce(length(CAST(t."revoked" AS BLOB)),0)) AS '
                "native_bytes, CASE WHEN"
            ),
            _SQLITE_ALL_GRAPH_PAGE_GATE_API_KEYS_FIRST_VALID,
            (
                'THEN 0 ELSE 1 END AS invalid FROM "api_keys" AS t LEFT JOIN '
                "resource_scopes AS s ON s.resource_kind='key' AND "
                "s.resource_id=t.id LEFT JOIN projects AS p ON p.id=s.project_id "
                'ORDER BY t."id" LIMIT 4096)'
            ),
            _SQLITE_ALL_GRAPH_PAGE_GATE_JOBS_FIRST_RANKED,
            _SQLITE_ALL_GRAPH_PAGE_GATE_JOBS_FIRST_PROJECTION,
        )
    ),
    ("all", "sqlite", "graph_page_body_api_keys_first"): "".join(
        (
            ("SELECT CASE WHEN"),
            _SQLITE_ALL_GRAPH_PAGE_GATE_API_KEYS_FIRST_VALID,
            ('THEN t."id" END AS "id",CASE WHEN'),
            _SQLITE_ALL_GRAPH_PAGE_GATE_API_KEYS_FIRST_VALID,
            ('THEN t."revoked" END AS "revoked",CASE WHEN'),
            _SQLITE_ALL_GRAPH_PAGE_GATE_API_KEYS_FIRST_VALID,
            ('THEN t."expires" END AS "expires",CASE WHEN'),
            _SQLITE_ALL_GRAPH_PAGE_GATE_API_KEYS_FIRST_VALID,
            ("THEN s.project_id END AS scope_project_id,CASE WHEN"),
            _SQLITE_ALL_GRAPH_PAGE_GATE_API_KEYS_FIRST_VALID,
            (
                'THEN 0 ELSE 1 END AS invalid FROM "api_keys" AS t LEFT JOIN '
                "resource_scopes AS s ON s.resource_kind='key' AND "
                "s.resource_id=t.id LEFT JOIN projects AS p ON p.id=s.project_id "
                'WHERE t."id" <= :through_id ORDER BY t."id" LIMIT 4097\n'
            ),
        )
    ),
    ("all", "sqlite", "graph_page_gate_api_keys_next"): "".join(
        (
            (
                "WITH candidate AS MATERIALIZED (SELECT "
                't."id",(coalesce(length(CAST(t."id" AS '
                'BLOB)),0)+coalesce(length(CAST(t."hash" AS '
                'BLOB)),0)+coalesce(length(CAST(t."role" AS '
                'BLOB)),0)+coalesce(length(CAST(t."name" AS '
                'BLOB)),0)+coalesce(length(CAST(t."expires" AS '
                'BLOB)),0)+coalesce(length(CAST(t."revoked" AS BLOB)),0)) AS '
                "native_bytes, CASE WHEN"
            ),
            _SQLITE_ALL_GRAPH_PAGE_GATE_API_KEYS_FIRST_VALID,
            (
                'THEN 0 ELSE 1 END AS invalid FROM "api_keys" AS t LEFT JOIN '
                "resource_scopes AS s ON s.resource_kind='key' AND "
                "s.resource_id=t.id LEFT JOIN projects AS p ON p.id=s.project_id "
                'WHERE t."id" > :after_id ORDER BY t."id" LIMIT 4096)'
            ),
            _SQLITE_ALL_GRAPH_PAGE_GATE_JOBS_FIRST_RANKED,
            _SQLITE_ALL_GRAPH_PAGE_GATE_JOBS_FIRST_PROJECTION,
        )
    ),
    ("all", "sqlite", "graph_page_body_api_keys_next"): "".join(
        (
            ("SELECT CASE WHEN"),
            _SQLITE_ALL_GRAPH_PAGE_GATE_API_KEYS_FIRST_VALID,
            ('THEN t."id" END AS "id",CASE WHEN'),
            _SQLITE_ALL_GRAPH_PAGE_GATE_API_KEYS_FIRST_VALID,
            ('THEN t."revoked" END AS "revoked",CASE WHEN'),
            _SQLITE_ALL_GRAPH_PAGE_GATE_API_KEYS_FIRST_VALID,
            ('THEN t."expires" END AS "expires",CASE WHEN'),
            _SQLITE_ALL_GRAPH_PAGE_GATE_API_KEYS_FIRST_VALID,
            ("THEN s.project_id END AS scope_project_id,CASE WHEN"),
            _SQLITE_ALL_GRAPH_PAGE_GATE_API_KEYS_FIRST_VALID,
            (
                'THEN 0 ELSE 1 END AS invalid FROM "api_keys" AS t LEFT JOIN '
                "resource_scopes AS s ON s.resource_kind='key' AND "
                "s.resource_id=t.id LEFT JOIN projects AS p ON p.id=s.project_id "
                'WHERE t."id" > :after_id AND t."id" <= :through_id ORDER BY t."id" '
                "LIMIT 4097\n"
            ),
        )
    ),
    ("all", "sqlite", "graph_page_gate_records_first"): "".join(
        (
            (
                "WITH candidate AS MATERIALIZED (SELECT "
                't."id",(coalesce(length(CAST(t."id" AS '
                'BLOB)),0)+coalesce(length(CAST(t."kind" AS '
                'BLOB)),0)+coalesce(length(CAST(t."created" AS '
                'BLOB)),0)+coalesce(length(CAST(t."data" AS BLOB)),0)) AS '
                "native_bytes, CASE WHEN"
            ),
            _SQLITE_ALL_GRAPH_PAGE_GATE_RECORDS_FIRST_VALID,
            (
                'THEN 0 ELSE 1 END AS invalid FROM "records" AS t LEFT JOIN '
                'resource_scopes AS s ON s.resource_kind=t."kind" AND '
                "s.resource_id=t.id LEFT JOIN projects AS p ON p.id=s.project_id "
                'ORDER BY t."id" LIMIT 4096)'
            ),
            _SQLITE_ALL_GRAPH_PAGE_GATE_JOBS_FIRST_RANKED,
            _SQLITE_ALL_GRAPH_PAGE_GATE_JOBS_FIRST_PROJECTION,
        )
    ),
    ("all", "sqlite", "graph_page_body_records_first"): "".join(
        (
            ("SELECT CASE WHEN"),
            _SQLITE_ALL_GRAPH_PAGE_GATE_RECORDS_FIRST_VALID,
            ('THEN t."id" END AS "id",CASE WHEN'),
            _SQLITE_ALL_GRAPH_PAGE_GATE_RECORDS_FIRST_VALID,
            ('THEN t."kind" END AS "kind",CASE WHEN'),
            _SQLITE_ALL_GRAPH_PAGE_GATE_RECORDS_FIRST_VALID,
            ('THEN CAST(t."data" AS TEXT) END AS "data",CASE WHEN'),
            _SQLITE_ALL_GRAPH_PAGE_GATE_RECORDS_FIRST_VALID,
            ("THEN s.project_id END AS scope_project_id,CASE WHEN"),
            _SQLITE_ALL_GRAPH_PAGE_GATE_RECORDS_FIRST_VALID,
            (
                'THEN 0 ELSE 1 END AS invalid FROM "records" AS t LEFT JOIN '
                'resource_scopes AS s ON s.resource_kind=t."kind" AND '
                "s.resource_id=t.id LEFT JOIN projects AS p ON p.id=s.project_id "
                'WHERE t."id" <= :through_id ORDER BY t."id" LIMIT 4097\n'
            ),
        )
    ),
    ("all", "sqlite", "graph_page_gate_records_next"): "".join(
        (
            (
                "WITH candidate AS MATERIALIZED (SELECT "
                't."id",(coalesce(length(CAST(t."id" AS '
                'BLOB)),0)+coalesce(length(CAST(t."kind" AS '
                'BLOB)),0)+coalesce(length(CAST(t."created" AS '
                'BLOB)),0)+coalesce(length(CAST(t."data" AS BLOB)),0)) AS '
                "native_bytes, CASE WHEN"
            ),
            _SQLITE_ALL_GRAPH_PAGE_GATE_RECORDS_FIRST_VALID,
            (
                'THEN 0 ELSE 1 END AS invalid FROM "records" AS t LEFT JOIN '
                'resource_scopes AS s ON s.resource_kind=t."kind" AND '
                "s.resource_id=t.id LEFT JOIN projects AS p ON p.id=s.project_id "
                'WHERE t."id" > :after_id ORDER BY t."id" LIMIT 4096)'
            ),
            _SQLITE_ALL_GRAPH_PAGE_GATE_JOBS_FIRST_RANKED,
            _SQLITE_ALL_GRAPH_PAGE_GATE_JOBS_FIRST_PROJECTION,
        )
    ),
    ("all", "sqlite", "graph_page_body_records_next"): "".join(
        (
            ("SELECT CASE WHEN"),
            _SQLITE_ALL_GRAPH_PAGE_GATE_RECORDS_FIRST_VALID,
            ('THEN t."id" END AS "id",CASE WHEN'),
            _SQLITE_ALL_GRAPH_PAGE_GATE_RECORDS_FIRST_VALID,
            ('THEN t."kind" END AS "kind",CASE WHEN'),
            _SQLITE_ALL_GRAPH_PAGE_GATE_RECORDS_FIRST_VALID,
            ('THEN CAST(t."data" AS TEXT) END AS "data",CASE WHEN'),
            _SQLITE_ALL_GRAPH_PAGE_GATE_RECORDS_FIRST_VALID,
            ("THEN s.project_id END AS scope_project_id,CASE WHEN"),
            _SQLITE_ALL_GRAPH_PAGE_GATE_RECORDS_FIRST_VALID,
            (
                'THEN 0 ELSE 1 END AS invalid FROM "records" AS t LEFT JOIN '
                'resource_scopes AS s ON s.resource_kind=t."kind" AND '
                "s.resource_id=t.id LEFT JOIN projects AS p ON p.id=s.project_id "
                'WHERE t."id" > :after_id AND t."id" <= :through_id ORDER BY t."id" '
                "LIMIT 4097\n"
            ),
        )
    ),
    ("all", "sqlite", "graph_page_gate_events_first"): "".join(
        (
            (
                "WITH candidate AS MATERIALIZED (SELECT "
                't."run_id",t."step",(coalesce(length(CAST(t."run_id" AS '
                'BLOB)),0)+coalesce(length(CAST(t."step" AS '
                'BLOB)),0)+coalesce(length(CAST(t."artifact" AS '
                'BLOB)),0)+coalesce(length(CAST(t."hash" AS BLOB)),0)) AS '
                "native_bytes, CASE WHEN"
            ),
            _SQLITE_ALL_GRAPH_PAGE_GATE_EVENTS_FIRST_VALID,
            (
                'THEN 0 ELSE 1 END AS invalid FROM "events" AS t ORDER BY '
                't."run_id",t."step" LIMIT 4096)'
            ),
            _SQLITE_ALL_GRAPH_PAGE_GATE_EVENTS_FIRST_RANKED,
            _SQLITE_ALL_GRAPH_PAGE_GATE_EVENTS_FIRST_PROJECTION,
        )
    ),
    ("all", "sqlite", "graph_page_body_events_first"): "".join(
        (
            ("SELECT CASE WHEN"),
            _SQLITE_ALL_GRAPH_PAGE_GATE_EVENTS_FIRST_VALID,
            ('THEN t."run_id" END AS "run_id",CASE WHEN'),
            _SQLITE_ALL_GRAPH_PAGE_GATE_EVENTS_FIRST_VALID,
            ('THEN t."step" END AS "step",CASE WHEN'),
            _SQLITE_ALL_GRAPH_PAGE_GATE_EVENTS_FIRST_VALID,
            (
                'THEN 0 ELSE 1 END AS invalid FROM "events" AS t WHERE '
                '(t."run_id",t."step") <= (:through_run_id,:through_step) ORDER BY '
                't."run_id",t."step" LIMIT 4097\n'
            ),
        )
    ),
    ("all", "sqlite", "graph_page_gate_events_next"): "".join(
        (
            (
                "WITH candidate AS MATERIALIZED (SELECT "
                't."run_id",t."step",(coalesce(length(CAST(t."run_id" AS '
                'BLOB)),0)+coalesce(length(CAST(t."step" AS '
                'BLOB)),0)+coalesce(length(CAST(t."artifact" AS '
                'BLOB)),0)+coalesce(length(CAST(t."hash" AS BLOB)),0)) AS '
                "native_bytes, CASE WHEN"
            ),
            _SQLITE_ALL_GRAPH_PAGE_GATE_EVENTS_FIRST_VALID,
            (
                'THEN 0 ELSE 1 END AS invalid FROM "events" AS t WHERE '
                '(t."run_id",t."step") > (:after_run_id,:after_step) ORDER BY '
                't."run_id",t."step" LIMIT 4096)'
            ),
            _SQLITE_ALL_GRAPH_PAGE_GATE_EVENTS_FIRST_RANKED,
            _SQLITE_ALL_GRAPH_PAGE_GATE_EVENTS_FIRST_PROJECTION,
        )
    ),
    ("all", "sqlite", "graph_page_body_events_next"): "".join(
        (
            ("SELECT CASE WHEN"),
            _SQLITE_ALL_GRAPH_PAGE_GATE_EVENTS_FIRST_VALID,
            ('THEN t."run_id" END AS "run_id",CASE WHEN'),
            _SQLITE_ALL_GRAPH_PAGE_GATE_EVENTS_FIRST_VALID,
            ('THEN t."step" END AS "step",CASE WHEN'),
            _SQLITE_ALL_GRAPH_PAGE_GATE_EVENTS_FIRST_VALID,
            (
                'THEN 0 ELSE 1 END AS invalid FROM "events" AS t WHERE '
                '(t."run_id",t."step") > (:after_run_id,:after_step) AND '
                '(t."run_id",t."step") <= (:through_run_id,:through_step) ORDER BY '
                't."run_id",t."step" LIMIT 4097\n'
            ),
        )
    ),
    ("all", "postgresql", "source_count_api_keys"): "".join(
        (_SQLITE_ALL_SOURCE_COUNT_API_KEYS_PROJECTION,)
    ),
    ("all", "postgresql", "source_stats_api_keys"): (
        "SELECT count(*) AS observed_rows, coalesce(sum(CASE WHEN "
        '(octet_length(t."id")=32 AND t."id" ~ \'^[0-9a-f]{32}$\' AND (t."revoked" '
        'IS NULL OR t."revoked" IN (FALSE,TRUE)) AND t."expires" IS NOT NULL AND '
        "t.\"expires\" NOT IN ('NaN'::double precision,'Infinity'::double "
        "precision,'-Infinity'::double precision)) THEN 0 ELSE 1 END),0) AS "
        'graph_invalid_rows, coalesce(max((coalesce(octet_length(CAST(t."id" AS '
        'TEXT)),0)+coalesce(octet_length(CAST(t."hash" AS '
        'TEXT)),0)+coalesce(octet_length(CAST(t."role" AS '
        'TEXT)),0)+coalesce(octet_length(CAST(t."name" AS '
        'TEXT)),0)+coalesce(octet_length(CAST(t."expires" AS '
        'TEXT)),0)+coalesce(octet_length(CAST(t."revoked" AS TEXT)),0))),0) AS '
        'max_original_native_bytes, coalesce(sum((coalesce(octet_length(CAST(t."i'
        'd" AS TEXT)),0)+coalesce(octet_length(CAST(t."hash" AS '
        'TEXT)),0)+coalesce(octet_length(CAST(t."role" AS '
        'TEXT)),0)+coalesce(octet_length(CAST(t."name" AS '
        'TEXT)),0)+coalesce(octet_length(CAST(t."expires" AS '
        'TEXT)),0)+coalesce(octet_length(CAST(t."revoked" AS TEXT)),0))),0) AS '
        'original_native_bytes FROM "api_keys" AS t\n'
    ),
    ("all", "postgresql", "source_count_audit"): "".join(
        (_SQLITE_ALL_SOURCE_COUNT_AUDIT_PROJECTION,)
    ),
    ("all", "postgresql", "source_stats_audit"): (
        "SELECT count(*) AS observed_rows, coalesce(sum(CASE WHEN (1=1) THEN 0 "
        "ELSE 1 END),0) AS graph_invalid_rows, "
        'coalesce(max((coalesce(octet_length(CAST(t."id" AS '
        'TEXT)),0)+coalesce(octet_length(CAST(t."created" AS '
        'TEXT)),0)+coalesce(octet_length(CAST(t."actor" AS '
        'TEXT)),0)+coalesce(octet_length(CAST(t."action" AS '
        'TEXT)),0)+coalesce(octet_length(CAST(t."target" AS TEXT)),0))),0) AS '
        'max_original_native_bytes, coalesce(sum((coalesce(octet_length(CAST(t."i'
        'd" AS TEXT)),0)+coalesce(octet_length(CAST(t."created" AS '
        'TEXT)),0)+coalesce(octet_length(CAST(t."actor" AS '
        'TEXT)),0)+coalesce(octet_length(CAST(t."action" AS '
        'TEXT)),0)+coalesce(octet_length(CAST(t."target" AS TEXT)),0))),0) AS '
        'original_native_bytes FROM "audit" AS t\n'
    ),
    ("all", "postgresql", "source_count_events"): "".join(
        (_SQLITE_ALL_SOURCE_COUNT_EVENTS_PROJECTION,)
    ),
    ("all", "postgresql", "source_stats_events"): (
        "SELECT count(*) AS observed_rows, coalesce(sum(CASE WHEN "
        '(octet_length(t."run_id")=32 AND t."run_id" ~ \'^[0-9a-f]{32}$\' AND '
        't."step" IS NOT NULL AND t."step" >= 1) THEN 0 ELSE 1 END),0) AS '
        'graph_invalid_rows, coalesce(max((coalesce(octet_length(CAST(t."run_id" '
        'AS TEXT)),0)+coalesce(octet_length(CAST(t."step" AS '
        'TEXT)),0)+coalesce(octet_length(CAST(t."artifact" AS '
        'TEXT)),0)+coalesce(octet_length(CAST(t."hash" AS TEXT)),0))),0) AS '
        'max_original_native_bytes, coalesce(sum((coalesce(octet_length(CAST(t."r'
        'un_id" AS TEXT)),0)+coalesce(octet_length(CAST(t."step" AS '
        'TEXT)),0)+coalesce(octet_length(CAST(t."artifact" AS '
        'TEXT)),0)+coalesce(octet_length(CAST(t."hash" AS TEXT)),0))),0) AS '
        'original_native_bytes FROM "events" AS t\n'
    ),
    ("all", "postgresql", "source_count_jobs"): "".join(
        (_SQLITE_ALL_SOURCE_COUNT_JOBS_PROJECTION,)
    ),
    ("all", "postgresql", "source_stats_jobs"): (
        "SELECT count(*) AS observed_rows, coalesce(sum(CASE WHEN "
        '(octet_length(t."id")=32 AND t."id" ~ \'^[0-9a-f]{32}$\' AND t."kind" IN '
        "('run','branch','study','investigate')) THEN 0 ELSE 1 END),0) AS "
        'graph_invalid_rows, coalesce(max((coalesce(octet_length(CAST(t."id" AS '
        'TEXT)),0)+coalesce(octet_length(CAST(t."kind" AS '
        'TEXT)),0)+coalesce(octet_length(CAST(t."created" AS '
        'TEXT)),0)+coalesce(octet_length(CAST(t."payload" AS '
        'TEXT)),0)+coalesce(octet_length(CAST(t."status" AS '
        'TEXT)),0)+coalesce(octet_length(CAST(t."owner" AS '
        'TEXT)),0)+coalesce(octet_length(CAST(t."lease_until" AS '
        'TEXT)),0)+coalesce(octet_length(CAST(t."cancel" AS '
        'TEXT)),0)+coalesce(octet_length(CAST(t."budget" AS '
        'TEXT)),0)+coalesce(octet_length(CAST(t."reserved" AS '
        'TEXT)),0)+coalesce(octet_length(CAST(t."result" AS '
        'TEXT)),0)+coalesce(octet_length(CAST(t."error" AS '
        'TEXT)),0)+coalesce(octet_length(CAST(t."actor" AS TEXT)),0))),0) AS '
        'max_original_native_bytes, coalesce(sum((coalesce(octet_length(CAST(t."i'
        'd" AS TEXT)),0)+coalesce(octet_length(CAST(t."kind" AS '
        'TEXT)),0)+coalesce(octet_length(CAST(t."created" AS '
        'TEXT)),0)+coalesce(octet_length(CAST(t."payload" AS '
        'TEXT)),0)+coalesce(octet_length(CAST(t."status" AS '
        'TEXT)),0)+coalesce(octet_length(CAST(t."owner" AS '
        'TEXT)),0)+coalesce(octet_length(CAST(t."lease_until" AS '
        'TEXT)),0)+coalesce(octet_length(CAST(t."cancel" AS '
        'TEXT)),0)+coalesce(octet_length(CAST(t."budget" AS '
        'TEXT)),0)+coalesce(octet_length(CAST(t."reserved" AS '
        'TEXT)),0)+coalesce(octet_length(CAST(t."result" AS '
        'TEXT)),0)+coalesce(octet_length(CAST(t."error" AS '
        'TEXT)),0)+coalesce(octet_length(CAST(t."actor" AS TEXT)),0))),0) AS '
        'original_native_bytes FROM "jobs" AS t\n'
    ),
    ("all", "postgresql", "source_count_records"): "".join(
        (_SQLITE_ALL_SOURCE_COUNT_RECORDS_PROJECTION,)
    ),
    ("all", "postgresql", "source_stats_records"): (
        "SELECT count(*) AS observed_rows, coalesce(sum(CASE WHEN "
        '(octet_length(t."id")=32 AND t."id" ~ \'^[0-9a-f]{32}$\' AND t."kind" IN '
        "('run','study')) THEN 0 ELSE 1 END),0) AS graph_invalid_rows, "
        'coalesce(max((coalesce(octet_length(CAST(t."id" AS '
        'TEXT)),0)+coalesce(octet_length(CAST(t."kind" AS '
        'TEXT)),0)+coalesce(octet_length(CAST(t."created" AS '
        'TEXT)),0)+coalesce(octet_length(CAST(t."data" AS TEXT)),0))),0) AS '
        'max_original_native_bytes, coalesce(sum((coalesce(octet_length(CAST(t."i'
        'd" AS TEXT)),0)+coalesce(octet_length(CAST(t."kind" AS '
        'TEXT)),0)+coalesce(octet_length(CAST(t."created" AS '
        'TEXT)),0)+coalesce(octet_length(CAST(t."data" AS TEXT)),0))),0) AS '
        'original_native_bytes FROM "records" AS t\n'
    ),
    ("all", "postgresql", "graph_page_gate_jobs_first"): "".join(
        (
            (
                "WITH candidate AS MATERIALIZED (SELECT "
                't."id",(coalesce(octet_length(CAST(t."id" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(t."kind" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(t."created" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(t."payload" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(t."status" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(t."owner" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(t."lease_until" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(t."cancel" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(t."budget" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(t."reserved" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(t."result" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(t."error" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(t."actor" AS TEXT)),0)) AS '
                "native_bytes, CASE WHEN"
            ),
            _POSTGRESQL_ALL_GRAPH_PAGE_GATE_JOBS_FIRST_VALID,
            (
                'THEN 0 ELSE 1 END AS invalid FROM "jobs" AS t LEFT JOIN '
                "resource_scopes AS s ON s.resource_kind='job' AND "
                "s.resource_id=t.id LEFT JOIN projects AS p ON p.id=s.project_id "
                'ORDER BY t."id" LIMIT 4096)'
            ),
            _SQLITE_ALL_GRAPH_PAGE_GATE_JOBS_FIRST_RANKED,
            _SQLITE_ALL_GRAPH_PAGE_GATE_JOBS_FIRST_PROJECTION,
        )
    ),
    ("all", "postgresql", "graph_page_body_jobs_first"): "".join(
        (
            ("SELECT CASE WHEN"),
            _POSTGRESQL_ALL_GRAPH_PAGE_GATE_JOBS_FIRST_VALID,
            ('THEN t."id" END AS "id",CASE WHEN'),
            _POSTGRESQL_ALL_GRAPH_PAGE_GATE_JOBS_FIRST_VALID,
            ('THEN t."kind" END AS "kind",CASE WHEN'),
            _POSTGRESQL_ALL_GRAPH_PAGE_GATE_JOBS_FIRST_VALID,
            ("THEN s.project_id END AS scope_project_id,CASE WHEN"),
            _POSTGRESQL_ALL_GRAPH_PAGE_GATE_JOBS_FIRST_VALID,
            (
                'THEN 0 ELSE 1 END AS invalid FROM "jobs" AS t LEFT JOIN '
                "resource_scopes AS s ON s.resource_kind='job' AND "
                "s.resource_id=t.id LEFT JOIN projects AS p ON p.id=s.project_id "
                'WHERE t."id" <= :through_id ORDER BY t."id" LIMIT 4097\n'
            ),
        )
    ),
    ("all", "postgresql", "graph_page_gate_jobs_next"): "".join(
        (
            (
                "WITH candidate AS MATERIALIZED (SELECT "
                't."id",(coalesce(octet_length(CAST(t."id" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(t."kind" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(t."created" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(t."payload" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(t."status" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(t."owner" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(t."lease_until" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(t."cancel" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(t."budget" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(t."reserved" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(t."result" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(t."error" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(t."actor" AS TEXT)),0)) AS '
                "native_bytes, CASE WHEN"
            ),
            _POSTGRESQL_ALL_GRAPH_PAGE_GATE_JOBS_FIRST_VALID,
            (
                'THEN 0 ELSE 1 END AS invalid FROM "jobs" AS t LEFT JOIN '
                "resource_scopes AS s ON s.resource_kind='job' AND "
                "s.resource_id=t.id LEFT JOIN projects AS p ON p.id=s.project_id "
                'WHERE t."id" > :after_id ORDER BY t."id" LIMIT 4096)'
            ),
            _SQLITE_ALL_GRAPH_PAGE_GATE_JOBS_FIRST_RANKED,
            _SQLITE_ALL_GRAPH_PAGE_GATE_JOBS_FIRST_PROJECTION,
        )
    ),
    ("all", "postgresql", "graph_page_body_jobs_next"): "".join(
        (
            ("SELECT CASE WHEN"),
            _POSTGRESQL_ALL_GRAPH_PAGE_GATE_JOBS_FIRST_VALID,
            ('THEN t."id" END AS "id",CASE WHEN'),
            _POSTGRESQL_ALL_GRAPH_PAGE_GATE_JOBS_FIRST_VALID,
            ('THEN t."kind" END AS "kind",CASE WHEN'),
            _POSTGRESQL_ALL_GRAPH_PAGE_GATE_JOBS_FIRST_VALID,
            ("THEN s.project_id END AS scope_project_id,CASE WHEN"),
            _POSTGRESQL_ALL_GRAPH_PAGE_GATE_JOBS_FIRST_VALID,
            (
                'THEN 0 ELSE 1 END AS invalid FROM "jobs" AS t LEFT JOIN '
                "resource_scopes AS s ON s.resource_kind='job' AND "
                "s.resource_id=t.id LEFT JOIN projects AS p ON p.id=s.project_id "
                'WHERE t."id" > :after_id AND t."id" <= :through_id ORDER BY t."id" '
                "LIMIT 4097\n"
            ),
        )
    ),
    ("all", "postgresql", "graph_page_gate_api_keys_first"): "".join(
        (
            (
                "WITH candidate AS MATERIALIZED (SELECT "
                't."id",(coalesce(octet_length(CAST(t."id" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(t."hash" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(t."role" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(t."name" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(t."expires" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(t."revoked" AS TEXT)),0)) AS '
                "native_bytes, CASE WHEN"
            ),
            _POSTGRESQL_ALL_GRAPH_PAGE_GATE_API_KEYS_FIRST_VALID,
            (
                'THEN 0 ELSE 1 END AS invalid FROM "api_keys" AS t LEFT JOIN '
                "resource_scopes AS s ON s.resource_kind='key' AND "
                "s.resource_id=t.id LEFT JOIN projects AS p ON p.id=s.project_id "
                'ORDER BY t."id" LIMIT 4096)'
            ),
            _SQLITE_ALL_GRAPH_PAGE_GATE_JOBS_FIRST_RANKED,
            _SQLITE_ALL_GRAPH_PAGE_GATE_JOBS_FIRST_PROJECTION,
        )
    ),
    ("all", "postgresql", "graph_page_body_api_keys_first"): "".join(
        (
            ("SELECT CASE WHEN"),
            _POSTGRESQL_ALL_GRAPH_PAGE_GATE_API_KEYS_FIRST_VALID,
            ('THEN t."id" END AS "id",CASE WHEN'),
            _POSTGRESQL_ALL_GRAPH_PAGE_GATE_API_KEYS_FIRST_VALID,
            ('THEN t."revoked" END AS "revoked",CASE WHEN'),
            _POSTGRESQL_ALL_GRAPH_PAGE_GATE_API_KEYS_FIRST_VALID,
            ('THEN t."expires" END AS "expires",CASE WHEN'),
            _POSTGRESQL_ALL_GRAPH_PAGE_GATE_API_KEYS_FIRST_VALID,
            ("THEN s.project_id END AS scope_project_id,CASE WHEN"),
            _POSTGRESQL_ALL_GRAPH_PAGE_GATE_API_KEYS_FIRST_VALID,
            (
                'THEN 0 ELSE 1 END AS invalid FROM "api_keys" AS t LEFT JOIN '
                "resource_scopes AS s ON s.resource_kind='key' AND "
                "s.resource_id=t.id LEFT JOIN projects AS p ON p.id=s.project_id "
                'WHERE t."id" <= :through_id ORDER BY t."id" LIMIT 4097\n'
            ),
        )
    ),
    ("all", "postgresql", "graph_page_gate_api_keys_next"): "".join(
        (
            (
                "WITH candidate AS MATERIALIZED (SELECT "
                't."id",(coalesce(octet_length(CAST(t."id" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(t."hash" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(t."role" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(t."name" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(t."expires" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(t."revoked" AS TEXT)),0)) AS '
                "native_bytes, CASE WHEN"
            ),
            _POSTGRESQL_ALL_GRAPH_PAGE_GATE_API_KEYS_FIRST_VALID,
            (
                'THEN 0 ELSE 1 END AS invalid FROM "api_keys" AS t LEFT JOIN '
                "resource_scopes AS s ON s.resource_kind='key' AND "
                "s.resource_id=t.id LEFT JOIN projects AS p ON p.id=s.project_id "
                'WHERE t."id" > :after_id ORDER BY t."id" LIMIT 4096)'
            ),
            _SQLITE_ALL_GRAPH_PAGE_GATE_JOBS_FIRST_RANKED,
            _SQLITE_ALL_GRAPH_PAGE_GATE_JOBS_FIRST_PROJECTION,
        )
    ),
    ("all", "postgresql", "graph_page_body_api_keys_next"): "".join(
        (
            ("SELECT CASE WHEN"),
            _POSTGRESQL_ALL_GRAPH_PAGE_GATE_API_KEYS_FIRST_VALID,
            ('THEN t."id" END AS "id",CASE WHEN'),
            _POSTGRESQL_ALL_GRAPH_PAGE_GATE_API_KEYS_FIRST_VALID,
            ('THEN t."revoked" END AS "revoked",CASE WHEN'),
            _POSTGRESQL_ALL_GRAPH_PAGE_GATE_API_KEYS_FIRST_VALID,
            ('THEN t."expires" END AS "expires",CASE WHEN'),
            _POSTGRESQL_ALL_GRAPH_PAGE_GATE_API_KEYS_FIRST_VALID,
            ("THEN s.project_id END AS scope_project_id,CASE WHEN"),
            _POSTGRESQL_ALL_GRAPH_PAGE_GATE_API_KEYS_FIRST_VALID,
            (
                'THEN 0 ELSE 1 END AS invalid FROM "api_keys" AS t LEFT JOIN '
                "resource_scopes AS s ON s.resource_kind='key' AND "
                "s.resource_id=t.id LEFT JOIN projects AS p ON p.id=s.project_id "
                'WHERE t."id" > :after_id AND t."id" <= :through_id ORDER BY t."id" '
                "LIMIT 4097\n"
            ),
        )
    ),
    ("all", "postgresql", "graph_page_gate_records_first"): "".join(
        (
            (
                "WITH candidate AS MATERIALIZED (SELECT "
                't."id",(coalesce(octet_length(CAST(t."id" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(t."kind" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(t."created" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(t."data" AS TEXT)),0)) AS '
                "native_bytes, CASE WHEN"
            ),
            _POSTGRESQL_ALL_GRAPH_PAGE_GATE_RECORDS_FIRST_VALID,
            (
                'THEN 0 ELSE 1 END AS invalid FROM "records" AS t LEFT JOIN '
                'resource_scopes AS s ON s.resource_kind=t."kind" AND '
                "s.resource_id=t.id LEFT JOIN projects AS p ON p.id=s.project_id "
                'ORDER BY t."id" LIMIT 4096)'
            ),
            _SQLITE_ALL_GRAPH_PAGE_GATE_JOBS_FIRST_RANKED,
            _SQLITE_ALL_GRAPH_PAGE_GATE_JOBS_FIRST_PROJECTION,
        )
    ),
    ("all", "postgresql", "graph_page_body_records_first"): "".join(
        (
            ("SELECT CASE WHEN"),
            _POSTGRESQL_ALL_GRAPH_PAGE_GATE_RECORDS_FIRST_VALID,
            ('THEN t."id" END AS "id",CASE WHEN'),
            _POSTGRESQL_ALL_GRAPH_PAGE_GATE_RECORDS_FIRST_VALID,
            ('THEN t."kind" END AS "kind",CASE WHEN'),
            _POSTGRESQL_ALL_GRAPH_PAGE_GATE_RECORDS_FIRST_VALID,
            ('THEN CAST(t."data" AS TEXT) END AS "data",CASE WHEN'),
            _POSTGRESQL_ALL_GRAPH_PAGE_GATE_RECORDS_FIRST_VALID,
            ("THEN s.project_id END AS scope_project_id,CASE WHEN"),
            _POSTGRESQL_ALL_GRAPH_PAGE_GATE_RECORDS_FIRST_VALID,
            (
                'THEN 0 ELSE 1 END AS invalid FROM "records" AS t LEFT JOIN '
                'resource_scopes AS s ON s.resource_kind=t."kind" AND '
                "s.resource_id=t.id LEFT JOIN projects AS p ON p.id=s.project_id "
                'WHERE t."id" <= :through_id ORDER BY t."id" LIMIT 4097\n'
            ),
        )
    ),
    ("all", "postgresql", "graph_page_gate_records_next"): "".join(
        (
            (
                "WITH candidate AS MATERIALIZED (SELECT "
                't."id",(coalesce(octet_length(CAST(t."id" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(t."kind" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(t."created" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(t."data" AS TEXT)),0)) AS '
                "native_bytes, CASE WHEN"
            ),
            _POSTGRESQL_ALL_GRAPH_PAGE_GATE_RECORDS_FIRST_VALID,
            (
                'THEN 0 ELSE 1 END AS invalid FROM "records" AS t LEFT JOIN '
                'resource_scopes AS s ON s.resource_kind=t."kind" AND '
                "s.resource_id=t.id LEFT JOIN projects AS p ON p.id=s.project_id "
                'WHERE t."id" > :after_id ORDER BY t."id" LIMIT 4096)'
            ),
            _SQLITE_ALL_GRAPH_PAGE_GATE_JOBS_FIRST_RANKED,
            _SQLITE_ALL_GRAPH_PAGE_GATE_JOBS_FIRST_PROJECTION,
        )
    ),
    ("all", "postgresql", "graph_page_body_records_next"): "".join(
        (
            ("SELECT CASE WHEN"),
            _POSTGRESQL_ALL_GRAPH_PAGE_GATE_RECORDS_FIRST_VALID,
            ('THEN t."id" END AS "id",CASE WHEN'),
            _POSTGRESQL_ALL_GRAPH_PAGE_GATE_RECORDS_FIRST_VALID,
            ('THEN t."kind" END AS "kind",CASE WHEN'),
            _POSTGRESQL_ALL_GRAPH_PAGE_GATE_RECORDS_FIRST_VALID,
            ('THEN CAST(t."data" AS TEXT) END AS "data",CASE WHEN'),
            _POSTGRESQL_ALL_GRAPH_PAGE_GATE_RECORDS_FIRST_VALID,
            ("THEN s.project_id END AS scope_project_id,CASE WHEN"),
            _POSTGRESQL_ALL_GRAPH_PAGE_GATE_RECORDS_FIRST_VALID,
            (
                'THEN 0 ELSE 1 END AS invalid FROM "records" AS t LEFT JOIN '
                'resource_scopes AS s ON s.resource_kind=t."kind" AND '
                "s.resource_id=t.id LEFT JOIN projects AS p ON p.id=s.project_id "
                'WHERE t."id" > :after_id AND t."id" <= :through_id ORDER BY t."id" '
                "LIMIT 4097\n"
            ),
        )
    ),
    ("all", "postgresql", "graph_page_gate_events_first"): "".join(
        (
            (
                "WITH candidate AS MATERIALIZED (SELECT "
                't."run_id",t."step",(coalesce(octet_length(CAST(t."run_id" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(t."step" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(t."artifact" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(t."hash" AS TEXT)),0)) AS '
                "native_bytes, CASE WHEN"
            ),
            _POSTGRESQL_ALL_GRAPH_PAGE_GATE_EVENTS_FIRST_VALID,
            (
                'THEN 0 ELSE 1 END AS invalid FROM "events" AS t ORDER BY '
                't."run_id",t."step" LIMIT 4096)'
            ),
            _SQLITE_ALL_GRAPH_PAGE_GATE_EVENTS_FIRST_RANKED,
            _SQLITE_ALL_GRAPH_PAGE_GATE_EVENTS_FIRST_PROJECTION,
        )
    ),
    ("all", "postgresql", "graph_page_body_events_first"): "".join(
        (
            ("SELECT CASE WHEN"),
            _POSTGRESQL_ALL_GRAPH_PAGE_GATE_EVENTS_FIRST_VALID,
            ('THEN t."run_id" END AS "run_id",CASE WHEN'),
            _POSTGRESQL_ALL_GRAPH_PAGE_GATE_EVENTS_FIRST_VALID,
            ('THEN t."step" END AS "step",CASE WHEN'),
            _POSTGRESQL_ALL_GRAPH_PAGE_GATE_EVENTS_FIRST_VALID,
            (
                'THEN 0 ELSE 1 END AS invalid FROM "events" AS t WHERE '
                '(t."run_id",t."step") <= (:through_run_id,:through_step) ORDER BY '
                't."run_id",t."step" LIMIT 4097\n'
            ),
        )
    ),
    ("all", "postgresql", "graph_page_gate_events_next"): "".join(
        (
            (
                "WITH candidate AS MATERIALIZED (SELECT "
                't."run_id",t."step",(coalesce(octet_length(CAST(t."run_id" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(t."step" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(t."artifact" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(t."hash" AS TEXT)),0)) AS '
                "native_bytes, CASE WHEN"
            ),
            _POSTGRESQL_ALL_GRAPH_PAGE_GATE_EVENTS_FIRST_VALID,
            (
                'THEN 0 ELSE 1 END AS invalid FROM "events" AS t WHERE '
                '(t."run_id",t."step") > (:after_run_id,:after_step) ORDER BY '
                't."run_id",t."step" LIMIT 4096)'
            ),
            _SQLITE_ALL_GRAPH_PAGE_GATE_EVENTS_FIRST_RANKED,
            _SQLITE_ALL_GRAPH_PAGE_GATE_EVENTS_FIRST_PROJECTION,
        )
    ),
    ("all", "postgresql", "graph_page_body_events_next"): "".join(
        (
            ("SELECT CASE WHEN"),
            _POSTGRESQL_ALL_GRAPH_PAGE_GATE_EVENTS_FIRST_VALID,
            ('THEN t."run_id" END AS "run_id",CASE WHEN'),
            _POSTGRESQL_ALL_GRAPH_PAGE_GATE_EVENTS_FIRST_VALID,
            ('THEN t."step" END AS "step",CASE WHEN'),
            _POSTGRESQL_ALL_GRAPH_PAGE_GATE_EVENTS_FIRST_VALID,
            (
                'THEN 0 ELSE 1 END AS invalid FROM "events" AS t WHERE '
                '(t."run_id",t."step") > (:after_run_id,:after_step) AND '
                '(t."run_id",t."step") <= (:through_run_id,:through_step) ORDER BY '
                't."run_id",t."step" LIMIT 4097\n'
            ),
        )
    ),
    ("all", "sqlite", "scope_complete_count"): "".join(
        (_SQLITE_ALL_SCOPE_COMPLETE_COUNT_PROJECTION,)
    ),
    ("all", "postgresql", "scope_complete_count"): "".join(
        (_SQLITE_ALL_SCOPE_COMPLETE_COUNT_PROJECTION,)
    ),
}
