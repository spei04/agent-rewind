"""Bounded financial domains and descriptor closure statements."""

# Fixed fragments share identical predicates; no input becomes SQL syntax.

_SQLITE_AR7_JOB_VALID = (
    " (q.\"id\" IS NOT NULL AND (typeof(q.\"id\") IN ('null','integer','text') "
    'OR (typeof(q."id")=\'real\' AND q."id" BETWEEN -1.7976931348623157e308 '
    "AND 1.7976931348623157e308)) AND (typeof(q.\"id\")='text' AND "
    'length(q."id")=32 AND length(CAST(q."id" AS BLOB))=32 AND q."id" NOT '
    'GLOB \'*[^0-9a-f]*\') AND q."kind" IS NOT NULL AND (typeof(q."kind") IN '
    "('null','integer','text') OR (typeof(q.\"kind\")='real' AND q.\"kind\" "
    "BETWEEN -1.7976931348623157e308 AND 1.7976931348623157e308)) AND "
    "q.\"kind\" IN ('run','branch','study','investigate') AND q.\"created\" IS "
    "NOT NULL AND (typeof(q.\"created\") IN ('null','integer','text') OR "
    '(typeof(q."created")=\'real\' AND q."created" BETWEEN '
    '-1.7976931348623157e308 AND 1.7976931348623157e308)) AND q."payload" IS '
    "NOT NULL AND (typeof(q.\"payload\") IN ('null','integer','text') OR "
    '(typeof(q."payload")=\'real\' AND q."payload" BETWEEN '
    '-1.7976931348623157e308 AND 1.7976931348623157e308)) AND q."status" IS '
    "NOT NULL AND (typeof(q.\"status\") IN ('null','integer','text') OR "
    '(typeof(q."status")=\'real\' AND q."status" BETWEEN '
    '-1.7976931348623157e308 AND 1.7976931348623157e308)) AND q."status" IN '
    "('queued','running','succeeded','failed','cancelled') AND "
    "(typeof(q.\"owner\") IN ('null','integer','text') OR "
    '(typeof(q."owner")=\'real\' AND q."owner" BETWEEN -1.7976931348623157e308 '
    'AND 1.7976931348623157e308)) AND (typeof(q."lease_until") IN '
    "('null','integer','text') OR (typeof(q.\"lease_until\")='real' AND "
    'q."lease_until" BETWEEN -1.7976931348623157e308 AND '
    '1.7976931348623157e308)) AND q."cancel" IS NOT NULL AND '
    "(typeof(q.\"cancel\") IN ('null','integer','text') OR "
    '(typeof(q."cancel")=\'real\' AND q."cancel" BETWEEN '
    '-1.7976931348623157e308 AND 1.7976931348623157e308)) AND q."budget" IS '
    "NOT NULL AND (typeof(q.\"budget\") IN ('null','integer','text') OR "
    '(typeof(q."budget")=\'real\' AND q."budget" BETWEEN '
    "-1.7976931348623157e308 AND 1.7976931348623157e308)) AND "
    'typeof(q."budget")=\'integer\' AND q."budget" BETWEEN 0 AND '
    '9223372036854775807 AND q."reserved" IS NOT NULL AND '
    "(typeof(q.\"reserved\") IN ('null','integer','text') OR "
    '(typeof(q."reserved")=\'real\' AND q."reserved" BETWEEN '
    "-1.7976931348623157e308 AND 1.7976931348623157e308)) AND "
    'typeof(q."reserved")=\'integer\' AND q."reserved" BETWEEN 0 AND '
    '9223372036854775807 AND (typeof(q."result") IN '
    "('null','integer','text') OR (typeof(q.\"result\")='real' AND q.\"result\" "
    "BETWEEN -1.7976931348623157e308 AND 1.7976931348623157e308)) AND "
    "(typeof(q.\"error\") IN ('null','integer','text') OR "
    '(typeof(q."error")=\'real\' AND q."error" BETWEEN -1.7976931348623157e308 '
    'AND 1.7976931348623157e308)) AND (typeof(q."actor") IN '
    "('null','integer','text') OR (typeof(q.\"actor\")='real' AND q.\"actor\" "
    "BETWEEN -1.7976931348623157e308 AND 1.7976931348623157e308)) AND "
    'q."payload_version" IS NOT NULL AND (q."execution_config_ref" IS NULL '
    "OR (typeof(q.\"execution_config_ref\")='text' AND "
    'length(q."execution_config_ref")=64 AND '
    'length(CAST(q."execution_config_ref" AS BLOB))=64 AND '
    "q.\"execution_config_ref\" NOT GLOB '*[^0-9a-f]*')) AND "
    '(q."execution_config_digest" IS NULL OR '
    "(typeof(q.\"execution_config_digest\")='text' AND "
    'length(q."execution_config_digest")=64 AND '
    'length(CAST(q."execution_config_digest" AS BLOB))=64 AND '
    "q.\"execution_config_digest\" NOT GLOB '*[^0-9a-f]*')) AND "
    'q."lease_generation" IS NOT NULL AND q."legacy_reserved_microusd" IS '
    "NOT NULL AND (typeof(lease_generation)='integer' AND lease_generation "
    "BETWEEN 0 AND 9223372036854775807) AND "
    "(typeof(legacy_reserved_microusd)='integer' AND "
    "legacy_reserved_microusd BETWEEN 0 AND 9223372036854775807) AND "
    "(payload_version IN (1,2) AND typeof(payload_version)='integer') AND "
    "((payload_version=1 AND execution_config_ref IS NULL\n            AND "
    "execution_config_digest IS NULL)\n          OR (execution_config_ref IS "
    "NOT NULL AND execution_config_digest IS NOT NULL\n            AND "
    "typeof(execution_config_ref)='text' AND length(execution_config_ref)=64 "
    "AND length(CAST(execution_config_ref AS BLOB))=64 AND "
    "execution_config_ref NOT GLOB '*[^0-9a-f]*'\n            AND "
    "typeof(execution_config_digest)='text' AND "
    "length(execution_config_digest)=64 AND "
    "length(CAST(execution_config_digest AS BLOB))=64 AND "
    "execution_config_digest NOT GLOB '*[^0-9a-f]*'\n            AND "
    "execution_config_ref=execution_config_digest)) AND "
    'q."reserved"<=q."budget" AND (q."payload_version"<>2 OR ((q."id" IS NOT '
    'NULL AND (typeof(q."id")=\'text\' AND length(CAST(q."id" AS BLOB))<=32)) '
    'AND coalesce(length(CAST(q."id" AS BLOB)),0)<=32 AND (q."kind" IS NOT '
    'NULL AND (typeof(q."kind")=\'text\' AND length(CAST(q."kind" AS '
    'BLOB))<=20)) AND coalesce(length(CAST(q."kind" AS BLOB)),0)<=20 AND '
    "(q.\"created\" IS NOT NULL AND (typeof(q.\"created\") IN ('integer','real') "
    'AND q."created" BETWEEN -1.7976931348623157e308 AND '
    '1.7976931348623157e308)) AND coalesce(length(CAST(q."created" AS '
    'BLOB)),0)<=64 AND (q."payload" IS NOT NULL AND '
    '(typeof(q."payload")=\'text\' AND length(CAST(q."payload" AS BLOB))<=64)) '
    'AND coalesce(length(CAST(q."payload" AS BLOB)),0)<=64 AND (q."status" '
    'IS NOT NULL AND (typeof(q."status")=\'text\' AND length(CAST(q."status" '
    'AS BLOB))<=20)) AND coalesce(length(CAST(q."status" AS BLOB)),0)<=20 '
    'AND (q."owner" IS NULL OR (typeof(q."owner")=\'text\' AND '
    'length(CAST(q."owner" AS BLOB))<=64)) AND '
    'coalesce(length(CAST(q."owner" AS BLOB)),0)<=64 AND (q."lease_until" IS '
    "NULL OR (typeof(q.\"lease_until\") IN ('integer','real') AND "
    'q."lease_until" BETWEEN -1.7976931348623157e308 AND '
    '1.7976931348623157e308)) AND coalesce(length(CAST(q."lease_until" AS '
    'BLOB)),0)<=64 AND (q."cancel" IS NOT NULL AND '
    '(typeof(q."cancel")=\'integer\' AND q."cancel" IN (0,1))) AND '
    'coalesce(length(CAST(q."cancel" AS BLOB)),0)<=8 AND (q."budget" IS NOT '
    "NULL AND (typeof(q.\"budget\")='integer')) AND "
    'coalesce(length(CAST(q."budget" AS BLOB)),0)<=24 AND (q."reserved" IS '
    "NOT NULL AND (typeof(q.\"reserved\")='integer')) AND "
    'coalesce(length(CAST(q."reserved" AS BLOB)),0)<=24 AND (q."result" IS '
    'NULL OR (typeof(q."result")=\'text\' AND length(CAST(q."result" AS '
    'BLOB))<=64)) AND coalesce(length(CAST(q."result" AS BLOB)),0)<=64 AND '
    '(q."error" IS NULL OR (typeof(q."error")=\'text\' AND '
    'length(CAST(q."error" AS BLOB))<=1200)) AND '
    'coalesce(length(CAST(q."error" AS BLOB)),0)<=1200 AND (q."actor" IS '
    'NULL OR (typeof(q."actor")=\'text\' AND length(CAST(q."actor" AS '
    'BLOB))<=256)) AND coalesce(length(CAST(q."actor" AS BLOB)),0)<=256 AND '
    '(q."payload_version" IS NOT NULL AND (typeof(q."payload_version")=\'integ'
    'er\')) AND coalesce(length(CAST(q."payload_version" AS BLOB)),0)<=8 AND '
    '(q."execution_config_ref" IS NULL OR (typeof(q."execution_config_ref")=\''
    'text\' AND length(CAST(q."execution_config_ref" AS BLOB))<=64)) AND '
    'coalesce(length(CAST(q."execution_config_ref" AS BLOB)),0)<=64 AND '
    '(q."execution_config_digest" IS NULL OR '
    "(typeof(q.\"execution_config_digest\")='text' AND "
    'length(CAST(q."execution_config_digest" AS BLOB))<=64)) AND '
    'coalesce(length(CAST(q."execution_config_digest" AS BLOB)),0)<=64))) '
)


_SQLITE_AR6_JOB_VALID = (
    " (q.\"id\" IS NOT NULL AND (typeof(q.\"id\") IN ('null','integer','text') "
    'OR (typeof(q."id")=\'real\' AND q."id" BETWEEN -1.7976931348623157e308 '
    "AND 1.7976931348623157e308)) AND (typeof(q.\"id\")='text' AND "
    'length(q."id")=32 AND length(CAST(q."id" AS BLOB))=32 AND q."id" NOT '
    'GLOB \'*[^0-9a-f]*\') AND q."kind" IS NOT NULL AND (typeof(q."kind") IN '
    "('null','integer','text') OR (typeof(q.\"kind\")='real' AND q.\"kind\" "
    "BETWEEN -1.7976931348623157e308 AND 1.7976931348623157e308)) AND "
    "q.\"kind\" IN ('run','branch','study','investigate') AND q.\"created\" IS "
    "NOT NULL AND (typeof(q.\"created\") IN ('null','integer','text') OR "
    '(typeof(q."created")=\'real\' AND q."created" BETWEEN '
    '-1.7976931348623157e308 AND 1.7976931348623157e308)) AND q."payload" IS '
    "NOT NULL AND (typeof(q.\"payload\") IN ('null','integer','text') OR "
    '(typeof(q."payload")=\'real\' AND q."payload" BETWEEN '
    '-1.7976931348623157e308 AND 1.7976931348623157e308)) AND q."status" IS '
    "NOT NULL AND (typeof(q.\"status\") IN ('null','integer','text') OR "
    '(typeof(q."status")=\'real\' AND q."status" BETWEEN '
    '-1.7976931348623157e308 AND 1.7976931348623157e308)) AND q."status" IN '
    "('queued','running','succeeded','failed','cancelled') AND "
    "(typeof(q.\"owner\") IN ('null','integer','text') OR "
    '(typeof(q."owner")=\'real\' AND q."owner" BETWEEN -1.7976931348623157e308 '
    'AND 1.7976931348623157e308)) AND (typeof(q."lease_until") IN '
    "('null','integer','text') OR (typeof(q.\"lease_until\")='real' AND "
    'q."lease_until" BETWEEN -1.7976931348623157e308 AND '
    '1.7976931348623157e308)) AND q."cancel" IS NOT NULL AND '
    "(typeof(q.\"cancel\") IN ('null','integer','text') OR "
    '(typeof(q."cancel")=\'real\' AND q."cancel" BETWEEN '
    '-1.7976931348623157e308 AND 1.7976931348623157e308)) AND q."budget" IS '
    "NOT NULL AND (typeof(q.\"budget\") IN ('null','integer','text') OR "
    '(typeof(q."budget")=\'real\' AND q."budget" BETWEEN '
    "-1.7976931348623157e308 AND 1.7976931348623157e308)) AND "
    'typeof(q."budget")=\'integer\' AND q."budget" BETWEEN 0 AND '
    '9223372036854775807 AND q."reserved" IS NOT NULL AND '
    "(typeof(q.\"reserved\") IN ('null','integer','text') OR "
    '(typeof(q."reserved")=\'real\' AND q."reserved" BETWEEN '
    "-1.7976931348623157e308 AND 1.7976931348623157e308)) AND "
    'typeof(q."reserved")=\'integer\' AND q."reserved" BETWEEN 0 AND '
    '9223372036854775807 AND (typeof(q."result") IN '
    "('null','integer','text') OR (typeof(q.\"result\")='real' AND q.\"result\" "
    "BETWEEN -1.7976931348623157e308 AND 1.7976931348623157e308)) AND "
    "(typeof(q.\"error\") IN ('null','integer','text') OR "
    '(typeof(q."error")=\'real\' AND q."error" BETWEEN -1.7976931348623157e308 '
    'AND 1.7976931348623157e308)) AND (typeof(q."actor") IN '
    "('null','integer','text') OR (typeof(q.\"actor\")='real' AND q.\"actor\" "
    "BETWEEN -1.7976931348623157e308 AND 1.7976931348623157e308)) AND "
    'q."payload_version" IS NOT NULL AND (q."execution_config_ref" IS NULL '
    "OR (typeof(q.\"execution_config_ref\")='text' AND "
    'length(q."execution_config_ref")=64 AND '
    'length(CAST(q."execution_config_ref" AS BLOB))=64 AND '
    "q.\"execution_config_ref\" NOT GLOB '*[^0-9a-f]*')) AND "
    '(q."execution_config_digest" IS NULL OR '
    "(typeof(q.\"execution_config_digest\")='text' AND "
    'length(q."execution_config_digest")=64 AND '
    'length(CAST(q."execution_config_digest" AS BLOB))=64 AND '
    "q.\"execution_config_digest\" NOT GLOB '*[^0-9a-f]*')) AND "
    "(payload_version IN (1,2) AND typeof(payload_version)='integer') AND "
    "((payload_version=1 AND execution_config_ref IS NULL\n            AND "
    "execution_config_digest IS NULL)\n          OR (execution_config_ref IS "
    "NOT NULL AND execution_config_digest IS NOT NULL\n            AND "
    "typeof(execution_config_ref)='text' AND length(execution_config_ref)=64 "
    "AND length(CAST(execution_config_ref AS BLOB))=64 AND "
    "execution_config_ref NOT GLOB '*[^0-9a-f]*'\n            AND "
    "typeof(execution_config_digest)='text' AND "
    "length(execution_config_digest)=64 AND "
    "length(CAST(execution_config_digest AS BLOB))=64 AND "
    "execution_config_digest NOT GLOB '*[^0-9a-f]*'\n            AND "
    "execution_config_ref=execution_config_digest)) AND "
    'q."reserved"<=q."budget" AND (q."payload_version"<>2 OR ((q."id" IS NOT '
    'NULL AND (typeof(q."id")=\'text\' AND length(CAST(q."id" AS BLOB))<=32)) '
    'AND coalesce(length(CAST(q."id" AS BLOB)),0)<=32 AND (q."kind" IS NOT '
    'NULL AND (typeof(q."kind")=\'text\' AND length(CAST(q."kind" AS '
    'BLOB))<=20)) AND coalesce(length(CAST(q."kind" AS BLOB)),0)<=20 AND '
    "(q.\"created\" IS NOT NULL AND (typeof(q.\"created\") IN ('integer','real') "
    'AND q."created" BETWEEN -1.7976931348623157e308 AND '
    '1.7976931348623157e308)) AND coalesce(length(CAST(q."created" AS '
    'BLOB)),0)<=64 AND (q."payload" IS NOT NULL AND '
    '(typeof(q."payload")=\'text\' AND length(CAST(q."payload" AS BLOB))<=64)) '
    'AND coalesce(length(CAST(q."payload" AS BLOB)),0)<=64 AND (q."status" '
    'IS NOT NULL AND (typeof(q."status")=\'text\' AND length(CAST(q."status" '
    'AS BLOB))<=20)) AND coalesce(length(CAST(q."status" AS BLOB)),0)<=20 '
    'AND (q."owner" IS NULL OR (typeof(q."owner")=\'text\' AND '
    'length(CAST(q."owner" AS BLOB))<=64)) AND '
    'coalesce(length(CAST(q."owner" AS BLOB)),0)<=64 AND (q."lease_until" IS '
    "NULL OR (typeof(q.\"lease_until\") IN ('integer','real') AND "
    'q."lease_until" BETWEEN -1.7976931348623157e308 AND '
    '1.7976931348623157e308)) AND coalesce(length(CAST(q."lease_until" AS '
    'BLOB)),0)<=64 AND (q."cancel" IS NOT NULL AND '
    '(typeof(q."cancel")=\'integer\' AND q."cancel" IN (0,1))) AND '
    'coalesce(length(CAST(q."cancel" AS BLOB)),0)<=8 AND (q."budget" IS NOT '
    "NULL AND (typeof(q.\"budget\")='integer')) AND "
    'coalesce(length(CAST(q."budget" AS BLOB)),0)<=24 AND (q."reserved" IS '
    "NOT NULL AND (typeof(q.\"reserved\")='integer')) AND "
    'coalesce(length(CAST(q."reserved" AS BLOB)),0)<=24 AND (q."result" IS '
    'NULL OR (typeof(q."result")=\'text\' AND length(CAST(q."result" AS '
    'BLOB))<=64)) AND coalesce(length(CAST(q."result" AS BLOB)),0)<=64 AND '
    '(q."error" IS NULL OR (typeof(q."error")=\'text\' AND '
    'length(CAST(q."error" AS BLOB))<=1200)) AND '
    'coalesce(length(CAST(q."error" AS BLOB)),0)<=1200 AND (q."actor" IS '
    'NULL OR (typeof(q."actor")=\'text\' AND length(CAST(q."actor" AS '
    'BLOB))<=256)) AND coalesce(length(CAST(q."actor" AS BLOB)),0)<=256 AND '
    '(q."payload_version" IS NOT NULL AND (typeof(q."payload_version")=\'integ'
    'er\')) AND coalesce(length(CAST(q."payload_version" AS BLOB)),0)<=8 AND '
    '(q."execution_config_ref" IS NULL OR (typeof(q."execution_config_ref")=\''
    'text\' AND length(CAST(q."execution_config_ref" AS BLOB))<=64)) AND '
    'coalesce(length(CAST(q."execution_config_ref" AS BLOB)),0)<=64 AND '
    '(q."execution_config_digest" IS NULL OR '
    "(typeof(q.\"execution_config_digest\")='text' AND "
    'length(CAST(q."execution_config_digest" AS BLOB))<=64)) AND '
    'coalesce(length(CAST(q."execution_config_digest" AS BLOB)),0)<=64))) '
)


_SQLITE_AR6_OPERATION_VALID = (
    ' (q."id" IS NOT NULL AND (q."id" IS NOT NULL AND (typeof(q."id")=\'text\' '
    'AND length(CAST(q."id" AS BLOB))<=32)) AND (typeof(q."id")=\'text\' AND '
    'length(q."id")=32 AND length(CAST(q."id" AS BLOB))=32 AND q."id" NOT '
    'GLOB \'*[^0-9a-f]*\') AND q."project_id" IS NOT NULL AND (q."project_id" '
    "IS NOT NULL AND (typeof(q.\"project_id\")='text' AND "
    'length(CAST(q."project_id" AS BLOB))<=32)) AND '
    '(typeof(q."project_id")=\'text\' AND length(q."project_id")=32 AND '
    'length(CAST(q."project_id" AS BLOB))=32 AND q."project_id" NOT GLOB '
    '\'*[^0-9a-f]*\') AND q."principal_id" IS NOT NULL AND (q."principal_id" '
    "IS NOT NULL AND (typeof(q.\"principal_id\")='text' AND "
    'length(CAST(q."principal_id" AS BLOB))<=256)) AND q."kind" IS NOT NULL '
    'AND (q."kind" IS NOT NULL AND (typeof(q."kind")=\'text\' AND '
    'length(CAST(q."kind" AS BLOB))<=20)) AND q."client_operation_id" IS NOT '
    'NULL AND (q."client_operation_id" IS NOT NULL AND '
    "(typeof(q.\"client_operation_id\")='text' AND "
    'length(CAST(q."client_operation_id" AS BLOB))<=32)) AND '
    "(typeof(q.\"client_operation_id\")='text' AND "
    'length(q."client_operation_id")=32 AND '
    'length(CAST(q."client_operation_id" AS BLOB))=32 AND '
    'q."client_operation_id" NOT GLOB \'*[^0-9a-f]*\') AND q."request_digest" '
    'IS NOT NULL AND (q."request_digest" IS NOT NULL AND '
    '(typeof(q."request_digest")=\'text\' AND length(CAST(q."request_digest" '
    "AS BLOB))<=64)) AND (typeof(q.\"request_digest\")='text' AND "
    'length(q."request_digest")=64 AND length(CAST(q."request_digest" AS '
    'BLOB))=64 AND q."request_digest" NOT GLOB \'*[^0-9a-f]*\') AND q."job_id" '
    'IS NOT NULL AND (q."job_id" IS NOT NULL AND (typeof(q."job_id")=\'text\' '
    'AND length(CAST(q."job_id" AS BLOB))<=32)) AND '
    '(typeof(q."job_id")=\'text\' AND length(q."job_id")=32 AND '
    'length(CAST(q."job_id" AS BLOB))=32 AND q."job_id" NOT GLOB '
    "'*[^0-9a-f]*') AND q.\"accepted_response\" IS NOT NULL AND "
    '(q."accepted_response" IS NOT NULL AND '
    "(typeof(q.\"accepted_response\")='text' AND "
    'length(CAST(q."accepted_response" AS BLOB))<=128)) AND q."created_at" '
    'IS NOT NULL AND (q."created_at" IS NOT NULL AND '
    '(typeof(q."created_at")=\'text\' AND length(CAST(q."created_at" AS '
    'BLOB))<=64)) AND q."retain_until" IS NOT NULL AND (q."retain_until" IS '
    "NOT NULL AND (typeof(q.\"retain_until\")='text' AND "
    'length(CAST(q."retain_until" AS BLOB))<=64)) AND q."job_resource_kind" '
    'IS NOT NULL AND (q."job_resource_kind" IS NOT NULL AND '
    "(typeof(q.\"job_resource_kind\")='text' AND "
    'length(CAST(q."job_resource_kind" AS BLOB))<=20)) AND '
    'q."execution_config_digest" IS NOT NULL AND '
    '(q."execution_config_digest" IS NOT NULL AND '
    "(typeof(q.\"execution_config_digest\")='text' AND "
    'length(CAST(q."execution_config_digest" AS BLOB))<=64)) AND '
    "(typeof(q.\"execution_config_digest\")='text' AND "
    'length(q."execution_config_digest")=64 AND '
    'length(CAST(q."execution_config_digest" AS BLOB))=64 AND '
    "q.\"execution_config_digest\" NOT GLOB '*[^0-9a-f]*') AND "
    'q."payload_version" IS NOT NULL AND (q."payload_version" IS NOT NULL '
    "AND (typeof(q.\"payload_version\")='integer')) AND "
    '(q."failure_correlation_id" IS NULL OR '
    "(typeof(q.\"failure_correlation_id\")='text' AND "
    'length(CAST(q."failure_correlation_id" AS BLOB))<=32)) AND '
    '(q."failure_correlation_id" IS NULL OR '
    "(typeof(q.\"failure_correlation_id\")='text' AND "
    'length(q."failure_correlation_id")=32 AND '
    'length(CAST(q."failure_correlation_id" AS BLOB))=32 AND '
    "q.\"failure_correlation_id\" NOT GLOB '*[^0-9a-f]*')) AND "
    "(typeof(id)='text' AND length(id)=32 AND length(CAST(id AS BLOB))=32 "
    "AND id NOT GLOB '*[^0-9a-f]*') AND (typeof(project_id)='text' AND "
    "length(project_id)=32 AND length(CAST(project_id AS BLOB))=32 AND "
    "project_id NOT GLOB '*[^0-9a-f]*') AND (typeof(principal_id)='text' AND "
    "((substr(principal_id,1,5)='oidc:' AND length(principal_id)=69 AND "
    "length(CAST(principal_id AS BLOB))=69 AND substr(principal_id,6) NOT "
    "GLOB '*[^0-9a-f]*') OR (substr(principal_id,1,8)='api-key:' AND "
    "length(principal_id)=40 AND length(CAST(principal_id AS BLOB))=40 AND "
    "substr(principal_id,9) NOT GLOB '*[^0-9a-f]*'))) AND (kind='run') AND "
    "(typeof(client_operation_id)='text' AND length(client_operation_id)=32 "
    "AND length(CAST(client_operation_id AS BLOB))=32 AND "
    "client_operation_id NOT GLOB '*[^0-9a-f]*') AND "
    "(typeof(request_digest)='text' AND length(request_digest)=64 AND "
    "length(CAST(request_digest AS BLOB))=64 AND request_digest NOT GLOB "
    "'*[^0-9a-f]*') AND (typeof(job_id)='text' AND length(job_id)=32 AND "
    "length(CAST(job_id AS BLOB))=32 AND job_id NOT GLOB '*[^0-9a-f]*') AND "
    '(accepted_response=\'{"job_id":"\' || job_id || \'","operation_id":"\' || '
    "id || '\"}') AND (retain_until>=created_at) AND "
    "(job_resource_kind='job') AND (typeof(execution_config_digest)='text' "
    "AND length(execution_config_digest)=64 AND "
    "length(CAST(execution_config_digest AS BLOB))=64 AND "
    "execution_config_digest NOT GLOB '*[^0-9a-f]*') AND (payload_version=2 "
    "AND typeof(payload_version)='integer') AND (failure_correlation_id IS "
    "NULL OR (typeof(failure_correlation_id)='text' AND "
    "length(failure_correlation_id)=32 AND "
    "length(CAST(failure_correlation_id AS BLOB))=32 AND "
    "failure_correlation_id NOT GLOB '*[^0-9a-f]*'))) "
)


_SQLITE_AR7_CALL_VALID = (
    ' (q."id" IS NOT NULL AND (typeof(q."id")=\'text\' AND length(q."id")=32 '
    'AND length(CAST(q."id" AS BLOB))=32 AND q."id" NOT GLOB \'*[^0-9a-f]*\') '
    'AND q."project_id" IS NOT NULL AND (typeof(q."project_id")=\'text\' AND '
    'length(q."project_id")=32 AND length(CAST(q."project_id" AS BLOB))=32 '
    'AND q."project_id" NOT GLOB \'*[^0-9a-f]*\') AND q."job_id" IS NOT NULL '
    'AND (typeof(q."job_id")=\'text\' AND length(q."job_id")=32 AND '
    'length(CAST(q."job_id" AS BLOB))=32 AND q."job_id" NOT GLOB '
    "'*[^0-9a-f]*') AND q.\"logical_call_id\" IS NOT NULL AND "
    '(typeof(q."logical_call_id")=\'text\' AND length(q."logical_call_id")=32 '
    'AND length(CAST(q."logical_call_id" AS BLOB))=32 AND '
    'q."logical_call_id" NOT GLOB \'*[^0-9a-f]*\') AND q."purpose" IS NOT NULL '
    'AND q."request_digest" IS NOT NULL AND '
    '(typeof(q."request_digest")=\'text\' AND length(q."request_digest")=64 '
    'AND length(CAST(q."request_digest" AS BLOB))=64 AND q."request_digest" '
    'NOT GLOB \'*[^0-9a-f]*\') AND q."price_version" IS NOT NULL AND q."state" '
    'IS NOT NULL AND q."reserved_microusd" IS NOT NULL AND q."created_at" IS '
    'NOT NULL AND q."organization_id" IS NOT NULL AND '
    '(typeof(q."organization_id")=\'text\' AND length(q."organization_id")=32 '
    'AND length(CAST(q."organization_id" AS BLOB))=32 AND '
    'q."organization_id" NOT GLOB \'*[^0-9a-f]*\') AND q."job_resource_kind" '
    'IS NOT NULL AND q."lease_generation" IS NOT NULL AND '
    'q."organization_account_id" IS NOT NULL AND '
    "(typeof(q.\"organization_account_id\")='text' AND "
    'length(q."organization_account_id")=32 AND '
    'length(CAST(q."organization_account_id" AS BLOB))=32 AND '
    "q.\"organization_account_id\" NOT GLOB '*[^0-9a-f]*') AND "
    'q."project_account_id" IS NOT NULL AND '
    "(typeof(q.\"project_account_id\")='text' AND "
    'length(q."project_account_id")=32 AND '
    'length(CAST(q."project_account_id" AS BLOB))=32 AND '
    'q."project_account_id" NOT GLOB \'*[^0-9a-f]*\') AND q."job_account_id" '
    "IS NOT NULL AND (typeof(q.\"job_account_id\")='text' AND "
    'length(q."job_account_id")=32 AND length(CAST(q."job_account_id" AS '
    "BLOB))=32 AND q.\"job_account_id\" NOT GLOB '*[^0-9a-f]*') AND "
    "(typeof(created_at)='text' AND length(CAST(created_at AS BLOB))=27 AND "
    "created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:["
    "0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z' AND "
    "substr(created_at,1,4) BETWEEN '0001' AND '9999' AND "
    "date(substr(created_at,1,10),'+0 days') IS substr(created_at,1,10) AND "
    "substr(created_at,12,2) BETWEEN '00' AND '23' AND "
    "substr(created_at,15,2) BETWEEN '00' AND '59' AND "
    "substr(created_at,18,2) BETWEEN '00' AND '59') AND "
    "(typeof(request_digest)='text' AND length(request_digest)=64 AND "
    "length(CAST(request_digest AS BLOB))=64 AND request_digest NOT GLOB "
    "'*[^0-9a-f]*') AND (usage_estimate_microusd IS NULL OR "
    "(typeof(usage_estimate_microusd)='integer' AND usage_estimate_microusd "
    "BETWEEN 0 AND 9223372036854775807)) AND "
    "(typeof(lease_generation)='integer' AND lease_generation BETWEEN 1 AND "
    "9223372036854775807) AND (typeof(id)='text' AND length(id)=32 AND "
    "length(CAST(id AS BLOB))=32 AND id NOT GLOB '*[^0-9a-f]*') AND "
    "(typeof(job_id)='text' AND length(job_id)=32 AND length(CAST(job_id AS "
    "BLOB))=32 AND job_id NOT GLOB '*[^0-9a-f]*') AND "
    "(typeof(job_account_id)='text' AND length(job_account_id)=32 AND "
    "length(CAST(job_account_id AS BLOB))=32 AND job_account_id NOT GLOB "
    "'*[^0-9a-f]*') AND (job_resource_kind='job') AND "
    "(typeof(logical_call_id)='text' AND length(logical_call_id)=32 AND "
    "length(CAST(logical_call_id AS BLOB))=32 AND logical_call_id NOT GLOB "
    "'*[^0-9a-f]*') AND (typeof(organization_account_id)='text' AND "
    "length(organization_account_id)=32 AND "
    "length(CAST(organization_account_id AS BLOB))=32 AND "
    "organization_account_id NOT GLOB '*[^0-9a-f]*') AND "
    "(typeof(organization_id)='text' AND length(organization_id)=32 AND "
    "length(CAST(organization_id AS BLOB))=32 AND organization_id NOT GLOB "
    "'*[^0-9a-f]*') AND (typeof(price_version)='text' AND "
    "length(price_version)<=128 AND length(CAST(price_version AS BLOB))<=512 "
    "AND instr(price_version,char(0))=0) AND (typeof(project_id)='text' AND "
    "length(project_id)=32 AND length(CAST(project_id AS BLOB))=32 AND "
    "project_id NOT GLOB '*[^0-9a-f]*') AND "
    "(typeof(project_account_id)='text' AND length(project_account_id)=32 "
    "AND length(CAST(project_account_id AS BLOB))=32 AND project_account_id "
    "NOT GLOB '*[^0-9a-f]*') AND (provider_request_id IS NULL OR "
    "(typeof(provider_request_id)='text' AND "
    "length(provider_request_id)<=256 AND length(CAST(provider_request_id AS "
    "BLOB))<=1024 AND instr(provider_request_id,char(0))=0)) AND "
    "(purpose='continuation' OR purpose='discovery') AND "
    "(typeof(reserved_microusd)='integer' AND reserved_microusd BETWEEN 0 "
    "AND 9223372036854775807) AND (state='reserved' OR state='dispatching' "
    "OR state='observed'\n            OR state='uncertain' OR "
    "state='reconciled')) "
)


_POSTGRESQL_AR7_JOB_VALID = (
    ' (q."id" IS NOT NULL AND (octet_length(CAST(q."id" AS TEXT))=32 AND '
    'q."id" ~ \'^[0-9a-f]{32}$\') AND q."kind" IS NOT NULL AND q."kind" IN '
    "('run','branch','study','investigate') AND q.\"created\" IS NOT NULL AND "
    '(q."created" IS NULL OR q."created" NOT IN (\'NaN\'::double '
    "precision,'Infinity'::double precision,'-Infinity'::double precision)) "
    'AND q."payload" IS NOT NULL AND q."status" IS NOT NULL AND q."status" '
    "IN ('queued','running','succeeded','failed','cancelled') AND "
    '(q."lease_until" IS NULL OR q."lease_until" NOT IN (\'NaN\'::double '
    "precision,'Infinity'::double precision,'-Infinity'::double precision)) "
    'AND q."cancel" IS NOT NULL AND q."budget" IS NOT NULL AND q."budget" '
    'BETWEEN 0 AND 9223372036854775807 AND q."reserved" IS NOT NULL AND '
    'q."reserved" BETWEEN 0 AND 9223372036854775807 AND q."payload_version" '
    'IS NOT NULL AND (q."execution_config_ref" IS NULL OR '
    '(octet_length(CAST(q."execution_config_ref" AS TEXT))=64 AND '
    "q.\"execution_config_ref\" ~ '^[0-9a-f]{64}$')) AND "
    '(q."execution_config_digest" IS NULL OR '
    '(octet_length(CAST(q."execution_config_digest" AS TEXT))=64 AND '
    "q.\"execution_config_digest\" ~ '^[0-9a-f]{64}$')) AND "
    'q."lease_generation" IS NOT NULL AND q."legacy_reserved_microusd" IS '
    "NOT NULL AND (lease_generation >= 0 AND lease_generation <= "
    "'9223372036854775807'::bigint) AND (legacy_reserved_microusd >= 0 AND "
    "legacy_reserved_microusd <= '9223372036854775807'::bigint) AND "
    "(payload_version = 1 AND execution_config_ref IS NULL AND "
    "execution_config_digest IS NULL OR execution_config_ref IS NOT NULL AND "
    "execution_config_digest IS NOT NULL AND execution_config_ref::text ~ "
    "'^[0-9a-f]{64}$'::text AND execution_config_digest::text ~ "
    "'^[0-9a-f]{64}$'::text AND execution_config_ref::text = "
    "execution_config_digest::text) AND (payload_version = ANY (ARRAY[1, "
    '2])) AND q."reserved"<=q."budget" AND (q."payload_version"<>2 OR '
    '((q."id" IS NOT NULL AND (octet_length(CAST(q."id" AS TEXT))<=32)) AND '
    'coalesce(octet_length(CAST(q."id" AS TEXT)),0)<=32 AND (q."kind" IS NOT '
    'NULL AND (octet_length(CAST(q."kind" AS TEXT))<=20)) AND '
    'coalesce(octet_length(CAST(q."kind" AS TEXT)),0)<=20 AND (q."created" '
    "IS NOT NULL AND (q.\"created\" NOT IN ('NaN'::double "
    "precision,'Infinity'::double precision,'-Infinity'::double precision))) "
    'AND coalesce(octet_length(CAST(q."created" AS TEXT)),0)<=64 AND '
    '(q."payload" IS NOT NULL AND (octet_length(CAST(q."payload" AS '
    'TEXT))<=64)) AND coalesce(octet_length(CAST(q."payload" AS '
    'TEXT)),0)<=64 AND (q."status" IS NOT NULL AND '
    '(octet_length(CAST(q."status" AS TEXT))<=20)) AND '
    'coalesce(octet_length(CAST(q."status" AS TEXT)),0)<=20 AND (q."owner" '
    'IS NULL OR (octet_length(CAST(q."owner" AS TEXT))<=64)) AND '
    'coalesce(octet_length(CAST(q."owner" AS TEXT)),0)<=64 AND '
    '(q."lease_until" IS NULL OR (q."lease_until" NOT IN (\'NaN\'::double '
    "precision,'Infinity'::double precision,'-Infinity'::double precision))) "
    'AND coalesce(octet_length(CAST(q."lease_until" AS TEXT)),0)<=64 AND '
    '(q."cancel" IS NOT NULL AND (q."cancel" IS NOT NULL)) AND '
    'coalesce(octet_length(CAST(q."cancel" AS TEXT)),0)<=8 AND (q."budget" '
    'IS NOT NULL AND (q."budget" IS NOT NULL)) AND '
    'coalesce(octet_length(CAST(q."budget" AS TEXT)),0)<=24 AND '
    '(q."reserved" IS NOT NULL AND (q."reserved" IS NOT NULL)) AND '
    'coalesce(octet_length(CAST(q."reserved" AS TEXT)),0)<=24 AND '
    '(q."result" IS NULL OR (octet_length(CAST(q."result" AS TEXT))<=64)) '
    'AND coalesce(octet_length(CAST(q."result" AS TEXT)),0)<=64 AND '
    '(q."error" IS NULL OR (octet_length(CAST(q."error" AS TEXT))<=1200)) '
    'AND coalesce(octet_length(CAST(q."error" AS TEXT)),0)<=1200 AND '
    '(q."actor" IS NULL OR (octet_length(CAST(q."actor" AS TEXT))<=256)) AND '
    'coalesce(octet_length(CAST(q."actor" AS TEXT)),0)<=256 AND '
    '(q."payload_version" IS NOT NULL AND (q."payload_version" IS NOT NULL)) '
    'AND coalesce(octet_length(CAST(q."payload_version" AS TEXT)),0)<=8 AND '
    '(q."execution_config_ref" IS NULL OR (octet_length(CAST(q."execution_con'
    'fig_ref" AS TEXT))<=64)) AND coalesce(octet_length(CAST(q."execution_con'
    'fig_ref" AS TEXT)),0)<=64 AND (q."execution_config_digest" IS NULL OR '
    '(octet_length(CAST(q."execution_config_digest" AS TEXT))<=64)) AND '
    'coalesce(octet_length(CAST(q."execution_config_digest" AS '
    "TEXT)),0)<=64))) "
)


_POSTGRESQL_AR6_JOB_VALID = (
    ' (q."id" IS NOT NULL AND (octet_length(CAST(q."id" AS TEXT))=32 AND '
    'q."id" ~ \'^[0-9a-f]{32}$\') AND q."kind" IS NOT NULL AND q."kind" IN '
    "('run','branch','study','investigate') AND q.\"created\" IS NOT NULL AND "
    '(q."created" IS NULL OR q."created" NOT IN (\'NaN\'::double '
    "precision,'Infinity'::double precision,'-Infinity'::double precision)) "
    'AND q."payload" IS NOT NULL AND q."status" IS NOT NULL AND q."status" '
    "IN ('queued','running','succeeded','failed','cancelled') AND "
    '(q."lease_until" IS NULL OR q."lease_until" NOT IN (\'NaN\'::double '
    "precision,'Infinity'::double precision,'-Infinity'::double precision)) "
    'AND q."cancel" IS NOT NULL AND q."budget" IS NOT NULL AND q."budget" '
    'BETWEEN 0 AND 9223372036854775807 AND q."reserved" IS NOT NULL AND '
    'q."reserved" BETWEEN 0 AND 9223372036854775807 AND q."payload_version" '
    'IS NOT NULL AND (q."execution_config_ref" IS NULL OR '
    '(octet_length(CAST(q."execution_config_ref" AS TEXT))=64 AND '
    "q.\"execution_config_ref\" ~ '^[0-9a-f]{64}$')) AND "
    '(q."execution_config_digest" IS NULL OR '
    '(octet_length(CAST(q."execution_config_digest" AS TEXT))=64 AND '
    "q.\"execution_config_digest\" ~ '^[0-9a-f]{64}$')) AND (payload_version = "
    "1 AND execution_config_ref IS NULL AND execution_config_digest IS NULL "
    "OR execution_config_ref IS NOT NULL AND execution_config_digest IS NOT "
    "NULL AND execution_config_ref::text ~ '^[0-9a-f]{64}$'::text AND "
    "execution_config_digest::text ~ '^[0-9a-f]{64}$'::text AND "
    "execution_config_ref::text = execution_config_digest::text) AND "
    '(payload_version = ANY (ARRAY[1, 2])) AND q."reserved"<=q."budget" AND '
    '(q."payload_version"<>2 OR ((q."id" IS NOT NULL AND '
    '(octet_length(CAST(q."id" AS TEXT))<=32)) AND '
    'coalesce(octet_length(CAST(q."id" AS TEXT)),0)<=32 AND (q."kind" IS NOT '
    'NULL AND (octet_length(CAST(q."kind" AS TEXT))<=20)) AND '
    'coalesce(octet_length(CAST(q."kind" AS TEXT)),0)<=20 AND (q."created" '
    "IS NOT NULL AND (q.\"created\" NOT IN ('NaN'::double "
    "precision,'Infinity'::double precision,'-Infinity'::double precision))) "
    'AND coalesce(octet_length(CAST(q."created" AS TEXT)),0)<=64 AND '
    '(q."payload" IS NOT NULL AND (octet_length(CAST(q."payload" AS '
    'TEXT))<=64)) AND coalesce(octet_length(CAST(q."payload" AS '
    'TEXT)),0)<=64 AND (q."status" IS NOT NULL AND '
    '(octet_length(CAST(q."status" AS TEXT))<=20)) AND '
    'coalesce(octet_length(CAST(q."status" AS TEXT)),0)<=20 AND (q."owner" '
    'IS NULL OR (octet_length(CAST(q."owner" AS TEXT))<=64)) AND '
    'coalesce(octet_length(CAST(q."owner" AS TEXT)),0)<=64 AND '
    '(q."lease_until" IS NULL OR (q."lease_until" NOT IN (\'NaN\'::double '
    "precision,'Infinity'::double precision,'-Infinity'::double precision))) "
    'AND coalesce(octet_length(CAST(q."lease_until" AS TEXT)),0)<=64 AND '
    '(q."cancel" IS NOT NULL AND (q."cancel" IS NOT NULL)) AND '
    'coalesce(octet_length(CAST(q."cancel" AS TEXT)),0)<=8 AND (q."budget" '
    'IS NOT NULL AND (q."budget" IS NOT NULL)) AND '
    'coalesce(octet_length(CAST(q."budget" AS TEXT)),0)<=24 AND '
    '(q."reserved" IS NOT NULL AND (q."reserved" IS NOT NULL)) AND '
    'coalesce(octet_length(CAST(q."reserved" AS TEXT)),0)<=24 AND '
    '(q."result" IS NULL OR (octet_length(CAST(q."result" AS TEXT))<=64)) '
    'AND coalesce(octet_length(CAST(q."result" AS TEXT)),0)<=64 AND '
    '(q."error" IS NULL OR (octet_length(CAST(q."error" AS TEXT))<=1200)) '
    'AND coalesce(octet_length(CAST(q."error" AS TEXT)),0)<=1200 AND '
    '(q."actor" IS NULL OR (octet_length(CAST(q."actor" AS TEXT))<=256)) AND '
    'coalesce(octet_length(CAST(q."actor" AS TEXT)),0)<=256 AND '
    '(q."payload_version" IS NOT NULL AND (q."payload_version" IS NOT NULL)) '
    'AND coalesce(octet_length(CAST(q."payload_version" AS TEXT)),0)<=8 AND '
    '(q."execution_config_ref" IS NULL OR (octet_length(CAST(q."execution_con'
    'fig_ref" AS TEXT))<=64)) AND coalesce(octet_length(CAST(q."execution_con'
    'fig_ref" AS TEXT)),0)<=64 AND (q."execution_config_digest" IS NULL OR '
    '(octet_length(CAST(q."execution_config_digest" AS TEXT))<=64)) AND '
    'coalesce(octet_length(CAST(q."execution_config_digest" AS '
    "TEXT)),0)<=64))) "
)


_SQLITE_AR7_ACCOUNT_VALID = (
    ' (q."id" IS NOT NULL AND (typeof(q."id")=\'text\' AND length(q."id")=32 '
    'AND length(CAST(q."id" AS BLOB))=32 AND q."id" NOT GLOB \'*[^0-9a-f]*\') '
    'AND q."organization_id" IS NOT NULL AND '
    '(typeof(q."organization_id")=\'text\' AND length(q."organization_id")=32 '
    'AND length(CAST(q."organization_id" AS BLOB))=32 AND '
    'q."organization_id" NOT GLOB \'*[^0-9a-f]*\') AND q."scope" IS NOT NULL '
    'AND q."scope_id" IS NOT NULL AND (typeof(q."scope_id")=\'text\' AND '
    'length(q."scope_id")=32 AND length(CAST(q."scope_id" AS BLOB))=32 AND '
    'q."scope_id" NOT GLOB \'*[^0-9a-f]*\') AND q."period_start" IS NOT NULL '
    'AND q."period_end" IS NOT NULL AND q."limit_microusd" IS NOT NULL AND '
    'q."held_microusd" IS NOT NULL AND q."accounted_microusd" IS NOT NULL '
    'AND (q."project_id" IS NULL OR (typeof(q."project_id")=\'text\' AND '
    'length(q."project_id")=32 AND length(CAST(q."project_id" AS BLOB))=32 '
    'AND q."project_id" NOT GLOB \'*[^0-9a-f]*\')) AND (q."job_id" IS NULL OR '
    '(typeof(q."job_id")=\'text\' AND length(q."job_id")=32 AND '
    'length(CAST(q."job_id" AS BLOB))=32 AND q."job_id" NOT GLOB '
    "'*[^0-9a-f]*')) AND q.\"opening_held_microusd\" IS NOT NULL AND "
    "(typeof(accounted_microusd)='integer' AND accounted_microusd BETWEEN 0 "
    "AND 9223372036854775807) AND (accounted_microusd<=limit_microusd AND "
    "held_microusd<=limit_microusd-accounted_microusd) AND "
    "(typeof(period_end)='text' AND length(CAST(period_end AS BLOB))=27 AND "
    "period_end GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:["
    "0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z' AND "
    "substr(period_end,1,4) BETWEEN '0001' AND '9999' AND "
    "date(substr(period_end,1,10),'+0 days') IS substr(period_end,1,10) AND "
    "substr(period_end,12,2) BETWEEN '00' AND '23' AND "
    "substr(period_end,15,2) BETWEEN '00' AND '59' AND "
    "substr(period_end,18,2) BETWEEN '00' AND '59') AND "
    "(typeof(held_microusd)='integer' AND held_microusd BETWEEN 0 AND "
    "9223372036854775807) AND (typeof(id)='text' AND length(id)=32 AND "
    "length(CAST(id AS BLOB))=32 AND id NOT GLOB '*[^0-9a-f]*') AND (job_id "
    "IS NULL OR (typeof(job_id)='text' AND length(job_id)=32 AND "
    "length(CAST(job_id AS BLOB))=32 AND job_id NOT GLOB '*[^0-9a-f]*')) AND "
    "(typeof(limit_microusd)='integer' AND limit_microusd BETWEEN 0 AND "
    "9223372036854775807) AND (typeof(opening_held_microusd)='integer' AND "
    "opening_held_microusd BETWEEN 0 AND 9223372036854775807) AND "
    "(typeof(organization_id)='text' AND length(organization_id)=32 AND "
    "length(CAST(organization_id AS BLOB))=32 AND organization_id NOT GLOB "
    "'*[^0-9a-f]*') AND (period_start<period_end) AND (project_id IS NULL OR "
    "(typeof(project_id)='text' AND length(project_id)=32 AND "
    "length(CAST(project_id AS BLOB))=32 AND project_id NOT GLOB "
    "'*[^0-9a-f]*')) AND (scope='organization' OR scope='project' OR "
    "scope='job') AND (typeof(scope_id)='text' AND length(scope_id)=32 AND "
    "length(CAST(scope_id AS BLOB))=32 AND scope_id NOT GLOB '*[^0-9a-f]*') "
    "AND ((scope='organization' AND scope_id=organization_id\n            AND "
    "project_id IS NULL AND job_id IS NULL)\n          OR (scope='project' "
    "AND project_id IS NOT NULL AND scope_id=project_id AND job_id IS NULL)\n "
    "         OR (scope='job' AND project_id IS NOT NULL AND job_id IS NOT "
    "NULL AND scope_id=job_id)) AND (typeof(period_start)='text' AND "
    "length(CAST(period_start AS BLOB))=27 AND period_start GLOB "
    "'[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9]["
    "0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z' AND substr(period_start,1,4) "
    "BETWEEN '0001' AND '9999' AND date(substr(period_start,1,10),'+0 days') "
    "IS substr(period_start,1,10) AND substr(period_start,12,2) BETWEEN '00' "
    "AND '23' AND substr(period_start,15,2) BETWEEN '00' AND '59' AND "
    "substr(period_start,18,2) BETWEEN '00' AND '59')) "
)


_POSTGRESQL_AR6_OPERATION_VALID = (
    ' (q."id" IS NOT NULL AND (q."id" IS NOT NULL AND '
    '(octet_length(CAST(q."id" AS TEXT))<=32)) AND (octet_length(CAST(q."id" '
    'AS TEXT))=32 AND q."id" ~ \'^[0-9a-f]{32}$\') AND q."project_id" IS NOT '
    'NULL AND (q."project_id" IS NOT NULL AND '
    '(octet_length(CAST(q."project_id" AS TEXT))<=32)) AND '
    '(octet_length(CAST(q."project_id" AS TEXT))=32 AND q."project_id" ~ '
    "'^[0-9a-f]{32}$') AND q.\"principal_id\" IS NOT NULL AND "
    '(q."principal_id" IS NOT NULL AND (octet_length(CAST(q."principal_id" '
    'AS TEXT))<=256)) AND q."kind" IS NOT NULL AND (q."kind" IS NOT NULL AND '
    '(octet_length(CAST(q."kind" AS TEXT))<=20)) AND q."client_operation_id" '
    'IS NOT NULL AND (q."client_operation_id" IS NOT NULL AND '
    '(octet_length(CAST(q."client_operation_id" AS TEXT))<=32)) AND '
    '(octet_length(CAST(q."client_operation_id" AS TEXT))=32 AND '
    'q."client_operation_id" ~ \'^[0-9a-f]{32}$\') AND q."request_digest" IS '
    'NOT NULL AND (q."request_digest" IS NOT NULL AND '
    '(octet_length(CAST(q."request_digest" AS TEXT))<=64)) AND '
    '(octet_length(CAST(q."request_digest" AS TEXT))=64 AND '
    'q."request_digest" ~ \'^[0-9a-f]{64}$\') AND q."job_id" IS NOT NULL AND '
    '(q."job_id" IS NOT NULL AND (octet_length(CAST(q."job_id" AS '
    'TEXT))<=32)) AND (octet_length(CAST(q."job_id" AS TEXT))=32 AND '
    'q."job_id" ~ \'^[0-9a-f]{32}$\') AND q."accepted_response" IS NOT NULL '
    'AND (q."accepted_response" IS NOT NULL AND '
    '(octet_length(CAST(q."accepted_response" AS TEXT))<=128)) AND '
    'q."created_at" IS NOT NULL AND (q."created_at" IS NOT NULL AND '
    '(isfinite(q."created_at") AND q."created_at">=TIMESTAMPTZ \'0001-01-01 '
    "00:00:00+00' AND q.\"created_at\"<TIMESTAMPTZ '10000-01-01 00:00:00+00')) "
    'AND q."retain_until" IS NOT NULL AND (q."retain_until" IS NOT NULL AND '
    '(isfinite(q."retain_until") AND q."retain_until">=TIMESTAMPTZ '
    "'0001-01-01 00:00:00+00' AND q.\"retain_until\"<TIMESTAMPTZ '10000-01-01 "
    '00:00:00+00\')) AND q."job_resource_kind" IS NOT NULL AND '
    '(q."job_resource_kind" IS NOT NULL AND '
    '(octet_length(CAST(q."job_resource_kind" AS TEXT))<=20)) AND '
    'q."execution_config_digest" IS NOT NULL AND '
    '(q."execution_config_digest" IS NOT NULL AND '
    '(octet_length(CAST(q."execution_config_digest" AS TEXT))<=64)) AND '
    '(octet_length(CAST(q."execution_config_digest" AS TEXT))=64 AND '
    'q."execution_config_digest" ~ \'^[0-9a-f]{64}$\') AND q."payload_version" '
    'IS NOT NULL AND (q."payload_version" IS NOT NULL AND '
    '(q."payload_version" IS NOT NULL)) AND (q."failure_correlation_id" IS '
    'NULL OR (octet_length(CAST(q."failure_correlation_id" AS TEXT))<=32)) '
    'AND (q."failure_correlation_id" IS NULL OR '
    '(octet_length(CAST(q."failure_correlation_id" AS TEXT))=32 AND '
    "q.\"failure_correlation_id\" ~ '^[0-9a-f]{32}$')) AND (accepted_response "
    '= ((((\'{"job_id":"\'::text || job_id::text) || '
    '\'","operation_id":"\'::text) || id::text) || \'"}\'::text)) AND '
    "(retain_until >= created_at) AND (client_operation_id::text ~ "
    "'^[0-9a-f]{32}$'::text) AND (execution_config_digest::text ~ "
    "'^[0-9a-f]{64}$'::text) AND (failure_correlation_id IS NULL OR "
    "failure_correlation_id::text ~ '^[0-9a-f]{32}$'::text) AND (id::text ~ "
    "'^[0-9a-f]{32}$'::text) AND (job_id::text ~ '^[0-9a-f]{32}$'::text) AND "
    "(job_resource_kind::text = 'job'::text) AND (kind::text = 'run'::text) "
    "AND (payload_version = 2) AND (principal_id::text ~ "
    "'^(oidc:[0-9a-f]{64}|api-key:[0-9a-f]{32})$'::text) AND "
    "(project_id::text ~ '^[0-9a-f]{32}$'::text) AND (request_digest::text ~ "
    "'^[0-9a-f]{64}$'::text)) "
)


_POSTGRESQL_AR7_CALL_VALID = (
    ' (q."id" IS NOT NULL AND (octet_length(CAST(q."id" AS TEXT))=32 AND '
    'q."id" ~ \'^[0-9a-f]{32}$\') AND q."project_id" IS NOT NULL AND '
    '(octet_length(CAST(q."project_id" AS TEXT))=32 AND q."project_id" ~ '
    "'^[0-9a-f]{32}$') AND q.\"job_id\" IS NOT NULL AND "
    '(octet_length(CAST(q."job_id" AS TEXT))=32 AND q."job_id" ~ '
    "'^[0-9a-f]{32}$') AND q.\"logical_call_id\" IS NOT NULL AND "
    '(octet_length(CAST(q."logical_call_id" AS TEXT))=32 AND '
    'q."logical_call_id" ~ \'^[0-9a-f]{32}$\') AND q."purpose" IS NOT NULL AND '
    'q."request_digest" IS NOT NULL AND (octet_length(CAST(q."request_digest"'
    " AS TEXT))=64 AND q.\"request_digest\" ~ '^[0-9a-f]{64}$') AND "
    'q."price_version" IS NOT NULL AND q."state" IS NOT NULL AND '
    'q."reserved_microusd" IS NOT NULL AND q."created_at" IS NOT NULL AND '
    'q."organization_id" IS NOT NULL AND (octet_length(CAST(q."organization_i'
    'd" AS TEXT))=32 AND q."organization_id" ~ \'^[0-9a-f]{32}$\') AND '
    'q."job_resource_kind" IS NOT NULL AND q."lease_generation" IS NOT NULL '
    'AND q."organization_account_id" IS NOT NULL AND '
    '(octet_length(CAST(q."organization_account_id" AS TEXT))=32 AND '
    "q.\"organization_account_id\" ~ '^[0-9a-f]{32}$') AND "
    'q."project_account_id" IS NOT NULL AND '
    '(octet_length(CAST(q."project_account_id" AS TEXT))=32 AND '
    'q."project_account_id" ~ \'^[0-9a-f]{32}$\') AND q."job_account_id" IS '
    'NOT NULL AND (octet_length(CAST(q."job_account_id" AS TEXT))=32 AND '
    "q.\"job_account_id\" ~ '^[0-9a-f]{32}$') AND (isfinite(created_at) AND "
    "EXTRACT(year FROM (created_at AT TIME ZONE 'UTC'::text)) >= 1::numeric "
    "AND EXTRACT(year FROM (created_at AT TIME ZONE 'UTC'::text)) <= "
    "9999::numeric) AND (request_digest ~ '^[0-9a-f]{64}$'::text) AND "
    "(usage_estimate_microusd IS NULL OR usage_estimate_microusd >= 0 AND "
    "usage_estimate_microusd <= '9223372036854775807'::bigint) AND "
    "(lease_generation >= 1 AND lease_generation <= "
    "'9223372036854775807'::bigint) AND (id::text ~ '^[0-9a-f]{32}$'::text) "
    "AND (job_id::text ~ '^[0-9a-f]{32}$'::text) AND (job_account_id::text ~ "
    "'^[0-9a-f]{32}$'::text) AND (job_resource_kind::text = 'job'::text) AND "
    "(logical_call_id::text ~ '^[0-9a-f]{32}$'::text) AND "
    "(organization_account_id::text ~ '^[0-9a-f]{32}$'::text) AND "
    "(organization_id::text ~ '^[0-9a-f]{32}$'::text) AND "
    "(length(price_version::text) <= 128) AND (project_id::text ~ "
    "'^[0-9a-f]{32}$'::text) AND (project_account_id::text ~ "
    "'^[0-9a-f]{32}$'::text) AND (provider_request_id IS NULL OR "
    "length(provider_request_id::text) <= 256) AND (purpose::text = "
    "'continuation'::text OR purpose::text = 'discovery'::text) AND "
    "(reserved_microusd >= 0 AND reserved_microusd <= "
    "'9223372036854775807'::bigint) AND (state::text = 'reserved'::text OR "
    "state::text = 'dispatching'::text OR state::text = 'observed'::text OR "
    "state::text = 'uncertain'::text OR state::text = 'reconciled'::text)) "
)


_POSTGRESQL_AR7_ACCOUNT_VALID = (
    ' (q."id" IS NOT NULL AND (octet_length(CAST(q."id" AS TEXT))=32 AND '
    'q."id" ~ \'^[0-9a-f]{32}$\') AND q."organization_id" IS NOT NULL AND '
    '(octet_length(CAST(q."organization_id" AS TEXT))=32 AND '
    'q."organization_id" ~ \'^[0-9a-f]{32}$\') AND q."scope" IS NOT NULL AND '
    'q."scope_id" IS NOT NULL AND (octet_length(CAST(q."scope_id" AS '
    'TEXT))=32 AND q."scope_id" ~ \'^[0-9a-f]{32}$\') AND q."period_start" IS '
    'NOT NULL AND q."period_end" IS NOT NULL AND q."limit_microusd" IS NOT '
    'NULL AND q."held_microusd" IS NOT NULL AND q."accounted_microusd" IS '
    'NOT NULL AND (q."project_id" IS NULL OR '
    '(octet_length(CAST(q."project_id" AS TEXT))=32 AND q."project_id" ~ '
    "'^[0-9a-f]{32}$')) AND (q.\"job_id\" IS NULL OR "
    '(octet_length(CAST(q."job_id" AS TEXT))=32 AND q."job_id" ~ '
    "'^[0-9a-f]{32}$')) AND q.\"opening_held_microusd\" IS NOT NULL AND "
    "(accounted_microusd >= 0 AND accounted_microusd <= "
    "'9223372036854775807'::bigint) AND (accounted_microusd <= "
    "limit_microusd AND held_microusd <= (limit_microusd - "
    "accounted_microusd)) AND (isfinite(period_end) AND EXTRACT(year FROM "
    "(period_end AT TIME ZONE 'UTC'::text)) >= 1::numeric AND EXTRACT(year "
    "FROM (period_end AT TIME ZONE 'UTC'::text)) <= 9999::numeric) AND "
    "(held_microusd >= 0 AND held_microusd <= '9223372036854775807'::bigint) "
    "AND (id::text ~ '^[0-9a-f]{32}$'::text) AND (job_id IS NULL OR "
    "job_id::text ~ '^[0-9a-f]{32}$'::text) AND (limit_microusd >= 0 AND "
    "limit_microusd <= '9223372036854775807'::bigint) AND "
    "(opening_held_microusd >= 0 AND opening_held_microusd <= "
    "'9223372036854775807'::bigint) AND (organization_id::text ~ "
    "'^[0-9a-f]{32}$'::text) AND (period_start < period_end) AND (project_id "
    "IS NULL OR project_id::text ~ '^[0-9a-f]{32}$'::text) AND (scope::text "
    "= 'organization'::text OR scope::text = 'project'::text OR scope::text "
    "= 'job'::text) AND (scope_id::text ~ '^[0-9a-f]{32}$'::text) AND "
    "(scope::text = 'organization'::text AND scope_id::text = "
    "organization_id::text AND project_id IS NULL AND job_id IS NULL OR "
    "scope::text = 'project'::text AND project_id IS NOT NULL AND "
    "scope_id::text = project_id::text AND job_id IS NULL OR scope::text = "
    "'job'::text AND project_id IS NOT NULL AND job_id IS NOT NULL AND "
    "scope_id::text = job_id::text) AND (isfinite(period_start) AND "
    "EXTRACT(year FROM (period_start AT TIME ZONE 'UTC'::text)) >= "
    "1::numeric AND EXTRACT(year FROM (period_start AT TIME ZONE "
    "'UTC'::text)) <= 9999::numeric)) "
)


_SQLITE_AR7_ENTRY_VALID = (
    ' (q."call_id" IS NOT NULL AND (typeof(q."call_id")=\'text\' AND '
    'length(q."call_id")=32 AND length(CAST(q."call_id" AS BLOB))=32 AND '
    'q."call_id" NOT GLOB \'*[^0-9a-f]*\') AND q."account_id" IS NOT NULL AND '
    '(typeof(q."account_id")=\'text\' AND length(q."account_id")=32 AND '
    'length(CAST(q."account_id" AS BLOB))=32 AND q."account_id" NOT GLOB '
    '\'*[^0-9a-f]*\') AND q."entry_kind" IS NOT NULL AND q."amount_microusd" '
    'IS NOT NULL AND (q."evidence_ref" IS NULL OR '
    '(typeof(q."evidence_ref")=\'text\' AND length(q."evidence_ref")=32 AND '
    'length(CAST(q."evidence_ref" AS BLOB))=32 AND q."evidence_ref" NOT GLOB '
    '\'*[^0-9a-f]*\')) AND q."created_at" IS NOT NULL AND q."project_id" IS '
    "NOT NULL AND (typeof(q.\"project_id\")='text' AND "
    'length(q."project_id")=32 AND length(CAST(q."project_id" AS BLOB))=32 '
    'AND q."project_id" NOT GLOB \'*[^0-9a-f]*\') AND q."evidence_owner_kind" '
    'IS NOT NULL AND q."evidence_role" IS NOT NULL AND '
    "(typeof(account_id)='text' AND length(account_id)=32 AND "
    "length(CAST(account_id AS BLOB))=32 AND account_id NOT GLOB "
    "'*[^0-9a-f]*') AND (typeof(amount_microusd)='integer' AND "
    "amount_microusd BETWEEN 0 AND 9223372036854775807) AND "
    "(typeof(call_id)='text' AND length(call_id)=32 AND length(CAST(call_id "
    "AS BLOB))=32 AND call_id NOT GLOB '*[^0-9a-f]*') AND "
    "(typeof(created_at)='text' AND length(CAST(created_at AS BLOB))=27 AND "
    "created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:["
    "0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z' AND "
    "substr(created_at,1,4) BETWEEN '0001' AND '9999' AND "
    "date(substr(created_at,1,10),'+0 days') IS substr(created_at,1,10) AND "
    "substr(created_at,12,2) BETWEEN '00' AND '23' AND "
    "substr(created_at,15,2) BETWEEN '00' AND '59' AND "
    "substr(created_at,18,2) BETWEEN '00' AND '59') AND (evidence_ref IS "
    "NULL OR (typeof(evidence_ref)='text' AND length(evidence_ref)=32 AND "
    "length(CAST(evidence_ref AS BLOB))=32 AND evidence_ref NOT GLOB "
    "'*[^0-9a-f]*')) AND ((entry_kind='reserve' AND evidence_ref IS NULL)\n   "
    "       OR ((entry_kind='settle' OR entry_kind='release') AND "
    "evidence_ref IS NOT NULL)) AND (entry_kind='reserve' OR "
    "entry_kind='settle' OR entry_kind='release') AND "
    "(evidence_owner_kind='provider_call') AND (typeof(project_id)='text' "
    "AND length(project_id)=32 AND length(CAST(project_id AS BLOB))=32 AND "
    "project_id NOT GLOB '*[^0-9a-f]*') AND "
    "(evidence_role='budget_evidence')) "
)


_POSTGRESQL_AR7_ENTRY_VALID = (
    ' (q."call_id" IS NOT NULL AND (octet_length(CAST(q."call_id" AS '
    'TEXT))=32 AND q."call_id" ~ \'^[0-9a-f]{32}$\') AND q."account_id" IS NOT '
    'NULL AND (octet_length(CAST(q."account_id" AS TEXT))=32 AND '
    'q."account_id" ~ \'^[0-9a-f]{32}$\') AND q."entry_kind" IS NOT NULL AND '
    'q."amount_microusd" IS NOT NULL AND (q."evidence_ref" IS NULL OR '
    '(octet_length(CAST(q."evidence_ref" AS TEXT))=32 AND q."evidence_ref" ~ '
    '\'^[0-9a-f]{32}$\')) AND q."created_at" IS NOT NULL AND q."project_id" IS '
    'NOT NULL AND (octet_length(CAST(q."project_id" AS TEXT))=32 AND '
    'q."project_id" ~ \'^[0-9a-f]{32}$\') AND q."evidence_owner_kind" IS NOT '
    'NULL AND q."evidence_role" IS NOT NULL AND (account_id::text ~ '
    "'^[0-9a-f]{32}$'::text) AND (amount_microusd >= 0 AND amount_microusd "
    "<= '9223372036854775807'::bigint) AND (call_id::text ~ "
    "'^[0-9a-f]{32}$'::text) AND (isfinite(created_at) AND EXTRACT(year FROM "
    "(created_at AT TIME ZONE 'UTC'::text)) >= 1::numeric AND EXTRACT(year "
    "FROM (created_at AT TIME ZONE 'UTC'::text)) <= 9999::numeric) AND "
    "(evidence_ref IS NULL OR evidence_ref::text ~ '^[0-9a-f]{32}$'::text) "
    "AND (entry_kind::text = 'reserve'::text AND evidence_ref IS NULL OR "
    "(entry_kind::text = 'settle'::text OR entry_kind::text = "
    "'release'::text) AND evidence_ref IS NOT NULL) AND (entry_kind::text = "
    "'reserve'::text OR entry_kind::text = 'settle'::text OR "
    "entry_kind::text = 'release'::text) AND (evidence_owner_kind::text = "
    "'provider_call'::text) AND (project_id::text ~ '^[0-9a-f]{32}$'::text) "
    "AND (evidence_role::text = 'budget_evidence'::text)) "
)


_SQLITE_AR6_OBJECT_VALID = (
    ' (typeof(q."id")=\'text\' AND length(q."id")=32 AND length(CAST(q."id" AS '
    "BLOB))=32 AND q.\"id\" NOT GLOB '*[^0-9a-f]*' AND "
    'typeof(q."project_id")=\'text\' AND length(q."project_id")=32 AND '
    'length(CAST(q."project_id" AS BLOB))=32 AND q."project_id" NOT GLOB '
    "'*[^0-9a-f]*' AND typeof(q.\"digest\")='text' AND length(q.\"digest\")=64 "
    'AND length(CAST(q."digest" AS BLOB))=64 AND q."digest" NOT GLOB '
    '\'*[^0-9a-f]*\' AND q."id" IS NOT NULL AND q."project_id" IS NOT NULL AND '
    'q."digest" IS NOT NULL AND q."locator" IS NOT NULL AND '
    'q."format_version" IS NOT NULL AND q."byte_count" IS NOT NULL AND '
    'q."created_at" IS NOT NULL AND q.project_count=1 AND '
    "q.project_id=q.expected_project AND typeof(q.byte_count)='integer' AND "
    "q.byte_count BETWEEN 0 AND 9223372036854775807 AND "
    "typeof(q.format_version)='integer' AND q.format_version=1 AND "
    "typeof(q.created_at)='text' AND length(CAST(q.created_at AS BLOB))<=64 "
    "AND (length(id)=32 AND id NOT GLOB '*[^0-9a-f]*') AND "
    "(length(digest)=64 AND digest NOT GLOB '*[^0-9a-f]*') AND "
    "(length(locator) BETWEEN 1 AND 1024) AND (format_version=1) AND "
    "(byte_count>=0) AND (locator='objects/' || digest\n          OR "
    "locator='objects/' || project_id || '/v1/' || digest)) "
)


_POSTGRESQL_AR6_OBJECT_VALID = (
    ' (octet_length(CAST(q."id" AS TEXT))=32 AND q."id" ~ \'^[0-9a-f]{32}$\' '
    'AND octet_length(CAST(q."project_id" AS TEXT))=32 AND q."project_id" ~ '
    "'^[0-9a-f]{32}$' AND octet_length(CAST(q.\"digest\" AS TEXT))=64 AND "
    'q."digest" ~ \'^[0-9a-f]{64}$\' AND q."id" IS NOT NULL AND q."project_id" '
    'IS NOT NULL AND q."digest" IS NOT NULL AND q."locator" IS NOT NULL AND '
    'q."format_version" IS NOT NULL AND q."byte_count" IS NOT NULL AND '
    'q."created_at" IS NOT NULL AND q.project_count=1 AND '
    "q.project_id=q.expected_project AND q.byte_count BETWEEN 0 AND "
    "9223372036854775807 AND q.format_version=1 AND isfinite(q.created_at) "
    "AND q.created_at>=TIMESTAMPTZ '0001-01-01 00:00:00+00' AND "
    "q.created_at<TIMESTAMPTZ '10000-01-01 00:00:00+00' AND (byte_count >= "
    "0) AND (locator::text = ('objects/'::text || digest::text) OR "
    "locator::text = ((('objects/'::text || project_id::text) || "
    "'/v1/'::text) || digest::text)) AND (digest::text ~ "
    "'^[0-9a-f]{64}$'::text) AND (format_version = 1) AND (id::text ~ "
    "'^[0-9a-f]{32}$'::text) AND (length(locator::text) >= 1 AND "
    "length(locator::text) <= 1024)) "
)


_POSTGRESQL_AR6_REF_VALID = (
    ' (octet_length(CAST(q."project_id" AS TEXT))=32 AND q."project_id" ~ '
    "'^[0-9a-f]{32}$' AND octet_length(CAST(q.\"owner_id\" AS TEXT))=32 AND "
    'q."owner_id" ~ \'^[0-9a-f]{32}$\' AND octet_length(CAST(q."artifact_id" '
    'AS TEXT))=32 AND q."artifact_id" ~ \'^[0-9a-f]{32}$\' AND q."project_id" '
    'IS NOT NULL AND q."owner_kind" IS NOT NULL AND q."owner_id" IS NOT NULL '
    'AND q."artifact_id" IS NOT NULL AND q."role" IS NOT NULL AND '
    "(role::text <> 'budget_evidence'::text OR owner_kind::text = "
    "'provider_call'::text) AND (owner_kind::text = 'run'::text OR "
    "owner_kind::text = 'study'::text OR owner_kind::text = 'job'::text OR "
    "owner_kind::text = 'provider_call'::text) AND (role::text = "
    "'payload'::text OR role::text = 'admission_config'::text OR role::text "
    "= 'task'::text OR role::text = 'event'::text OR role::text = "
    "'checkpoint'::text OR role::text = 'workspace'::text OR role::text = "
    "'file_blob'::text OR role::text = 'evaluation'::text OR role::text = "
    "'result'::text OR role::text = 'study_attachment'::text OR role::text = "
    "'budget_evidence'::text)) "
)


_SQLITE_AR6_SCOPE_VALID = (
    ' (q."resource_kind" IS NOT NULL AND (q."resource_kind" IS NOT NULL AND '
    '(typeof(q."resource_kind")=\'text\' AND length(q."resource_kind")<=20 AND '
    'length(CAST(q."resource_kind" AS BLOB))<=80)) AND q."resource_id" IS '
    'NOT NULL AND (q."resource_id" IS NOT NULL AND '
    '(typeof(q."resource_id")=\'text\' AND length(q."resource_id")<=32 AND '
    'length(CAST(q."resource_id" AS BLOB))<=128)) AND '
    '(typeof(q."resource_id")=\'text\' AND length(q."resource_id")=32 AND '
    'length(CAST(q."resource_id" AS BLOB))=32 AND q."resource_id" NOT GLOB '
    '\'*[^0-9a-f]*\') AND q."project_id" IS NOT NULL AND (q."project_id" IS '
    "NOT NULL AND (typeof(q.\"project_id\")='text' AND "
    'length(q."project_id")<=32 AND length(CAST(q."project_id" AS '
    "BLOB))<=128)) AND (typeof(q.\"project_id\")='text' AND "
    'length(q."project_id")=32 AND length(CAST(q."project_id" AS BLOB))=32 '
    "AND q.\"project_id\" NOT GLOB '*[^0-9a-f]*') AND (resource_kind IN "
    "('run','study','job','key','provider_call')) AND (length(resource_id) = "
    "32 AND resource_id NOT GLOB '*[^0-9a-f]*')) "
)


_SQLITE_AR6_REF_VALID = (
    ' (typeof(q."project_id")=\'text\' AND length(q."project_id")=32 AND '
    'length(CAST(q."project_id" AS BLOB))=32 AND q."project_id" NOT GLOB '
    "'*[^0-9a-f]*' AND typeof(q.\"owner_id\")='text' AND "
    'length(q."owner_id")=32 AND length(CAST(q."owner_id" AS BLOB))=32 AND '
    "q.\"owner_id\" NOT GLOB '*[^0-9a-f]*' AND typeof(q.\"artifact_id\")='text' "
    'AND length(q."artifact_id")=32 AND length(CAST(q."artifact_id" AS '
    'BLOB))=32 AND q."artifact_id" NOT GLOB \'*[^0-9a-f]*\' AND q."project_id" '
    'IS NOT NULL AND q."owner_kind" IS NOT NULL AND q."owner_id" IS NOT NULL '
    'AND q."artifact_id" IS NOT NULL AND q."role" IS NOT NULL AND '
    "(owner_kind='run' OR owner_kind='study' OR owner_kind='job' OR "
    "owner_kind='provider_call') AND (role='payload' OR "
    "role='admission_config' OR role='task' OR role='event' OR "
    "role='checkpoint' OR role='workspace' OR role='file_blob' OR "
    "role='evaluation' OR role='result' OR role='study_attachment' OR "
    "role='budget_evidence') AND (role<>'budget_evidence' OR "
    "owner_kind='provider_call')) "
)


_POSTGRESQL_AR6_SCOPE_VALID = (
    ' (q."resource_kind" IS NOT NULL AND (q."resource_kind" IS NOT NULL AND '
    '(length(q."resource_kind")<=20 AND octet_length(CAST(q."resource_kind" '
    'AS TEXT))<=80)) AND q."resource_id" IS NOT NULL AND (q."resource_id" IS '
    'NOT NULL AND (length(q."resource_id")<=32 AND '
    'octet_length(CAST(q."resource_id" AS TEXT))<=128)) AND '
    '(octet_length(CAST(q."resource_id" AS TEXT))=32 AND q."resource_id" ~ '
    '\'^[0-9a-f]{32}$\') AND q."project_id" IS NOT NULL AND (q."project_id" IS '
    'NOT NULL AND (length(q."project_id")<=32 AND '
    'octet_length(CAST(q."project_id" AS TEXT))<=128)) AND '
    '(octet_length(CAST(q."project_id" AS TEXT))=32 AND q."project_id" ~ '
    "'^[0-9a-f]{32}$') AND (resource_id::text ~ '^[0-9a-f]{32}$'::text) AND "
    "(resource_kind::text = ANY (ARRAY['run'::character varying, "
    "'study'::character varying, 'job'::character varying, 'key'::character "
    "varying, 'provider_call'::character varying]::text[]))) "
)


_SQLITE_AR6_OWNER_VALID = (
    " (typeof(q.owner_id)='text' AND length(q.owner_id)=32 AND "
    "length(CAST(q.owner_id AS BLOB))=32 AND q.owner_id NOT GLOB "
    "'*[^0-9a-f]*') AND (typeof(q.project_id)='text' AND "
    "length(q.project_id)=32 AND length(CAST(q.project_id AS BLOB))=32 AND "
    "q.project_id NOT GLOB '*[^0-9a-f]*') AND "
    "(typeof(q.organization_id)='text' AND length(q.organization_id)=32 AND "
    "length(CAST(q.organization_id AS BLOB))=32 AND q.organization_id NOT "
    "GLOB '*[^0-9a-f]*') AND (q.matched_id=q.owner_id) AND "
    "(q.project_id=q.expected_project) AND (q.matched_project=q.project_id) "
    "AND (q.organization_id=(SELECT id FROM organizations)) "
)


_SQLITE_AR6_ORGANIZATION_VALID = (
    ' (q."id" IS NOT NULL AND (q."id" IS NOT NULL AND (typeof(q."id")=\'text\' '
    'AND length(q."id")<=32 AND length(CAST(q."id" AS BLOB))<=128)) AND '
    '(typeof(q."id")=\'text\' AND length(q."id")=32 AND length(CAST(q."id" AS '
    'BLOB))=32 AND q."id" NOT GLOB \'*[^0-9a-f]*\') AND q."installation_key" '
    'IS NOT NULL AND (q."installation_key" IS NOT NULL AND '
    "(typeof(q.\"installation_key\")='text' AND "
    'length(q."installation_key")<=64 AND length(CAST(q."installation_key" '
    "AS BLOB))<=256)) AND (length(id) = 32 AND id NOT GLOB '*[^0-9a-f]*')) "
)


_POSTGRESQL_AR6_OWNER_VALID = (
    " (octet_length(CAST(q.owner_id AS TEXT))=32 AND q.owner_id ~ "
    "'^[0-9a-f]{32}$') AND (octet_length(CAST(q.project_id AS TEXT))=32 AND "
    "q.project_id ~ '^[0-9a-f]{32}$') AND (octet_length(CAST(q.organization_i"
    "d AS TEXT))=32 AND q.organization_id ~ '^[0-9a-f]{32}$') AND "
    "(q.matched_id=q.owner_id) AND (q.project_id=q.expected_project) AND "
    "(q.matched_project=q.project_id) AND (q.organization_id=(SELECT id FROM "
    "organizations)) "
)


_POSTGRESQL_AR6_ORGANIZATION_VALID = (
    ' (q."id" IS NOT NULL AND (q."id" IS NOT NULL AND (length(q."id")<=32 '
    'AND octet_length(CAST(q."id" AS TEXT))<=128)) AND '
    '(octet_length(CAST(q."id" AS TEXT))=32 AND q."id" ~ \'^[0-9a-f]{32}$\') '
    'AND q."installation_key" IS NOT NULL AND (q."installation_key" IS NOT '
    'NULL AND (length(q."installation_key")<=64 AND '
    'octet_length(CAST(q."installation_key" AS TEXT))<=256)) AND (id::text ~ '
    "'^[0-9a-f]{32}$'::text)) "
)


_SQLITE_AR6_PROJECT_VALID = (
    " (typeof(q.id)='text' AND length(q.id)=32 AND length(CAST(q.id AS "
    "BLOB))=32 AND q.id NOT GLOB '*[^0-9a-f]*') AND "
    "(typeof(q.organization_id)='text' AND length(q.organization_id)=32 AND "
    "length(CAST(q.organization_id AS BLOB))=32 AND q.organization_id NOT "
    "GLOB '*[^0-9a-f]*') AND (q.id=q.required_id) AND "
    "(q.organization_id=(SELECT id FROM organizations)) "
)


_POSTGRESQL_AR6_PROJECT_VALID = (
    " (octet_length(CAST(q.id AS TEXT))=32 AND q.id ~ '^[0-9a-f]{32}$') AND "
    "(octet_length(CAST(q.organization_id AS TEXT))=32 AND q.organization_id "
    "~ '^[0-9a-f]{32}$') AND (q.id=q.required_id) AND "
    "(q.organization_id=(SELECT id FROM organizations)) "
)


_SQLITE_AR6_JOB_CANDIDATE = (
    "WITH candidate AS MATERIALIZED (SELECT "
    '"id","kind","created","payload","status","owner","lease_until","cancel",'
    '"budget","reserved","result","error","actor","payload_version","executio'
    'n_config_ref","execution_config_digest" FROM "jobs" ORDER BY "id" LIMIT '
    "65537) "
)


_SQLITE_AR6_OPERATION_CANDIDATE = (
    "WITH candidate AS MATERIALIZED (SELECT "
    '"id","project_id","principal_id","kind","client_operation_id","request_d'
    'igest","job_id","accepted_response","created_at","retain_until","job_res'
    'ource_kind","execution_config_digest","payload_version","failure_correla'
    'tion_id" FROM "operations" ORDER BY "id" LIMIT 65537) '
)


_SQLITE_AR6_OPERATION_PROJECTION = "".join(
    (
        ("SELECT count(*) AS candidate_rows, coalesce(sum(CASE WHEN"),
        _SQLITE_AR6_OPERATION_VALID,
        (
            "THEN 0 ELSE 1 END),0) AS invalid_rows, "
            'coalesce(sum((coalesce(length(CAST(q."id" AS '
            'BLOB)),0)+coalesce(length(CAST(q."project_id" AS '
            'BLOB)),0)+coalesce(length(CAST(q."principal_id" AS '
            'BLOB)),0)+coalesce(length(CAST(q."kind" AS '
            'BLOB)),0)+coalesce(length(CAST(q."client_operation_id" AS '
            'BLOB)),0)+coalesce(length(CAST(q."request_digest" AS '
            'BLOB)),0)+coalesce(length(CAST(q."job_id" AS '
            'BLOB)),0)+coalesce(length(CAST(q."accepted_response" AS '
            'BLOB)),0)+coalesce(length(CAST(q."created_at" AS '
            'BLOB)),0)+coalesce(length(CAST(q."retain_until" AS '
            'BLOB)),0)+coalesce(length(CAST(q."job_resource_kind" AS '
            'BLOB)),0)+coalesce(length(CAST(q."execution_config_digest" AS '
            'BLOB)),0)+coalesce(length(CAST(q."payload_version" AS '
            'BLOB)),0)+coalesce(length(CAST(q."failure_correlation_id" AS '
            "BLOB)),0))),0) AS native_bytes FROM candidate AS q\n"
        ),
    )
)


_SQLITE_AR6_OPERATION_PROJECTION_2 = "".join(
    (
        ("SELECT CASE WHEN"),
        _SQLITE_AR6_OPERATION_VALID,
        ('THEN q."id" END AS "id",CASE WHEN'),
        _SQLITE_AR6_OPERATION_VALID,
        ('THEN q."project_id" END AS "project_id",CASE WHEN'),
        _SQLITE_AR6_OPERATION_VALID,
        ('THEN q."principal_id" END AS "principal_id",CASE WHEN'),
        _SQLITE_AR6_OPERATION_VALID,
        ('THEN q."kind" END AS "kind",CASE WHEN'),
        _SQLITE_AR6_OPERATION_VALID,
        ('THEN q."client_operation_id" END AS "client_operation_id",CASE WHEN'),
        _SQLITE_AR6_OPERATION_VALID,
        ('THEN q."request_digest" END AS "request_digest",CASE WHEN'),
        _SQLITE_AR6_OPERATION_VALID,
        ('THEN q."job_id" END AS "job_id",CASE WHEN'),
        _SQLITE_AR6_OPERATION_VALID,
        ('THEN q."accepted_response" END AS "accepted_response",CASE WHEN'),
        _SQLITE_AR6_OPERATION_VALID,
        ('THEN q."created_at" END AS "created_at",CASE WHEN'),
        _SQLITE_AR6_OPERATION_VALID,
        ('THEN q."retain_until" END AS "retain_until",CASE WHEN'),
        _SQLITE_AR6_OPERATION_VALID,
        ('THEN q."job_resource_kind" END AS "job_resource_kind",CASE WHEN'),
        _SQLITE_AR6_OPERATION_VALID,
        ('THEN q."execution_config_digest" END AS "execution_config_digest",CASE WHEN'),
        _SQLITE_AR6_OPERATION_VALID,
        ('THEN q."payload_version" END AS "payload_version",CASE WHEN'),
        _SQLITE_AR6_OPERATION_VALID,
        ('THEN q."failure_correlation_id" END AS "failure_correlation_id",CASE WHEN'),
        _SQLITE_AR6_OPERATION_VALID,
        ('THEN 0 ELSE 1 END AS invalid FROM candidate AS q ORDER BY q."id"\n'),
    )
)


_SQLITE_AR6_SCOPE_CANDIDATE = (
    "WITH candidate AS MATERIALIZED (SELECT "
    '"resource_kind","resource_id","project_id" FROM resource_scopes WHERE '
    "resource_kind='job' ORDER BY resource_id LIMIT 65537) "
)


_SQLITE_AR6_SCOPE_PROJECTION = "".join(
    (
        ("SELECT count(*) AS candidate_rows, coalesce(sum(CASE WHEN"),
        _SQLITE_AR6_SCOPE_VALID,
        (
            "THEN 0 ELSE 1 END),0) AS invalid_rows, "
            'coalesce(sum((coalesce(length(CAST(q."resource_kind" AS '
            'BLOB)),0)+coalesce(length(CAST(q."resource_id" AS '
            'BLOB)),0)+coalesce(length(CAST(q."project_id" AS BLOB)),0))),0) AS '
            "native_bytes FROM candidate AS q\n"
        ),
    )
)


_SQLITE_AR6_SCOPE_PROJECTION_2 = "".join(
    (
        ("SELECT CASE WHEN"),
        _SQLITE_AR6_SCOPE_VALID,
        ('THEN q."resource_kind" END AS "resource_kind",CASE WHEN'),
        _SQLITE_AR6_SCOPE_VALID,
        ('THEN q."resource_id" END AS "resource_id",CASE WHEN'),
        _SQLITE_AR6_SCOPE_VALID,
        ('THEN q."project_id" END AS "project_id",CASE WHEN'),
        _SQLITE_AR6_SCOPE_VALID,
        (
            "THEN 0 ELSE 1 END AS invalid FROM candidate AS q ORDER BY "
            'q."resource_kind",q."resource_id"\n'
        ),
    )
)


_SQLITE_AR6_ORGANIZATION_CANDIDATE = (
    'WITH candidate AS MATERIALIZED (SELECT "id","installation_key" FROM '
    '"organizations" ORDER BY "id" LIMIT 2) '
)


_SQLITE_AR6_ORGANIZATION_PROJECTION = "".join(
    (
        ("SELECT count(*) AS candidate_rows, coalesce(sum(CASE WHEN"),
        _SQLITE_AR6_ORGANIZATION_VALID,
        (
            "THEN 0 ELSE 1 END),0) AS invalid_rows, "
            'coalesce(sum((coalesce(length(CAST(q."id" AS '
            'BLOB)),0)+coalesce(length(CAST(q."installation_key" AS '
            "BLOB)),0))),0) AS native_bytes FROM candidate AS q\n"
        ),
    )
)


_SQLITE_AR6_ORGANIZATION_PROJECTION_2 = "".join(
    (
        ("SELECT CASE WHEN"),
        _SQLITE_AR6_ORGANIZATION_VALID,
        ('THEN q."id" END AS "id",CASE WHEN'),
        _SQLITE_AR6_ORGANIZATION_VALID,
        ('THEN q."installation_key" END AS "installation_key",CASE WHEN'),
        _SQLITE_AR6_ORGANIZATION_VALID,
        ('THEN 0 ELSE 1 END AS invalid FROM candidate AS q ORDER BY q."id"\n'),
    )
)


_POSTGRESQL_AR6_OPERATION_PROJECTION = "".join(
    (
        ("SELECT count(*) AS candidate_rows, coalesce(sum(CASE WHEN"),
        _POSTGRESQL_AR6_OPERATION_VALID,
        (
            "THEN 0 ELSE 1 END),0) AS invalid_rows, "
            'coalesce(sum((coalesce(octet_length(CAST(q."id" AS '
            'TEXT)),0)+coalesce(octet_length(CAST(q."project_id" AS '
            'TEXT)),0)+coalesce(octet_length(CAST(q."principal_id" AS '
            'TEXT)),0)+coalesce(octet_length(CAST(q."kind" AS '
            'TEXT)),0)+coalesce(octet_length(CAST(q."client_operation_id" AS '
            'TEXT)),0)+coalesce(octet_length(CAST(q."request_digest" AS '
            'TEXT)),0)+coalesce(octet_length(CAST(q."job_id" AS '
            'TEXT)),0)+coalesce(octet_length(CAST(q."accepted_response" AS '
            'TEXT)),0)+coalesce(octet_length(CAST(to_char(q."created_at" AT TIME '
            "ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"') AS "
            'TEXT)),0)+coalesce(octet_length(CAST(to_char(q."retain_until" AT '
            "TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"') AS "
            'TEXT)),0)+coalesce(octet_length(CAST(q."job_resource_kind" AS '
            'TEXT)),0)+coalesce(octet_length(CAST(q."execution_config_digest" AS '
            'TEXT)),0)+coalesce(octet_length(CAST(q."payload_version" AS '
            'TEXT)),0)+coalesce(octet_length(CAST(q."failure_correlation_id" AS '
            "TEXT)),0))),0) AS native_bytes FROM candidate AS q\n"
        ),
    )
)


_POSTGRESQL_AR6_OPERATION_PROJECTION_2 = "".join(
    (
        ("SELECT CASE WHEN"),
        _POSTGRESQL_AR6_OPERATION_VALID,
        ('THEN q."id" END AS "id",CASE WHEN'),
        _POSTGRESQL_AR6_OPERATION_VALID,
        ('THEN q."project_id" END AS "project_id",CASE WHEN'),
        _POSTGRESQL_AR6_OPERATION_VALID,
        ('THEN q."principal_id" END AS "principal_id",CASE WHEN'),
        _POSTGRESQL_AR6_OPERATION_VALID,
        ('THEN q."kind" END AS "kind",CASE WHEN'),
        _POSTGRESQL_AR6_OPERATION_VALID,
        ('THEN q."client_operation_id" END AS "client_operation_id",CASE WHEN'),
        _POSTGRESQL_AR6_OPERATION_VALID,
        ('THEN q."request_digest" END AS "request_digest",CASE WHEN'),
        _POSTGRESQL_AR6_OPERATION_VALID,
        ('THEN q."job_id" END AS "job_id",CASE WHEN'),
        _POSTGRESQL_AR6_OPERATION_VALID,
        ('THEN q."accepted_response" END AS "accepted_response",CASE WHEN'),
        _POSTGRESQL_AR6_OPERATION_VALID,
        (
            "THEN to_char(q.\"created_at\" AT TIME ZONE 'UTC', "
            '\'YYYY-MM-DD"T"HH24:MI:SS.US"Z"\') END AS "created_at",CASE WHEN'
        ),
        _POSTGRESQL_AR6_OPERATION_VALID,
        (
            "THEN to_char(q.\"retain_until\" AT TIME ZONE 'UTC', "
            '\'YYYY-MM-DD"T"HH24:MI:SS.US"Z"\') END AS "retain_until",CASE WHEN'
        ),
        _POSTGRESQL_AR6_OPERATION_VALID,
        ('THEN q."job_resource_kind" END AS "job_resource_kind",CASE WHEN'),
        _POSTGRESQL_AR6_OPERATION_VALID,
        ('THEN q."execution_config_digest" END AS "execution_config_digest",CASE WHEN'),
        _POSTGRESQL_AR6_OPERATION_VALID,
        ('THEN q."payload_version" END AS "payload_version",CASE WHEN'),
        _POSTGRESQL_AR6_OPERATION_VALID,
        ('THEN q."failure_correlation_id" END AS "failure_correlation_id",CASE WHEN'),
        _POSTGRESQL_AR6_OPERATION_VALID,
        ('THEN 0 ELSE 1 END AS invalid FROM candidate AS q ORDER BY q."id"\n'),
    )
)


_POSTGRESQL_AR6_SCOPE_PROJECTION = "".join(
    (
        ("SELECT count(*) AS candidate_rows, coalesce(sum(CASE WHEN"),
        _POSTGRESQL_AR6_SCOPE_VALID,
        (
            "THEN 0 ELSE 1 END),0) AS invalid_rows, "
            'coalesce(sum((coalesce(octet_length(CAST(q."resource_kind" AS '
            'TEXT)),0)+coalesce(octet_length(CAST(q."resource_id" AS '
            'TEXT)),0)+coalesce(octet_length(CAST(q."project_id" AS '
            "TEXT)),0))),0) AS native_bytes FROM candidate AS q\n"
        ),
    )
)


_POSTGRESQL_AR6_SCOPE_PROJECTION_2 = "".join(
    (
        ("SELECT CASE WHEN"),
        _POSTGRESQL_AR6_SCOPE_VALID,
        ('THEN q."resource_kind" END AS "resource_kind",CASE WHEN'),
        _POSTGRESQL_AR6_SCOPE_VALID,
        ('THEN q."resource_id" END AS "resource_id",CASE WHEN'),
        _POSTGRESQL_AR6_SCOPE_VALID,
        ('THEN q."project_id" END AS "project_id",CASE WHEN'),
        _POSTGRESQL_AR6_SCOPE_VALID,
        (
            "THEN 0 ELSE 1 END AS invalid FROM candidate AS q ORDER BY "
            'q."resource_kind",q."resource_id"\n'
        ),
    )
)


_POSTGRESQL_AR6_ORGANIZATION_PROJECTION = "".join(
    (
        ("SELECT count(*) AS candidate_rows, coalesce(sum(CASE WHEN"),
        _POSTGRESQL_AR6_ORGANIZATION_VALID,
        (
            "THEN 0 ELSE 1 END),0) AS invalid_rows, "
            'coalesce(sum((coalesce(octet_length(CAST(q."id" AS '
            'TEXT)),0)+coalesce(octet_length(CAST(q."installation_key" AS '
            "TEXT)),0))),0) AS native_bytes FROM candidate AS q\n"
        ),
    )
)


_POSTGRESQL_AR6_ORGANIZATION_PROJECTION_2 = "".join(
    (
        ("SELECT CASE WHEN"),
        _POSTGRESQL_AR6_ORGANIZATION_VALID,
        ('THEN q."id" END AS "id",CASE WHEN'),
        _POSTGRESQL_AR6_ORGANIZATION_VALID,
        ('THEN q."installation_key" END AS "installation_key",CASE WHEN'),
        _POSTGRESQL_AR6_ORGANIZATION_VALID,
        ('THEN 0 ELSE 1 END AS invalid FROM candidate AS q ORDER BY q."id"\n'),
    )
)


_SQLITE_AR7_ACCOUNT_CANDIDATE = (
    "WITH candidate AS MATERIALIZED (SELECT "
    '"id","organization_id","scope","scope_id","period_start","period_end","l'
    'imit_microusd","held_microusd","accounted_microusd","project_id","job_id'
    '","opening_held_microusd" FROM "budget_accounts" ORDER BY "id" LIMIT '
    "4097) "
)


_SQLITE_AR7_CALL_CANDIDATE = (
    "WITH candidate AS MATERIALIZED (SELECT "
    '"id","project_id","job_id","logical_call_id","purpose","request_digest",'
    '"price_version","state","reserved_microusd","usage_estimate_microusd","p'
    'rovider_request_id","created_at","organization_id","job_resource_kind","'
    'lease_generation","organization_account_id","project_account_id","job_ac'
    'count_id" FROM "provider_calls" ORDER BY "id" LIMIT 65537) '
)


_SQLITE_AR7_ENTRY_CANDIDATE = (
    "WITH candidate AS MATERIALIZED (SELECT "
    '"call_id","account_id","entry_kind","amount_microusd","evidence_ref","cr'
    'eated_at","project_id","evidence_owner_kind","evidence_role" FROM '
    '"budget_entries" ORDER BY "call_id","account_id","entry_kind" LIMIT '
    "65537) "
)


_SQLITE_AR7_JOB_CANDIDATE = (
    "WITH candidate AS MATERIALIZED (SELECT "
    '"id","kind","created","payload","status","owner","lease_until","cancel",'
    '"budget","reserved","result","error","actor","payload_version","executio'
    'n_config_ref","execution_config_digest","lease_generation","legacy_reser'
    'ved_microusd" FROM "jobs" ORDER BY "id" LIMIT 65537) '
)


_SQLITE_AR7_SCOPE_CANDIDATE = (
    "WITH candidate AS MATERIALIZED (SELECT "
    '"resource_kind","resource_id","project_id" FROM (SELECT * FROM (SELECT '
    '"resource_kind","resource_id","project_id" FROM resource_scopes WHERE '
    "resource_kind='job' ORDER BY resource_id LIMIT 65537) AS job_prefix "
    'UNION ALL SELECT * FROM (SELECT "resource_kind","resource_id","project_i'
    "d\" FROM resource_scopes WHERE resource_kind='provider_call' ORDER BY "
    "resource_id LIMIT 65537) AS call_prefix) AS both_prefixes ORDER BY "
    "resource_kind,resource_id LIMIT 65537) "
)


_SQLITE_AR6_OWNER_PROJECTION = "".join(
    (
        ("SELECT count(*) AS owner_rows,coalesce(sum(CASE WHEN"),
        _SQLITE_AR6_OWNER_VALID,
        ("THEN 0 ELSE 1 END),0) AS invalid_rows FROM owner_rows q\n"),
    )
)


_SQLITE_AR6_OWNER_OWNER_ROWS = (
    ",owner_rows AS MATERIALIZED (SELECT s.project_id,'job' AS "
    "owner_kind,j.id AS owner_id,s.resource_id AS matched_id,s.project_id AS "
    "expected_project,p.id AS matched_project,p.organization_id FROM jbase j "
    "LEFT JOIN resource_scopes s ON s.resource_kind='job' AND "
    "s.resource_id=j.id LEFT JOIN projects p ON p.id=s.project_id)"
)


_SQLITE_AR6_REF_REF_CANDIDATE = (
    ",ref_candidate AS MATERIALIZED (SELECT "
    'r."project_id",r."owner_kind",r."owner_id",r."artifact_id",r."role" '
    "FROM owner_rows o CROSS JOIN artifact_refs r WHERE "
    "r.project_id=o.project_id AND r.owner_kind=o.owner_kind AND "
    "r.owner_id=o.owner_id LIMIT 65537) "
)


_SQLITE_AR6_REF_PROJECTION = "".join(
    (
        ("SELECT count(*) AS candidate_rows,coalesce(sum(CASE WHEN"),
        _SQLITE_AR6_REF_VALID,
        (
            "THEN 0 ELSE 1 END),0) AS invalid_rows,coalesce(sum((coalesce(length("
            'CAST(q."project_id" AS BLOB)),0)+coalesce(length(CAST(q."owner_kind"'
            ' AS BLOB)),0)+coalesce(length(CAST(q."owner_id" AS '
            'BLOB)),0)+coalesce(length(CAST(q."artifact_id" AS '
            'BLOB)),0)+coalesce(length(CAST(q."role" AS BLOB)),0))),0) AS '
            "native_bytes FROM ref_candidate q\n"
        ),
    )
)


_SQLITE_AR6_REF_PROJECTION_2 = "".join(
    (
        ("SELECT CASE WHEN"),
        _SQLITE_AR6_REF_VALID,
        ('THEN q."project_id" END AS "project_id",CASE WHEN'),
        _SQLITE_AR6_REF_VALID,
        ('THEN q."owner_kind" END AS "owner_kind",CASE WHEN'),
        _SQLITE_AR6_REF_VALID,
        ('THEN q."owner_id" END AS "owner_id",CASE WHEN'),
        _SQLITE_AR6_REF_VALID,
        ('THEN q."artifact_id" END AS "artifact_id",CASE WHEN'),
        _SQLITE_AR6_REF_VALID,
        ('THEN q."role" END AS "role",CASE WHEN'),
        _SQLITE_AR6_REF_VALID,
        (
            "THEN 0 ELSE 1 END AS invalid FROM ref_candidate q ORDER BY "
            'q."project_id",q."owner_kind",q."owner_id",q."artifact_id",q."role"\n'
        ),
    )
)


_SQLITE_AR6_REF_REF_CANDIDATE_2 = (
    ",ref_candidate AS MATERIALIZED (SELECT "
    'r."project_id",r."owner_kind",r."owner_id",r."artifact_id",r."role" '
    "FROM owner_rows o CROSS JOIN artifact_refs r WHERE "
    "r.project_id=o.project_id AND r.owner_kind=o.owner_kind AND "
    "r.owner_id=o.owner_id LIMIT 65537)"
)


_SQLITE_AR6_OBJECT_OBJECT_KEYS = (
    ",object_keys AS MATERIALIZED (SELECT artifact_id,min(project_id) AS "
    "expected_project,count(DISTINCT project_id) AS project_count FROM "
    "ref_candidate WHERE role IN ('admission_config','budget_evidence') "
    "GROUP BY artifact_id)"
)


_SQLITE_AR6_OBJECT_OBJECT_CANDIDATE = (
    ",object_candidate AS MATERIALIZED (SELECT "
    'o."id",o."project_id",o."digest",o."locator",o."format_version",o."byte_'
    'count",o."created_at",k.expected_project,k.project_count FROM '
    "object_keys k LEFT JOIN artifact_objects o ON o.id=k.artifact_id) "
)


_SQLITE_AR6_OBJECT_PROJECTION = "".join(
    (
        ("SELECT count(*) AS candidate_rows,coalesce(sum(CASE WHEN"),
        _SQLITE_AR6_OBJECT_VALID,
        (
            "THEN 0 ELSE 1 END),0) AS invalid_rows,coalesce(sum((coalesce(length("
            'CAST(q."id" AS BLOB)),0)+coalesce(length(CAST(q."project_id" AS '
            'BLOB)),0)+coalesce(length(CAST(q."digest" AS '
            'BLOB)),0)+coalesce(length(CAST(q."locator" AS '
            'BLOB)),0)+coalesce(length(CAST(q."format_version" AS '
            'BLOB)),0)+coalesce(length(CAST(q."byte_count" AS '
            'BLOB)),0)+coalesce(length(CAST(q."created_at" AS BLOB)),0))),0) AS '
            "native_bytes FROM object_candidate q\n"
        ),
    )
)


_SQLITE_AR6_OBJECT_PROJECTION_2 = "".join(
    (
        ("SELECT CASE WHEN"),
        _SQLITE_AR6_OBJECT_VALID,
        ('THEN q."id" END AS "id",CASE WHEN'),
        _SQLITE_AR6_OBJECT_VALID,
        ('THEN q."project_id" END AS "project_id",CASE WHEN'),
        _SQLITE_AR6_OBJECT_VALID,
        ('THEN q."digest" END AS "digest",CASE WHEN'),
        _SQLITE_AR6_OBJECT_VALID,
        ('THEN q."locator" END AS "locator",CASE WHEN'),
        _SQLITE_AR6_OBJECT_VALID,
        ('THEN q."format_version" END AS "format_version",CASE WHEN'),
        _SQLITE_AR6_OBJECT_VALID,
        ('THEN q."byte_count" END AS "byte_count",CASE WHEN'),
        _SQLITE_AR6_OBJECT_VALID,
        ('THEN q."created_at" END AS "created_at",CASE WHEN'),
        _SQLITE_AR6_OBJECT_VALID,
        ('THEN 0 ELSE 1 END AS invalid FROM object_candidate q ORDER BY q."id"\n'),
    )
)


_SQLITE_AR6_PROJECT_PROJECT_KEYS = (
    "WITH project_keys AS MATERIALIZED (SELECT project_id FROM (SELECT "
    "project_id FROM operations ORDER BY id LIMIT 65537) op UNION SELECT "
    "project_id FROM (SELECT project_id FROM resource_scopes WHERE "
    "resource_kind='job' ORDER BY resource_id LIMIT 65537) s)"
)


_SQLITE_AR6_PROJECT_PROJECT_CANDIDATE = (
    ",project_candidate AS MATERIALIZED (SELECT "
    "p.id,p.organization_id,k.project_id AS required_id FROM project_keys k "
    "LEFT JOIN projects p ON p.id=k.project_id) "
)


_SQLITE_AR6_PROJECT_PROJECTION = "".join(
    (
        ("SELECT count(*) AS candidate_rows,coalesce(sum(CASE WHEN"),
        _SQLITE_AR6_PROJECT_VALID,
        (
            "THEN 0 ELSE 1 END),0) AS invalid_rows,coalesce(sum((coalesce(length("
            'CAST(q."id" AS BLOB)),0)+coalesce(length(CAST(q."organization_id" '
            "AS BLOB)),0))),0) AS native_bytes FROM project_candidate q\n"
        ),
    )
)


_SQLITE_AR6_PROJECT_PROJECTION_2 = "".join(
    (
        ("SELECT CASE WHEN"),
        _SQLITE_AR6_PROJECT_VALID,
        ('THEN q."id" END AS "id",CASE WHEN'),
        _SQLITE_AR6_PROJECT_VALID,
        ('THEN q."organization_id" END AS "organization_id",CASE WHEN'),
        _SQLITE_AR6_PROJECT_VALID,
        ('THEN 0 ELSE 1 END AS invalid FROM project_candidate q ORDER BY q."id"\n'),
    )
)


_POSTGRESQL_AR6_OWNER_PROJECTION = "".join(
    (
        ("SELECT count(*) AS owner_rows,coalesce(sum(CASE WHEN"),
        _POSTGRESQL_AR6_OWNER_VALID,
        ("THEN 0 ELSE 1 END),0) AS invalid_rows FROM owner_rows q\n"),
    )
)


_POSTGRESQL_AR6_OWNER_OWNER_ROWS = (
    ",owner_rows AS MATERIALIZED (SELECT s.project_id,'job' AS "
    "owner_kind,j.id AS owner_id,s.resource_id AS matched_id,s.project_id AS "
    "expected_project,p.id AS matched_project,p.organization_id FROM jbase j "
    "LEFT JOIN LATERAL (SELECT resource_id,project_id FROM resource_scopes "
    "WHERE resource_kind='job' AND resource_id=j.id LIMIT 1) s ON TRUE LEFT "
    "JOIN LATERAL (SELECT id,organization_id FROM projects WHERE "
    "id=s.project_id LIMIT 1) p ON TRUE)"
)


_POSTGRESQL_AR6_REF_REF_CANDIDATE = (
    ",ref_candidate AS MATERIALIZED (SELECT "
    'r."project_id",r."owner_kind",r."owner_id",r."artifact_id",r."role" '
    "FROM owner_rows o CROSS JOIN LATERAL (SELECT "
    'x."project_id",x."owner_kind",x."owner_id",x."artifact_id",x."role" '
    "FROM artifact_refs x WHERE x.project_id=o.project_id AND "
    "x.owner_kind=o.owner_kind AND x.owner_id=o.owner_id ORDER BY "
    "x.artifact_id,x.role LIMIT 65537) r LIMIT 65537) "
)


_POSTGRESQL_AR6_REF_PROJECTION = "".join(
    (
        ("SELECT count(*) AS candidate_rows,coalesce(sum(CASE WHEN"),
        _POSTGRESQL_AR6_REF_VALID,
        (
            "THEN 0 ELSE 1 END),0) AS invalid_rows,coalesce(sum((coalesce(octet_l"
            'ength(CAST(q."project_id" AS TEXT)),0)+coalesce(octet_length(CAST(q.'
            '"owner_kind" AS TEXT)),0)+coalesce(octet_length(CAST(q."owner_id" '
            'AS TEXT)),0)+coalesce(octet_length(CAST(q."artifact_id" AS '
            'TEXT)),0)+coalesce(octet_length(CAST(q."role" AS TEXT)),0))),0) AS '
            "native_bytes FROM ref_candidate q\n"
        ),
    )
)


_POSTGRESQL_AR6_REF_PROJECTION_2 = "".join(
    (
        ("SELECT CASE WHEN"),
        _POSTGRESQL_AR6_REF_VALID,
        ('THEN q."project_id" END AS "project_id",CASE WHEN'),
        _POSTGRESQL_AR6_REF_VALID,
        ('THEN q."owner_kind" END AS "owner_kind",CASE WHEN'),
        _POSTGRESQL_AR6_REF_VALID,
        ('THEN q."owner_id" END AS "owner_id",CASE WHEN'),
        _POSTGRESQL_AR6_REF_VALID,
        ('THEN q."artifact_id" END AS "artifact_id",CASE WHEN'),
        _POSTGRESQL_AR6_REF_VALID,
        ('THEN q."role" END AS "role",CASE WHEN'),
        _POSTGRESQL_AR6_REF_VALID,
        (
            "THEN 0 ELSE 1 END AS invalid FROM ref_candidate q ORDER BY "
            'q."project_id",q."owner_kind",q."owner_id",q."artifact_id",q."role"\n'
        ),
    )
)


_POSTGRESQL_AR6_REF_REF_CANDIDATE_2 = (
    ",ref_candidate AS MATERIALIZED (SELECT "
    'r."project_id",r."owner_kind",r."owner_id",r."artifact_id",r."role" '
    "FROM owner_rows o CROSS JOIN LATERAL (SELECT "
    'x."project_id",x."owner_kind",x."owner_id",x."artifact_id",x."role" '
    "FROM artifact_refs x WHERE x.project_id=o.project_id AND "
    "x.owner_kind=o.owner_kind AND x.owner_id=o.owner_id ORDER BY "
    "x.artifact_id,x.role LIMIT 65537) r LIMIT 65537)"
)


_POSTGRESQL_AR6_OBJECT_OBJECT_CANDIDATE = (
    ",object_candidate AS MATERIALIZED (SELECT "
    'o."id",o."project_id",o."digest",o."locator",o."format_version",o."byte_'
    'count",o."created_at",k.expected_project,k.project_count FROM '
    "object_keys k LEFT JOIN LATERAL (SELECT "
    '"id","project_id","digest","locator","format_version","byte_count","crea'
    'ted_at" FROM artifact_objects WHERE id=k.artifact_id LIMIT 1) o ON '
    "TRUE) "
)


_POSTGRESQL_AR6_OBJECT_PROJECTION = "".join(
    (
        ("SELECT count(*) AS candidate_rows,coalesce(sum(CASE WHEN"),
        _POSTGRESQL_AR6_OBJECT_VALID,
        (
            "THEN 0 ELSE 1 END),0) AS invalid_rows,coalesce(sum((coalesce(octet_l"
            'ength(CAST(q."id" AS TEXT)),0)+coalesce(octet_length(CAST(q."project'
            '_id" AS TEXT)),0)+coalesce(octet_length(CAST(q."digest" AS '
            'TEXT)),0)+coalesce(octet_length(CAST(q."locator" AS '
            'TEXT)),0)+coalesce(octet_length(CAST(q."format_version" AS '
            'TEXT)),0)+coalesce(octet_length(CAST(q."byte_count" AS '
            'TEXT)),0)+coalesce(octet_length(CAST(to_char(q."created_at" AT TIME '
            "ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"') AS TEXT)),0))),0) AS "
            "native_bytes FROM object_candidate q\n"
        ),
    )
)


_POSTGRESQL_AR6_OBJECT_PROJECTION_2 = "".join(
    (
        ("SELECT CASE WHEN"),
        _POSTGRESQL_AR6_OBJECT_VALID,
        ('THEN q."id" END AS "id",CASE WHEN'),
        _POSTGRESQL_AR6_OBJECT_VALID,
        ('THEN q."project_id" END AS "project_id",CASE WHEN'),
        _POSTGRESQL_AR6_OBJECT_VALID,
        ('THEN q."digest" END AS "digest",CASE WHEN'),
        _POSTGRESQL_AR6_OBJECT_VALID,
        ('THEN q."locator" END AS "locator",CASE WHEN'),
        _POSTGRESQL_AR6_OBJECT_VALID,
        ('THEN q."format_version" END AS "format_version",CASE WHEN'),
        _POSTGRESQL_AR6_OBJECT_VALID,
        ('THEN q."byte_count" END AS "byte_count",CASE WHEN'),
        _POSTGRESQL_AR6_OBJECT_VALID,
        (
            "THEN to_char(q.\"created_at\" AT TIME ZONE 'UTC', "
            '\'YYYY-MM-DD"T"HH24:MI:SS.US"Z"\') END AS "created_at",CASE WHEN'
        ),
        _POSTGRESQL_AR6_OBJECT_VALID,
        ('THEN 0 ELSE 1 END AS invalid FROM object_candidate q ORDER BY q."id"\n'),
    )
)


_POSTGRESQL_AR6_PROJECT_PROJECT_CANDIDATE = (
    ",project_candidate AS MATERIALIZED (SELECT "
    "p.id,p.organization_id,k.project_id AS required_id FROM project_keys k "
    "LEFT JOIN LATERAL (SELECT id,organization_id FROM projects WHERE "
    "id=k.project_id LIMIT 1) p ON TRUE) "
)


_POSTGRESQL_AR6_PROJECT_PROJECTION = "".join(
    (
        ("SELECT count(*) AS candidate_rows,coalesce(sum(CASE WHEN"),
        _POSTGRESQL_AR6_PROJECT_VALID,
        (
            "THEN 0 ELSE 1 END),0) AS invalid_rows,coalesce(sum((coalesce(octet_l"
            'ength(CAST(q."id" AS TEXT)),0)+coalesce(octet_length(CAST(q."organiz'
            'ation_id" AS TEXT)),0))),0) AS native_bytes FROM project_candidate '
            "q\n"
        ),
    )
)


_POSTGRESQL_AR6_PROJECT_PROJECTION_2 = "".join(
    (
        ("SELECT CASE WHEN"),
        _POSTGRESQL_AR6_PROJECT_VALID,
        ('THEN q."id" END AS "id",CASE WHEN'),
        _POSTGRESQL_AR6_PROJECT_VALID,
        ('THEN q."organization_id" END AS "organization_id",CASE WHEN'),
        _POSTGRESQL_AR6_PROJECT_VALID,
        ('THEN 0 ELSE 1 END AS invalid FROM project_candidate q ORDER BY q."id"\n'),
    )
)


_SQLITE_AR7_OWNER_OWNER_ROWS = (
    ",owner_rows AS MATERIALIZED (SELECT s.project_id,'job' AS "
    "owner_kind,j.id AS owner_id,s.resource_id AS matched_id,s.project_id AS "
    "expected_project,p.id AS matched_project,p.organization_id FROM jbase j "
    "LEFT JOIN resource_scopes s ON s.resource_kind='job' AND "
    "s.resource_id=j.id LEFT JOIN projects p ON p.id=s.project_id UNION ALL "
    "SELECT s.project_id,'provider_call' AS owner_kind,c.id AS "
    "owner_id,s.resource_id AS matched_id,c.project_id AS "
    "expected_project,p.id AS matched_project,p.organization_id FROM cbase c "
    "LEFT JOIN resource_scopes s ON s.resource_kind='provider_call' AND "
    "s.resource_id=c.id LEFT JOIN projects p ON p.id=s.project_id)"
)


_SQLITE_AR7_PROJECT_PROJECT_KEYS = (
    ",project_keys AS MATERIALIZED (SELECT project_id FROM (SELECT "
    "project_id FROM budget_accounts ORDER BY id LIMIT 4097) a WHERE "
    "project_id IS NOT NULL UNION SELECT project_id FROM cbase UNION SELECT "
    "project_id FROM (SELECT project_id FROM budget_entries ORDER BY "
    "call_id,account_id,entry_kind LIMIT 65537) be UNION SELECT project_id "
    "FROM (SELECT project_id FROM operations ORDER BY id LIMIT 65537) op "
    "UNION SELECT project_id FROM (SELECT project_id FROM resource_scopes "
    "WHERE resource_kind='job' ORDER BY resource_id LIMIT 65537) s UNION "
    "SELECT project_id FROM (SELECT project_id FROM resource_scopes WHERE "
    "resource_kind='provider_call' ORDER BY resource_id LIMIT 65537) s)"
)


_POSTGRESQL_AR7_OWNER_OWNER_ROWS = (
    ",owner_rows AS MATERIALIZED (SELECT s.project_id,'job' AS "
    "owner_kind,j.id AS owner_id,s.resource_id AS matched_id,s.project_id AS "
    "expected_project,p.id AS matched_project,p.organization_id FROM jbase j "
    "LEFT JOIN LATERAL (SELECT resource_id,project_id FROM resource_scopes "
    "WHERE resource_kind='job' AND resource_id=j.id LIMIT 1) s ON TRUE LEFT "
    "JOIN LATERAL (SELECT id,organization_id FROM projects WHERE "
    "id=s.project_id LIMIT 1) p ON TRUE UNION ALL SELECT "
    "s.project_id,'provider_call' AS owner_kind,c.id AS "
    "owner_id,s.resource_id AS matched_id,c.project_id AS "
    "expected_project,p.id AS matched_project,p.organization_id FROM cbase c "
    "LEFT JOIN LATERAL (SELECT resource_id,project_id FROM resource_scopes "
    "WHERE resource_kind='provider_call' AND resource_id=c.id LIMIT 1) s ON "
    "TRUE LEFT JOIN LATERAL (SELECT id,organization_id FROM projects WHERE "
    "id=s.project_id LIMIT 1) p ON TRUE)"
)


SQL: dict[tuple[str, str, str], str] = {
    ("ar6", "sqlite", "financial_base_job_gate"): "".join(
        (
            _SQLITE_AR6_JOB_CANDIDATE,
            ("SELECT count(*) AS candidate_rows, coalesce(sum(CASE WHEN"),
            _SQLITE_AR6_JOB_VALID,
            (
                "THEN 0 ELSE 1 END),0) AS invalid_rows, "
                'coalesce(sum((coalesce(length(CAST(q."id" AS '
                'BLOB)),0)+coalesce(length(CAST(q."kind" AS '
                'BLOB)),0)+coalesce(length(CAST(q."created" AS '
                'BLOB)),0)+coalesce(length(CAST(q."payload" AS '
                'BLOB)),0)+coalesce(length(CAST(q."status" AS '
                'BLOB)),0)+coalesce(length(CAST(q."owner" AS '
                'BLOB)),0)+coalesce(length(CAST(q."lease_until" AS '
                'BLOB)),0)+coalesce(length(CAST(q."cancel" AS '
                'BLOB)),0)+coalesce(length(CAST(q."budget" AS '
                'BLOB)),0)+coalesce(length(CAST(q."reserved" AS '
                'BLOB)),0)+coalesce(length(CAST(q."result" AS '
                'BLOB)),0)+coalesce(length(CAST(q."error" AS '
                'BLOB)),0)+coalesce(length(CAST(q."actor" AS '
                'BLOB)),0)+coalesce(length(CAST(q."payload_version" AS '
                'BLOB)),0)+coalesce(length(CAST(q."execution_config_ref" AS '
                'BLOB)),0)+coalesce(length(CAST(q."execution_config_digest" AS '
                "BLOB)),0))),0) AS native_bytes FROM candidate AS q\n"
            ),
        )
    ),
    ("ar6", "sqlite", "financial_base_job_body"): "".join(
        (
            _SQLITE_AR6_JOB_CANDIDATE,
            ("SELECT CASE WHEN"),
            _SQLITE_AR6_JOB_VALID,
            ('THEN q."id" END AS "id",CASE WHEN'),
            _SQLITE_AR6_JOB_VALID,
            ('THEN q."kind" END AS "kind",CASE WHEN'),
            _SQLITE_AR6_JOB_VALID,
            ('THEN q."created" END AS "created",CASE WHEN'),
            _SQLITE_AR6_JOB_VALID,
            ('THEN q."payload" END AS "payload",CASE WHEN'),
            _SQLITE_AR6_JOB_VALID,
            ('THEN q."status" END AS "status",CASE WHEN'),
            _SQLITE_AR6_JOB_VALID,
            ('THEN q."owner" END AS "owner",CASE WHEN'),
            _SQLITE_AR6_JOB_VALID,
            ('THEN q."lease_until" END AS "lease_until",CASE WHEN'),
            _SQLITE_AR6_JOB_VALID,
            ('THEN q."cancel" END AS "cancel",CASE WHEN'),
            _SQLITE_AR6_JOB_VALID,
            ('THEN q."budget" END AS "budget",CASE WHEN'),
            _SQLITE_AR6_JOB_VALID,
            ('THEN q."reserved" END AS "reserved",CASE WHEN'),
            _SQLITE_AR6_JOB_VALID,
            ('THEN q."result" END AS "result",CASE WHEN'),
            _SQLITE_AR6_JOB_VALID,
            ('THEN q."error" END AS "error",CASE WHEN'),
            _SQLITE_AR6_JOB_VALID,
            ('THEN q."actor" END AS "actor",CASE WHEN'),
            _SQLITE_AR6_JOB_VALID,
            ('THEN q."payload_version" END AS "payload_version",CASE WHEN'),
            _SQLITE_AR6_JOB_VALID,
            ('THEN q."execution_config_ref" END AS "execution_config_ref",CASE WHEN'),
            _SQLITE_AR6_JOB_VALID,
            ('THEN q."execution_config_digest" END AS "execution_config_digest",CASE WHEN'),
            _SQLITE_AR6_JOB_VALID,
            ('THEN 0 ELSE 1 END AS invalid FROM candidate AS q ORDER BY q."id"\n'),
        )
    ),
    ("ar6", "sqlite", "financial_base_operation_gate"): "".join(
        (
            _SQLITE_AR6_OPERATION_CANDIDATE,
            _SQLITE_AR6_OPERATION_PROJECTION,
        )
    ),
    ("ar6", "sqlite", "financial_base_operation_body"): "".join(
        (
            _SQLITE_AR6_OPERATION_CANDIDATE,
            _SQLITE_AR6_OPERATION_PROJECTION_2,
        )
    ),
    ("ar6", "sqlite", "financial_base_scope_gate"): "".join(
        (
            _SQLITE_AR6_SCOPE_CANDIDATE,
            _SQLITE_AR6_SCOPE_PROJECTION,
        )
    ),
    ("ar6", "sqlite", "financial_base_scope_body"): "".join(
        (
            _SQLITE_AR6_SCOPE_CANDIDATE,
            _SQLITE_AR6_SCOPE_PROJECTION_2,
        )
    ),
    ("ar6", "sqlite", "financial_base_organization_gate"): "".join(
        (
            _SQLITE_AR6_ORGANIZATION_CANDIDATE,
            _SQLITE_AR6_ORGANIZATION_PROJECTION,
        )
    ),
    ("ar6", "sqlite", "financial_base_organization_body"): "".join(
        (
            _SQLITE_AR6_ORGANIZATION_CANDIDATE,
            _SQLITE_AR6_ORGANIZATION_PROJECTION_2,
        )
    ),
    ("ar6", "postgresql", "financial_base_job_gate"): "".join(
        (
            _SQLITE_AR6_JOB_CANDIDATE,
            ("SELECT count(*) AS candidate_rows, coalesce(sum(CASE WHEN"),
            _POSTGRESQL_AR6_JOB_VALID,
            (
                "THEN 0 ELSE 1 END),0) AS invalid_rows, "
                'coalesce(sum((coalesce(octet_length(CAST(q."id" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(q."kind" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(q."created" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(q."payload" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(q."status" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(q."owner" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(q."lease_until" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(q."cancel" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(q."budget" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(q."reserved" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(q."result" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(q."error" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(q."actor" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(q."payload_version" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(q."execution_config_ref" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(q."execution_config_digest" AS '
                "TEXT)),0))),0) AS native_bytes FROM candidate AS q\n"
            ),
        )
    ),
    ("ar6", "postgresql", "financial_base_job_body"): "".join(
        (
            _SQLITE_AR6_JOB_CANDIDATE,
            ("SELECT CASE WHEN"),
            _POSTGRESQL_AR6_JOB_VALID,
            ('THEN q."id" END AS "id",CASE WHEN'),
            _POSTGRESQL_AR6_JOB_VALID,
            ('THEN q."kind" END AS "kind",CASE WHEN'),
            _POSTGRESQL_AR6_JOB_VALID,
            ('THEN q."created" END AS "created",CASE WHEN'),
            _POSTGRESQL_AR6_JOB_VALID,
            ('THEN q."payload" END AS "payload",CASE WHEN'),
            _POSTGRESQL_AR6_JOB_VALID,
            ('THEN q."status" END AS "status",CASE WHEN'),
            _POSTGRESQL_AR6_JOB_VALID,
            ('THEN q."owner" END AS "owner",CASE WHEN'),
            _POSTGRESQL_AR6_JOB_VALID,
            ('THEN q."lease_until" END AS "lease_until",CASE WHEN'),
            _POSTGRESQL_AR6_JOB_VALID,
            ('THEN q."cancel" END AS "cancel",CASE WHEN'),
            _POSTGRESQL_AR6_JOB_VALID,
            ('THEN q."budget" END AS "budget",CASE WHEN'),
            _POSTGRESQL_AR6_JOB_VALID,
            ('THEN q."reserved" END AS "reserved",CASE WHEN'),
            _POSTGRESQL_AR6_JOB_VALID,
            ('THEN q."result" END AS "result",CASE WHEN'),
            _POSTGRESQL_AR6_JOB_VALID,
            ('THEN q."error" END AS "error",CASE WHEN'),
            _POSTGRESQL_AR6_JOB_VALID,
            ('THEN q."actor" END AS "actor",CASE WHEN'),
            _POSTGRESQL_AR6_JOB_VALID,
            ('THEN q."payload_version" END AS "payload_version",CASE WHEN'),
            _POSTGRESQL_AR6_JOB_VALID,
            ('THEN q."execution_config_ref" END AS "execution_config_ref",CASE WHEN'),
            _POSTGRESQL_AR6_JOB_VALID,
            ('THEN q."execution_config_digest" END AS "execution_config_digest",CASE WHEN'),
            _POSTGRESQL_AR6_JOB_VALID,
            ('THEN 0 ELSE 1 END AS invalid FROM candidate AS q ORDER BY q."id"\n'),
        )
    ),
    ("ar6", "postgresql", "financial_base_operation_gate"): "".join(
        (
            _SQLITE_AR6_OPERATION_CANDIDATE,
            _POSTGRESQL_AR6_OPERATION_PROJECTION,
        )
    ),
    ("ar6", "postgresql", "financial_base_operation_body"): "".join(
        (
            _SQLITE_AR6_OPERATION_CANDIDATE,
            _POSTGRESQL_AR6_OPERATION_PROJECTION_2,
        )
    ),
    ("ar6", "postgresql", "financial_base_scope_gate"): "".join(
        (
            _SQLITE_AR6_SCOPE_CANDIDATE,
            _POSTGRESQL_AR6_SCOPE_PROJECTION,
        )
    ),
    ("ar6", "postgresql", "financial_base_scope_body"): "".join(
        (
            _SQLITE_AR6_SCOPE_CANDIDATE,
            _POSTGRESQL_AR6_SCOPE_PROJECTION_2,
        )
    ),
    ("ar6", "postgresql", "financial_base_organization_gate"): "".join(
        (
            _SQLITE_AR6_ORGANIZATION_CANDIDATE,
            _POSTGRESQL_AR6_ORGANIZATION_PROJECTION,
        )
    ),
    ("ar6", "postgresql", "financial_base_organization_body"): "".join(
        (
            _SQLITE_AR6_ORGANIZATION_CANDIDATE,
            _POSTGRESQL_AR6_ORGANIZATION_PROJECTION_2,
        )
    ),
    ("ar7", "sqlite", "financial_base_account_gate"): "".join(
        (
            _SQLITE_AR7_ACCOUNT_CANDIDATE,
            ("SELECT count(*) AS candidate_rows, coalesce(sum(CASE WHEN"),
            _SQLITE_AR7_ACCOUNT_VALID,
            (
                "THEN 0 ELSE 1 END),0) AS invalid_rows, "
                'coalesce(sum((coalesce(length(CAST(q."id" AS '
                'BLOB)),0)+coalesce(length(CAST(q."organization_id" AS '
                'BLOB)),0)+coalesce(length(CAST(q."scope" AS '
                'BLOB)),0)+coalesce(length(CAST(q."scope_id" AS '
                'BLOB)),0)+coalesce(length(CAST(q."period_start" AS '
                'BLOB)),0)+coalesce(length(CAST(q."period_end" AS '
                'BLOB)),0)+coalesce(length(CAST(q."limit_microusd" AS '
                'BLOB)),0)+coalesce(length(CAST(q."held_microusd" AS '
                'BLOB)),0)+coalesce(length(CAST(q."accounted_microusd" AS '
                'BLOB)),0)+coalesce(length(CAST(q."project_id" AS '
                'BLOB)),0)+coalesce(length(CAST(q."job_id" AS '
                'BLOB)),0)+coalesce(length(CAST(q."opening_held_microusd" AS '
                "BLOB)),0))),0) AS native_bytes FROM candidate AS q\n"
            ),
        )
    ),
    ("ar7", "sqlite", "financial_base_account_body"): "".join(
        (
            _SQLITE_AR7_ACCOUNT_CANDIDATE,
            ("SELECT CASE WHEN"),
            _SQLITE_AR7_ACCOUNT_VALID,
            ('THEN q."id" END AS "id",CASE WHEN'),
            _SQLITE_AR7_ACCOUNT_VALID,
            ('THEN q."organization_id" END AS "organization_id",CASE WHEN'),
            _SQLITE_AR7_ACCOUNT_VALID,
            ('THEN q."scope" END AS "scope",CASE WHEN'),
            _SQLITE_AR7_ACCOUNT_VALID,
            ('THEN q."scope_id" END AS "scope_id",CASE WHEN'),
            _SQLITE_AR7_ACCOUNT_VALID,
            ('THEN q."period_start" END AS "period_start",CASE WHEN'),
            _SQLITE_AR7_ACCOUNT_VALID,
            ('THEN q."period_end" END AS "period_end",CASE WHEN'),
            _SQLITE_AR7_ACCOUNT_VALID,
            ('THEN q."limit_microusd" END AS "limit_microusd",CASE WHEN'),
            _SQLITE_AR7_ACCOUNT_VALID,
            ('THEN q."held_microusd" END AS "held_microusd",CASE WHEN'),
            _SQLITE_AR7_ACCOUNT_VALID,
            ('THEN q."accounted_microusd" END AS "accounted_microusd",CASE WHEN'),
            _SQLITE_AR7_ACCOUNT_VALID,
            ('THEN q."project_id" END AS "project_id",CASE WHEN'),
            _SQLITE_AR7_ACCOUNT_VALID,
            ('THEN q."job_id" END AS "job_id",CASE WHEN'),
            _SQLITE_AR7_ACCOUNT_VALID,
            ('THEN q."opening_held_microusd" END AS "opening_held_microusd",CASE WHEN'),
            _SQLITE_AR7_ACCOUNT_VALID,
            ('THEN 0 ELSE 1 END AS invalid FROM candidate AS q ORDER BY q."id"\n'),
        )
    ),
    ("ar7", "sqlite", "financial_base_call_gate"): "".join(
        (
            _SQLITE_AR7_CALL_CANDIDATE,
            ("SELECT count(*) AS candidate_rows, coalesce(sum(CASE WHEN"),
            _SQLITE_AR7_CALL_VALID,
            (
                "THEN 0 ELSE 1 END),0) AS invalid_rows, "
                'coalesce(sum((coalesce(length(CAST(q."id" AS '
                'BLOB)),0)+coalesce(length(CAST(q."project_id" AS '
                'BLOB)),0)+coalesce(length(CAST(q."job_id" AS '
                'BLOB)),0)+coalesce(length(CAST(q."logical_call_id" AS '
                'BLOB)),0)+coalesce(length(CAST(q."purpose" AS '
                'BLOB)),0)+coalesce(length(CAST(q."request_digest" AS '
                'BLOB)),0)+coalesce(length(CAST(q."price_version" AS '
                'BLOB)),0)+coalesce(length(CAST(q."state" AS '
                'BLOB)),0)+coalesce(length(CAST(q."reserved_microusd" AS '
                'BLOB)),0)+coalesce(length(CAST(q."usage_estimate_microusd" AS '
                'BLOB)),0)+coalesce(length(CAST(q."provider_request_id" AS '
                'BLOB)),0)+coalesce(length(CAST(q."created_at" AS '
                'BLOB)),0)+coalesce(length(CAST(q."organization_id" AS '
                'BLOB)),0)+coalesce(length(CAST(q."job_resource_kind" AS '
                'BLOB)),0)+coalesce(length(CAST(q."lease_generation" AS '
                'BLOB)),0)+coalesce(length(CAST(q."organization_account_id" AS '
                'BLOB)),0)+coalesce(length(CAST(q."project_account_id" AS '
                'BLOB)),0)+coalesce(length(CAST(q."job_account_id" AS BLOB)),0))),0) '
                "AS native_bytes FROM candidate AS q\n"
            ),
        )
    ),
    ("ar7", "sqlite", "financial_base_call_body"): "".join(
        (
            _SQLITE_AR7_CALL_CANDIDATE,
            ("SELECT CASE WHEN"),
            _SQLITE_AR7_CALL_VALID,
            ('THEN q."id" END AS "id",CASE WHEN'),
            _SQLITE_AR7_CALL_VALID,
            ('THEN q."project_id" END AS "project_id",CASE WHEN'),
            _SQLITE_AR7_CALL_VALID,
            ('THEN q."job_id" END AS "job_id",CASE WHEN'),
            _SQLITE_AR7_CALL_VALID,
            ('THEN q."logical_call_id" END AS "logical_call_id",CASE WHEN'),
            _SQLITE_AR7_CALL_VALID,
            ('THEN q."purpose" END AS "purpose",CASE WHEN'),
            _SQLITE_AR7_CALL_VALID,
            ('THEN q."request_digest" END AS "request_digest",CASE WHEN'),
            _SQLITE_AR7_CALL_VALID,
            ('THEN q."price_version" END AS "price_version",CASE WHEN'),
            _SQLITE_AR7_CALL_VALID,
            ('THEN q."state" END AS "state",CASE WHEN'),
            _SQLITE_AR7_CALL_VALID,
            ('THEN q."reserved_microusd" END AS "reserved_microusd",CASE WHEN'),
            _SQLITE_AR7_CALL_VALID,
            ('THEN q."usage_estimate_microusd" END AS "usage_estimate_microusd",CASE WHEN'),
            _SQLITE_AR7_CALL_VALID,
            ('THEN q."provider_request_id" END AS "provider_request_id",CASE WHEN'),
            _SQLITE_AR7_CALL_VALID,
            ('THEN q."created_at" END AS "created_at",CASE WHEN'),
            _SQLITE_AR7_CALL_VALID,
            ('THEN q."organization_id" END AS "organization_id",CASE WHEN'),
            _SQLITE_AR7_CALL_VALID,
            ('THEN q."job_resource_kind" END AS "job_resource_kind",CASE WHEN'),
            _SQLITE_AR7_CALL_VALID,
            ('THEN q."lease_generation" END AS "lease_generation",CASE WHEN'),
            _SQLITE_AR7_CALL_VALID,
            ('THEN q."organization_account_id" END AS "organization_account_id",CASE WHEN'),
            _SQLITE_AR7_CALL_VALID,
            ('THEN q."project_account_id" END AS "project_account_id",CASE WHEN'),
            _SQLITE_AR7_CALL_VALID,
            ('THEN q."job_account_id" END AS "job_account_id",CASE WHEN'),
            _SQLITE_AR7_CALL_VALID,
            ('THEN 0 ELSE 1 END AS invalid FROM candidate AS q ORDER BY q."id"\n'),
        )
    ),
    ("ar7", "sqlite", "financial_base_entry_gate"): "".join(
        (
            _SQLITE_AR7_ENTRY_CANDIDATE,
            ("SELECT count(*) AS candidate_rows, coalesce(sum(CASE WHEN"),
            _SQLITE_AR7_ENTRY_VALID,
            (
                "THEN 0 ELSE 1 END),0) AS invalid_rows, "
                'coalesce(sum((coalesce(length(CAST(q."call_id" AS '
                'BLOB)),0)+coalesce(length(CAST(q."account_id" AS '
                'BLOB)),0)+coalesce(length(CAST(q."entry_kind" AS '
                'BLOB)),0)+coalesce(length(CAST(q."amount_microusd" AS '
                'BLOB)),0)+coalesce(length(CAST(q."evidence_ref" AS '
                'BLOB)),0)+coalesce(length(CAST(q."created_at" AS '
                'BLOB)),0)+coalesce(length(CAST(q."project_id" AS '
                'BLOB)),0)+coalesce(length(CAST(q."evidence_owner_kind" AS '
                'BLOB)),0)+coalesce(length(CAST(q."evidence_role" AS BLOB)),0))),0) '
                "AS native_bytes FROM candidate AS q\n"
            ),
        )
    ),
    ("ar7", "sqlite", "financial_base_entry_body"): "".join(
        (
            _SQLITE_AR7_ENTRY_CANDIDATE,
            ("SELECT CASE WHEN"),
            _SQLITE_AR7_ENTRY_VALID,
            ('THEN q."call_id" END AS "call_id",CASE WHEN'),
            _SQLITE_AR7_ENTRY_VALID,
            ('THEN q."account_id" END AS "account_id",CASE WHEN'),
            _SQLITE_AR7_ENTRY_VALID,
            ('THEN q."entry_kind" END AS "entry_kind",CASE WHEN'),
            _SQLITE_AR7_ENTRY_VALID,
            ('THEN q."amount_microusd" END AS "amount_microusd",CASE WHEN'),
            _SQLITE_AR7_ENTRY_VALID,
            ('THEN q."evidence_ref" END AS "evidence_ref",CASE WHEN'),
            _SQLITE_AR7_ENTRY_VALID,
            ('THEN q."created_at" END AS "created_at",CASE WHEN'),
            _SQLITE_AR7_ENTRY_VALID,
            ('THEN q."project_id" END AS "project_id",CASE WHEN'),
            _SQLITE_AR7_ENTRY_VALID,
            ('THEN q."evidence_owner_kind" END AS "evidence_owner_kind",CASE WHEN'),
            _SQLITE_AR7_ENTRY_VALID,
            ('THEN q."evidence_role" END AS "evidence_role",CASE WHEN'),
            _SQLITE_AR7_ENTRY_VALID,
            (
                "THEN 0 ELSE 1 END AS invalid FROM candidate AS q ORDER BY "
                'q."call_id",q."account_id",q."entry_kind"\n'
            ),
        )
    ),
    ("ar7", "sqlite", "financial_base_job_gate"): "".join(
        (
            _SQLITE_AR7_JOB_CANDIDATE,
            ("SELECT count(*) AS candidate_rows, coalesce(sum(CASE WHEN"),
            _SQLITE_AR7_JOB_VALID,
            (
                "THEN 0 ELSE 1 END),0) AS invalid_rows, "
                'coalesce(sum((coalesce(length(CAST(q."id" AS '
                'BLOB)),0)+coalesce(length(CAST(q."kind" AS '
                'BLOB)),0)+coalesce(length(CAST(q."created" AS '
                'BLOB)),0)+coalesce(length(CAST(q."payload" AS '
                'BLOB)),0)+coalesce(length(CAST(q."status" AS '
                'BLOB)),0)+coalesce(length(CAST(q."owner" AS '
                'BLOB)),0)+coalesce(length(CAST(q."lease_until" AS '
                'BLOB)),0)+coalesce(length(CAST(q."cancel" AS '
                'BLOB)),0)+coalesce(length(CAST(q."budget" AS '
                'BLOB)),0)+coalesce(length(CAST(q."reserved" AS '
                'BLOB)),0)+coalesce(length(CAST(q."result" AS '
                'BLOB)),0)+coalesce(length(CAST(q."error" AS '
                'BLOB)),0)+coalesce(length(CAST(q."actor" AS '
                'BLOB)),0)+coalesce(length(CAST(q."payload_version" AS '
                'BLOB)),0)+coalesce(length(CAST(q."execution_config_ref" AS '
                'BLOB)),0)+coalesce(length(CAST(q."execution_config_digest" AS '
                'BLOB)),0)+coalesce(length(CAST(q."lease_generation" AS '
                'BLOB)),0)+coalesce(length(CAST(q."legacy_reserved_microusd" AS '
                "BLOB)),0))),0) AS native_bytes FROM candidate AS q\n"
            ),
        )
    ),
    ("ar7", "sqlite", "financial_base_job_body"): "".join(
        (
            _SQLITE_AR7_JOB_CANDIDATE,
            ("SELECT CASE WHEN"),
            _SQLITE_AR7_JOB_VALID,
            ('THEN q."id" END AS "id",CASE WHEN'),
            _SQLITE_AR7_JOB_VALID,
            ('THEN q."kind" END AS "kind",CASE WHEN'),
            _SQLITE_AR7_JOB_VALID,
            ('THEN q."created" END AS "created",CASE WHEN'),
            _SQLITE_AR7_JOB_VALID,
            ('THEN q."payload" END AS "payload",CASE WHEN'),
            _SQLITE_AR7_JOB_VALID,
            ('THEN q."status" END AS "status",CASE WHEN'),
            _SQLITE_AR7_JOB_VALID,
            ('THEN q."owner" END AS "owner",CASE WHEN'),
            _SQLITE_AR7_JOB_VALID,
            ('THEN q."lease_until" END AS "lease_until",CASE WHEN'),
            _SQLITE_AR7_JOB_VALID,
            ('THEN q."cancel" END AS "cancel",CASE WHEN'),
            _SQLITE_AR7_JOB_VALID,
            ('THEN q."budget" END AS "budget",CASE WHEN'),
            _SQLITE_AR7_JOB_VALID,
            ('THEN q."reserved" END AS "reserved",CASE WHEN'),
            _SQLITE_AR7_JOB_VALID,
            ('THEN q."result" END AS "result",CASE WHEN'),
            _SQLITE_AR7_JOB_VALID,
            ('THEN q."error" END AS "error",CASE WHEN'),
            _SQLITE_AR7_JOB_VALID,
            ('THEN q."actor" END AS "actor",CASE WHEN'),
            _SQLITE_AR7_JOB_VALID,
            ('THEN q."payload_version" END AS "payload_version",CASE WHEN'),
            _SQLITE_AR7_JOB_VALID,
            ('THEN q."execution_config_ref" END AS "execution_config_ref",CASE WHEN'),
            _SQLITE_AR7_JOB_VALID,
            ('THEN q."execution_config_digest" END AS "execution_config_digest",CASE WHEN'),
            _SQLITE_AR7_JOB_VALID,
            ('THEN q."lease_generation" END AS "lease_generation",CASE WHEN'),
            _SQLITE_AR7_JOB_VALID,
            ('THEN q."legacy_reserved_microusd" END AS "legacy_reserved_microusd",CASE WHEN'),
            _SQLITE_AR7_JOB_VALID,
            ('THEN 0 ELSE 1 END AS invalid FROM candidate AS q ORDER BY q."id"\n'),
        )
    ),
    ("ar7", "sqlite", "financial_base_operation_gate"): "".join(
        (
            _SQLITE_AR6_OPERATION_CANDIDATE,
            _SQLITE_AR6_OPERATION_PROJECTION,
        )
    ),
    ("ar7", "sqlite", "financial_base_operation_body"): "".join(
        (
            _SQLITE_AR6_OPERATION_CANDIDATE,
            _SQLITE_AR6_OPERATION_PROJECTION_2,
        )
    ),
    ("ar7", "sqlite", "financial_base_scope_gate"): "".join(
        (
            _SQLITE_AR7_SCOPE_CANDIDATE,
            _SQLITE_AR6_SCOPE_PROJECTION,
        )
    ),
    ("ar7", "sqlite", "financial_base_scope_body"): "".join(
        (
            _SQLITE_AR7_SCOPE_CANDIDATE,
            _SQLITE_AR6_SCOPE_PROJECTION_2,
        )
    ),
    ("ar7", "sqlite", "financial_base_organization_gate"): "".join(
        (
            _SQLITE_AR6_ORGANIZATION_CANDIDATE,
            _SQLITE_AR6_ORGANIZATION_PROJECTION,
        )
    ),
    ("ar7", "sqlite", "financial_base_organization_body"): "".join(
        (
            _SQLITE_AR6_ORGANIZATION_CANDIDATE,
            _SQLITE_AR6_ORGANIZATION_PROJECTION_2,
        )
    ),
    ("ar7", "postgresql", "financial_base_account_gate"): "".join(
        (
            _SQLITE_AR7_ACCOUNT_CANDIDATE,
            ("SELECT count(*) AS candidate_rows, coalesce(sum(CASE WHEN"),
            _POSTGRESQL_AR7_ACCOUNT_VALID,
            (
                "THEN 0 ELSE 1 END),0) AS invalid_rows, "
                'coalesce(sum((coalesce(octet_length(CAST(q."id" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(q."organization_id" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(q."scope" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(q."scope_id" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(to_char(q."period_start" AT '
                "TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"') AS "
                'TEXT)),0)+coalesce(octet_length(CAST(to_char(q."period_end" AT TIME '
                "ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"') AS "
                'TEXT)),0)+coalesce(octet_length(CAST(q."limit_microusd" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(q."held_microusd" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(q."accounted_microusd" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(q."project_id" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(q."job_id" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(q."opening_held_microusd" AS '
                "TEXT)),0))),0) AS native_bytes FROM candidate AS q\n"
            ),
        )
    ),
    ("ar7", "postgresql", "financial_base_account_body"): "".join(
        (
            _SQLITE_AR7_ACCOUNT_CANDIDATE,
            ("SELECT CASE WHEN"),
            _POSTGRESQL_AR7_ACCOUNT_VALID,
            ('THEN q."id" END AS "id",CASE WHEN'),
            _POSTGRESQL_AR7_ACCOUNT_VALID,
            ('THEN q."organization_id" END AS "organization_id",CASE WHEN'),
            _POSTGRESQL_AR7_ACCOUNT_VALID,
            ('THEN q."scope" END AS "scope",CASE WHEN'),
            _POSTGRESQL_AR7_ACCOUNT_VALID,
            ('THEN q."scope_id" END AS "scope_id",CASE WHEN'),
            _POSTGRESQL_AR7_ACCOUNT_VALID,
            (
                "THEN to_char(q.\"period_start\" AT TIME ZONE 'UTC', "
                '\'YYYY-MM-DD"T"HH24:MI:SS.US"Z"\') END AS "period_start",CASE WHEN'
            ),
            _POSTGRESQL_AR7_ACCOUNT_VALID,
            (
                "THEN to_char(q.\"period_end\" AT TIME ZONE 'UTC', "
                '\'YYYY-MM-DD"T"HH24:MI:SS.US"Z"\') END AS "period_end",CASE WHEN'
            ),
            _POSTGRESQL_AR7_ACCOUNT_VALID,
            ('THEN q."limit_microusd" END AS "limit_microusd",CASE WHEN'),
            _POSTGRESQL_AR7_ACCOUNT_VALID,
            ('THEN q."held_microusd" END AS "held_microusd",CASE WHEN'),
            _POSTGRESQL_AR7_ACCOUNT_VALID,
            ('THEN q."accounted_microusd" END AS "accounted_microusd",CASE WHEN'),
            _POSTGRESQL_AR7_ACCOUNT_VALID,
            ('THEN q."project_id" END AS "project_id",CASE WHEN'),
            _POSTGRESQL_AR7_ACCOUNT_VALID,
            ('THEN q."job_id" END AS "job_id",CASE WHEN'),
            _POSTGRESQL_AR7_ACCOUNT_VALID,
            ('THEN q."opening_held_microusd" END AS "opening_held_microusd",CASE WHEN'),
            _POSTGRESQL_AR7_ACCOUNT_VALID,
            ('THEN 0 ELSE 1 END AS invalid FROM candidate AS q ORDER BY q."id"\n'),
        )
    ),
    ("ar7", "postgresql", "financial_base_call_gate"): "".join(
        (
            _SQLITE_AR7_CALL_CANDIDATE,
            ("SELECT count(*) AS candidate_rows, coalesce(sum(CASE WHEN"),
            _POSTGRESQL_AR7_CALL_VALID,
            (
                "THEN 0 ELSE 1 END),0) AS invalid_rows, "
                'coalesce(sum((coalesce(octet_length(CAST(q."id" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(q."project_id" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(q."job_id" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(q."logical_call_id" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(q."purpose" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(q."request_digest" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(q."price_version" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(q."state" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(q."reserved_microusd" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(q."usage_estimate_microusd" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(q."provider_request_id" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(to_char(q."created_at" AT TIME '
                "ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"') AS "
                'TEXT)),0)+coalesce(octet_length(CAST(q."organization_id" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(q."job_resource_kind" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(q."lease_generation" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(q."organization_account_id" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(q."project_account_id" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(q."job_account_id" AS '
                "TEXT)),0))),0) AS native_bytes FROM candidate AS q\n"
            ),
        )
    ),
    ("ar7", "postgresql", "financial_base_call_body"): "".join(
        (
            _SQLITE_AR7_CALL_CANDIDATE,
            ("SELECT CASE WHEN"),
            _POSTGRESQL_AR7_CALL_VALID,
            ('THEN q."id" END AS "id",CASE WHEN'),
            _POSTGRESQL_AR7_CALL_VALID,
            ('THEN q."project_id" END AS "project_id",CASE WHEN'),
            _POSTGRESQL_AR7_CALL_VALID,
            ('THEN q."job_id" END AS "job_id",CASE WHEN'),
            _POSTGRESQL_AR7_CALL_VALID,
            ('THEN q."logical_call_id" END AS "logical_call_id",CASE WHEN'),
            _POSTGRESQL_AR7_CALL_VALID,
            ('THEN q."purpose" END AS "purpose",CASE WHEN'),
            _POSTGRESQL_AR7_CALL_VALID,
            ('THEN q."request_digest" END AS "request_digest",CASE WHEN'),
            _POSTGRESQL_AR7_CALL_VALID,
            ('THEN q."price_version" END AS "price_version",CASE WHEN'),
            _POSTGRESQL_AR7_CALL_VALID,
            ('THEN q."state" END AS "state",CASE WHEN'),
            _POSTGRESQL_AR7_CALL_VALID,
            ('THEN q."reserved_microusd" END AS "reserved_microusd",CASE WHEN'),
            _POSTGRESQL_AR7_CALL_VALID,
            ('THEN q."usage_estimate_microusd" END AS "usage_estimate_microusd",CASE WHEN'),
            _POSTGRESQL_AR7_CALL_VALID,
            ('THEN q."provider_request_id" END AS "provider_request_id",CASE WHEN'),
            _POSTGRESQL_AR7_CALL_VALID,
            (
                "THEN to_char(q.\"created_at\" AT TIME ZONE 'UTC', "
                '\'YYYY-MM-DD"T"HH24:MI:SS.US"Z"\') END AS "created_at",CASE WHEN'
            ),
            _POSTGRESQL_AR7_CALL_VALID,
            ('THEN q."organization_id" END AS "organization_id",CASE WHEN'),
            _POSTGRESQL_AR7_CALL_VALID,
            ('THEN q."job_resource_kind" END AS "job_resource_kind",CASE WHEN'),
            _POSTGRESQL_AR7_CALL_VALID,
            ('THEN q."lease_generation" END AS "lease_generation",CASE WHEN'),
            _POSTGRESQL_AR7_CALL_VALID,
            ('THEN q."organization_account_id" END AS "organization_account_id",CASE WHEN'),
            _POSTGRESQL_AR7_CALL_VALID,
            ('THEN q."project_account_id" END AS "project_account_id",CASE WHEN'),
            _POSTGRESQL_AR7_CALL_VALID,
            ('THEN q."job_account_id" END AS "job_account_id",CASE WHEN'),
            _POSTGRESQL_AR7_CALL_VALID,
            ('THEN 0 ELSE 1 END AS invalid FROM candidate AS q ORDER BY q."id"\n'),
        )
    ),
    ("ar7", "postgresql", "financial_base_entry_gate"): "".join(
        (
            _SQLITE_AR7_ENTRY_CANDIDATE,
            ("SELECT count(*) AS candidate_rows, coalesce(sum(CASE WHEN"),
            _POSTGRESQL_AR7_ENTRY_VALID,
            (
                "THEN 0 ELSE 1 END),0) AS invalid_rows, "
                'coalesce(sum((coalesce(octet_length(CAST(q."call_id" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(q."account_id" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(q."entry_kind" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(q."amount_microusd" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(q."evidence_ref" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(to_char(q."created_at" AT TIME '
                "ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"') AS "
                'TEXT)),0)+coalesce(octet_length(CAST(q."project_id" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(q."evidence_owner_kind" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(q."evidence_role" AS '
                "TEXT)),0))),0) AS native_bytes FROM candidate AS q\n"
            ),
        )
    ),
    ("ar7", "postgresql", "financial_base_entry_body"): "".join(
        (
            _SQLITE_AR7_ENTRY_CANDIDATE,
            ("SELECT CASE WHEN"),
            _POSTGRESQL_AR7_ENTRY_VALID,
            ('THEN q."call_id" END AS "call_id",CASE WHEN'),
            _POSTGRESQL_AR7_ENTRY_VALID,
            ('THEN q."account_id" END AS "account_id",CASE WHEN'),
            _POSTGRESQL_AR7_ENTRY_VALID,
            ('THEN q."entry_kind" END AS "entry_kind",CASE WHEN'),
            _POSTGRESQL_AR7_ENTRY_VALID,
            ('THEN q."amount_microusd" END AS "amount_microusd",CASE WHEN'),
            _POSTGRESQL_AR7_ENTRY_VALID,
            ('THEN q."evidence_ref" END AS "evidence_ref",CASE WHEN'),
            _POSTGRESQL_AR7_ENTRY_VALID,
            (
                "THEN to_char(q.\"created_at\" AT TIME ZONE 'UTC', "
                '\'YYYY-MM-DD"T"HH24:MI:SS.US"Z"\') END AS "created_at",CASE WHEN'
            ),
            _POSTGRESQL_AR7_ENTRY_VALID,
            ('THEN q."project_id" END AS "project_id",CASE WHEN'),
            _POSTGRESQL_AR7_ENTRY_VALID,
            ('THEN q."evidence_owner_kind" END AS "evidence_owner_kind",CASE WHEN'),
            _POSTGRESQL_AR7_ENTRY_VALID,
            ('THEN q."evidence_role" END AS "evidence_role",CASE WHEN'),
            _POSTGRESQL_AR7_ENTRY_VALID,
            (
                "THEN 0 ELSE 1 END AS invalid FROM candidate AS q ORDER BY "
                'q."call_id",q."account_id",q."entry_kind"\n'
            ),
        )
    ),
    ("ar7", "postgresql", "financial_base_job_gate"): "".join(
        (
            _SQLITE_AR7_JOB_CANDIDATE,
            ("SELECT count(*) AS candidate_rows, coalesce(sum(CASE WHEN"),
            _POSTGRESQL_AR7_JOB_VALID,
            (
                "THEN 0 ELSE 1 END),0) AS invalid_rows, "
                'coalesce(sum((coalesce(octet_length(CAST(q."id" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(q."kind" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(q."created" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(q."payload" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(q."status" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(q."owner" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(q."lease_until" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(q."cancel" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(q."budget" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(q."reserved" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(q."result" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(q."error" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(q."actor" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(q."payload_version" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(q."execution_config_ref" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(q."execution_config_digest" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(q."lease_generation" AS '
                'TEXT)),0)+coalesce(octet_length(CAST(q."legacy_reserved_microusd" '
                "AS TEXT)),0))),0) AS native_bytes FROM candidate AS q\n"
            ),
        )
    ),
    ("ar7", "postgresql", "financial_base_job_body"): "".join(
        (
            _SQLITE_AR7_JOB_CANDIDATE,
            ("SELECT CASE WHEN"),
            _POSTGRESQL_AR7_JOB_VALID,
            ('THEN q."id" END AS "id",CASE WHEN'),
            _POSTGRESQL_AR7_JOB_VALID,
            ('THEN q."kind" END AS "kind",CASE WHEN'),
            _POSTGRESQL_AR7_JOB_VALID,
            ('THEN q."created" END AS "created",CASE WHEN'),
            _POSTGRESQL_AR7_JOB_VALID,
            ('THEN q."payload" END AS "payload",CASE WHEN'),
            _POSTGRESQL_AR7_JOB_VALID,
            ('THEN q."status" END AS "status",CASE WHEN'),
            _POSTGRESQL_AR7_JOB_VALID,
            ('THEN q."owner" END AS "owner",CASE WHEN'),
            _POSTGRESQL_AR7_JOB_VALID,
            ('THEN q."lease_until" END AS "lease_until",CASE WHEN'),
            _POSTGRESQL_AR7_JOB_VALID,
            ('THEN q."cancel" END AS "cancel",CASE WHEN'),
            _POSTGRESQL_AR7_JOB_VALID,
            ('THEN q."budget" END AS "budget",CASE WHEN'),
            _POSTGRESQL_AR7_JOB_VALID,
            ('THEN q."reserved" END AS "reserved",CASE WHEN'),
            _POSTGRESQL_AR7_JOB_VALID,
            ('THEN q."result" END AS "result",CASE WHEN'),
            _POSTGRESQL_AR7_JOB_VALID,
            ('THEN q."error" END AS "error",CASE WHEN'),
            _POSTGRESQL_AR7_JOB_VALID,
            ('THEN q."actor" END AS "actor",CASE WHEN'),
            _POSTGRESQL_AR7_JOB_VALID,
            ('THEN q."payload_version" END AS "payload_version",CASE WHEN'),
            _POSTGRESQL_AR7_JOB_VALID,
            ('THEN q."execution_config_ref" END AS "execution_config_ref",CASE WHEN'),
            _POSTGRESQL_AR7_JOB_VALID,
            ('THEN q."execution_config_digest" END AS "execution_config_digest",CASE WHEN'),
            _POSTGRESQL_AR7_JOB_VALID,
            ('THEN q."lease_generation" END AS "lease_generation",CASE WHEN'),
            _POSTGRESQL_AR7_JOB_VALID,
            ('THEN q."legacy_reserved_microusd" END AS "legacy_reserved_microusd",CASE WHEN'),
            _POSTGRESQL_AR7_JOB_VALID,
            ('THEN 0 ELSE 1 END AS invalid FROM candidate AS q ORDER BY q."id"\n'),
        )
    ),
    ("ar7", "postgresql", "financial_base_operation_gate"): "".join(
        (
            _SQLITE_AR6_OPERATION_CANDIDATE,
            _POSTGRESQL_AR6_OPERATION_PROJECTION,
        )
    ),
    ("ar7", "postgresql", "financial_base_operation_body"): "".join(
        (
            _SQLITE_AR6_OPERATION_CANDIDATE,
            _POSTGRESQL_AR6_OPERATION_PROJECTION_2,
        )
    ),
    ("ar7", "postgresql", "financial_base_scope_gate"): "".join(
        (
            _SQLITE_AR7_SCOPE_CANDIDATE,
            _POSTGRESQL_AR6_SCOPE_PROJECTION,
        )
    ),
    ("ar7", "postgresql", "financial_base_scope_body"): "".join(
        (
            _SQLITE_AR7_SCOPE_CANDIDATE,
            _POSTGRESQL_AR6_SCOPE_PROJECTION_2,
        )
    ),
    ("ar7", "postgresql", "financial_base_organization_gate"): "".join(
        (
            _SQLITE_AR6_ORGANIZATION_CANDIDATE,
            _POSTGRESQL_AR6_ORGANIZATION_PROJECTION,
        )
    ),
    ("ar7", "postgresql", "financial_base_organization_body"): "".join(
        (
            _SQLITE_AR6_ORGANIZATION_CANDIDATE,
            _POSTGRESQL_AR6_ORGANIZATION_PROJECTION_2,
        )
    ),
    ("ar6", "sqlite", "financial_owner_gate"): "".join(
        (
            ("WITH jbase AS MATERIALIZED (SELECT id FROM jobs ORDER BY id LIMIT 65537)"),
            _SQLITE_AR6_OWNER_OWNER_ROWS,
            (" "),
            _SQLITE_AR6_OWNER_PROJECTION,
        )
    ),
    ("ar6", "sqlite", "financial_ref_gate"): "".join(
        (
            ("WITH jbase AS MATERIALIZED (SELECT id FROM jobs ORDER BY id LIMIT 65537)"),
            _SQLITE_AR6_OWNER_OWNER_ROWS,
            _SQLITE_AR6_REF_REF_CANDIDATE,
            _SQLITE_AR6_REF_PROJECTION,
        )
    ),
    ("ar6", "sqlite", "financial_ref_body"): "".join(
        (
            ("WITH jbase AS MATERIALIZED (SELECT id FROM jobs ORDER BY id LIMIT 65537)"),
            _SQLITE_AR6_OWNER_OWNER_ROWS,
            _SQLITE_AR6_REF_REF_CANDIDATE,
            _SQLITE_AR6_REF_PROJECTION_2,
        )
    ),
    ("ar6", "sqlite", "financial_object_gate"): "".join(
        (
            ("WITH jbase AS MATERIALIZED (SELECT id FROM jobs ORDER BY id LIMIT 65537)"),
            _SQLITE_AR6_OWNER_OWNER_ROWS,
            _SQLITE_AR6_REF_REF_CANDIDATE_2,
            _SQLITE_AR6_OBJECT_OBJECT_KEYS,
            _SQLITE_AR6_OBJECT_OBJECT_CANDIDATE,
            _SQLITE_AR6_OBJECT_PROJECTION,
        )
    ),
    ("ar6", "sqlite", "financial_object_body"): "".join(
        (
            ("WITH jbase AS MATERIALIZED (SELECT id FROM jobs ORDER BY id LIMIT 65537)"),
            _SQLITE_AR6_OWNER_OWNER_ROWS,
            _SQLITE_AR6_REF_REF_CANDIDATE_2,
            _SQLITE_AR6_OBJECT_OBJECT_KEYS,
            _SQLITE_AR6_OBJECT_OBJECT_CANDIDATE,
            _SQLITE_AR6_OBJECT_PROJECTION_2,
        )
    ),
    ("ar6", "sqlite", "financial_project_gate"): "".join(
        (
            _SQLITE_AR6_PROJECT_PROJECT_KEYS,
            _SQLITE_AR6_PROJECT_PROJECT_CANDIDATE,
            _SQLITE_AR6_PROJECT_PROJECTION,
        )
    ),
    ("ar6", "sqlite", "financial_project_body"): "".join(
        (
            _SQLITE_AR6_PROJECT_PROJECT_KEYS,
            _SQLITE_AR6_PROJECT_PROJECT_CANDIDATE,
            _SQLITE_AR6_PROJECT_PROJECTION_2,
        )
    ),
    ("ar6", "postgresql", "financial_owner_gate"): "".join(
        (
            ("WITH jbase AS MATERIALIZED (SELECT id FROM jobs ORDER BY id LIMIT 65537)"),
            _POSTGRESQL_AR6_OWNER_OWNER_ROWS,
            (" "),
            _POSTGRESQL_AR6_OWNER_PROJECTION,
        )
    ),
    ("ar6", "postgresql", "financial_ref_gate"): "".join(
        (
            ("WITH jbase AS MATERIALIZED (SELECT id FROM jobs ORDER BY id LIMIT 65537)"),
            _POSTGRESQL_AR6_OWNER_OWNER_ROWS,
            _POSTGRESQL_AR6_REF_REF_CANDIDATE,
            _POSTGRESQL_AR6_REF_PROJECTION,
        )
    ),
    ("ar6", "postgresql", "financial_ref_body"): "".join(
        (
            ("WITH jbase AS MATERIALIZED (SELECT id FROM jobs ORDER BY id LIMIT 65537)"),
            _POSTGRESQL_AR6_OWNER_OWNER_ROWS,
            _POSTGRESQL_AR6_REF_REF_CANDIDATE,
            _POSTGRESQL_AR6_REF_PROJECTION_2,
        )
    ),
    ("ar6", "postgresql", "financial_object_gate"): "".join(
        (
            ("WITH jbase AS MATERIALIZED (SELECT id FROM jobs ORDER BY id LIMIT 65537)"),
            _POSTGRESQL_AR6_OWNER_OWNER_ROWS,
            _POSTGRESQL_AR6_REF_REF_CANDIDATE_2,
            _SQLITE_AR6_OBJECT_OBJECT_KEYS,
            _POSTGRESQL_AR6_OBJECT_OBJECT_CANDIDATE,
            _POSTGRESQL_AR6_OBJECT_PROJECTION,
        )
    ),
    ("ar6", "postgresql", "financial_object_body"): "".join(
        (
            ("WITH jbase AS MATERIALIZED (SELECT id FROM jobs ORDER BY id LIMIT 65537)"),
            _POSTGRESQL_AR6_OWNER_OWNER_ROWS,
            _POSTGRESQL_AR6_REF_REF_CANDIDATE_2,
            _SQLITE_AR6_OBJECT_OBJECT_KEYS,
            _POSTGRESQL_AR6_OBJECT_OBJECT_CANDIDATE,
            _POSTGRESQL_AR6_OBJECT_PROJECTION_2,
        )
    ),
    ("ar6", "postgresql", "financial_project_gate"): "".join(
        (
            _SQLITE_AR6_PROJECT_PROJECT_KEYS,
            _POSTGRESQL_AR6_PROJECT_PROJECT_CANDIDATE,
            _POSTGRESQL_AR6_PROJECT_PROJECTION,
        )
    ),
    ("ar6", "postgresql", "financial_project_body"): "".join(
        (
            _SQLITE_AR6_PROJECT_PROJECT_KEYS,
            _POSTGRESQL_AR6_PROJECT_PROJECT_CANDIDATE,
            _POSTGRESQL_AR6_PROJECT_PROJECTION_2,
        )
    ),
    ("ar7", "sqlite", "financial_owner_gate"): "".join(
        (
            (
                "WITH jbase AS MATERIALIZED (SELECT id FROM jobs ORDER BY id LIMIT "
                "65537),cbase AS MATERIALIZED (SELECT id,project_id FROM "
                "provider_calls ORDER BY id LIMIT 65537)"
            ),
            _SQLITE_AR7_OWNER_OWNER_ROWS,
            (" "),
            _SQLITE_AR6_OWNER_PROJECTION,
        )
    ),
    ("ar7", "sqlite", "financial_ref_gate"): "".join(
        (
            (
                "WITH jbase AS MATERIALIZED (SELECT id FROM jobs ORDER BY id LIMIT "
                "65537),cbase AS MATERIALIZED (SELECT id,project_id FROM "
                "provider_calls ORDER BY id LIMIT 65537)"
            ),
            _SQLITE_AR7_OWNER_OWNER_ROWS,
            _SQLITE_AR6_REF_REF_CANDIDATE,
            _SQLITE_AR6_REF_PROJECTION,
        )
    ),
    ("ar7", "sqlite", "financial_ref_body"): "".join(
        (
            (
                "WITH jbase AS MATERIALIZED (SELECT id FROM jobs ORDER BY id LIMIT "
                "65537),cbase AS MATERIALIZED (SELECT id,project_id FROM "
                "provider_calls ORDER BY id LIMIT 65537)"
            ),
            _SQLITE_AR7_OWNER_OWNER_ROWS,
            _SQLITE_AR6_REF_REF_CANDIDATE,
            _SQLITE_AR6_REF_PROJECTION_2,
        )
    ),
    ("ar7", "sqlite", "financial_object_gate"): "".join(
        (
            (
                "WITH jbase AS MATERIALIZED (SELECT id FROM jobs ORDER BY id LIMIT "
                "65537),cbase AS MATERIALIZED (SELECT id,project_id FROM "
                "provider_calls ORDER BY id LIMIT 65537)"
            ),
            _SQLITE_AR7_OWNER_OWNER_ROWS,
            _SQLITE_AR6_REF_REF_CANDIDATE_2,
            _SQLITE_AR6_OBJECT_OBJECT_KEYS,
            _SQLITE_AR6_OBJECT_OBJECT_CANDIDATE,
            _SQLITE_AR6_OBJECT_PROJECTION,
        )
    ),
    ("ar7", "sqlite", "financial_object_body"): "".join(
        (
            (
                "WITH jbase AS MATERIALIZED (SELECT id FROM jobs ORDER BY id LIMIT "
                "65537),cbase AS MATERIALIZED (SELECT id,project_id FROM "
                "provider_calls ORDER BY id LIMIT 65537)"
            ),
            _SQLITE_AR7_OWNER_OWNER_ROWS,
            _SQLITE_AR6_REF_REF_CANDIDATE_2,
            _SQLITE_AR6_OBJECT_OBJECT_KEYS,
            _SQLITE_AR6_OBJECT_OBJECT_CANDIDATE,
            _SQLITE_AR6_OBJECT_PROJECTION_2,
        )
    ),
    ("ar7", "sqlite", "financial_project_gate"): "".join(
        (
            (
                "WITH cbase AS MATERIALIZED (SELECT id,project_id FROM "
                "provider_calls ORDER BY id LIMIT 65537)"
            ),
            _SQLITE_AR7_PROJECT_PROJECT_KEYS,
            _SQLITE_AR6_PROJECT_PROJECT_CANDIDATE,
            _SQLITE_AR6_PROJECT_PROJECTION,
        )
    ),
    ("ar7", "sqlite", "financial_project_body"): "".join(
        (
            (
                "WITH cbase AS MATERIALIZED (SELECT id,project_id FROM "
                "provider_calls ORDER BY id LIMIT 65537)"
            ),
            _SQLITE_AR7_PROJECT_PROJECT_KEYS,
            _SQLITE_AR6_PROJECT_PROJECT_CANDIDATE,
            _SQLITE_AR6_PROJECT_PROJECTION_2,
        )
    ),
    ("ar7", "postgresql", "financial_owner_gate"): "".join(
        (
            (
                "WITH jbase AS MATERIALIZED (SELECT id FROM jobs ORDER BY id LIMIT "
                "65537),cbase AS MATERIALIZED (SELECT id,project_id FROM "
                "provider_calls ORDER BY id LIMIT 65537)"
            ),
            _POSTGRESQL_AR7_OWNER_OWNER_ROWS,
            (" "),
            _POSTGRESQL_AR6_OWNER_PROJECTION,
        )
    ),
    ("ar7", "postgresql", "financial_ref_gate"): "".join(
        (
            (
                "WITH jbase AS MATERIALIZED (SELECT id FROM jobs ORDER BY id LIMIT "
                "65537),cbase AS MATERIALIZED (SELECT id,project_id FROM "
                "provider_calls ORDER BY id LIMIT 65537)"
            ),
            _POSTGRESQL_AR7_OWNER_OWNER_ROWS,
            _POSTGRESQL_AR6_REF_REF_CANDIDATE,
            _POSTGRESQL_AR6_REF_PROJECTION,
        )
    ),
    ("ar7", "postgresql", "financial_ref_body"): "".join(
        (
            (
                "WITH jbase AS MATERIALIZED (SELECT id FROM jobs ORDER BY id LIMIT "
                "65537),cbase AS MATERIALIZED (SELECT id,project_id FROM "
                "provider_calls ORDER BY id LIMIT 65537)"
            ),
            _POSTGRESQL_AR7_OWNER_OWNER_ROWS,
            _POSTGRESQL_AR6_REF_REF_CANDIDATE,
            _POSTGRESQL_AR6_REF_PROJECTION_2,
        )
    ),
    ("ar7", "postgresql", "financial_object_gate"): "".join(
        (
            (
                "WITH jbase AS MATERIALIZED (SELECT id FROM jobs ORDER BY id LIMIT "
                "65537),cbase AS MATERIALIZED (SELECT id,project_id FROM "
                "provider_calls ORDER BY id LIMIT 65537)"
            ),
            _POSTGRESQL_AR7_OWNER_OWNER_ROWS,
            _POSTGRESQL_AR6_REF_REF_CANDIDATE_2,
            _SQLITE_AR6_OBJECT_OBJECT_KEYS,
            _POSTGRESQL_AR6_OBJECT_OBJECT_CANDIDATE,
            _POSTGRESQL_AR6_OBJECT_PROJECTION,
        )
    ),
    ("ar7", "postgresql", "financial_object_body"): "".join(
        (
            (
                "WITH jbase AS MATERIALIZED (SELECT id FROM jobs ORDER BY id LIMIT "
                "65537),cbase AS MATERIALIZED (SELECT id,project_id FROM "
                "provider_calls ORDER BY id LIMIT 65537)"
            ),
            _POSTGRESQL_AR7_OWNER_OWNER_ROWS,
            _POSTGRESQL_AR6_REF_REF_CANDIDATE_2,
            _SQLITE_AR6_OBJECT_OBJECT_KEYS,
            _POSTGRESQL_AR6_OBJECT_OBJECT_CANDIDATE,
            _POSTGRESQL_AR6_OBJECT_PROJECTION_2,
        )
    ),
    ("ar7", "postgresql", "financial_project_gate"): "".join(
        (
            (
                "WITH cbase AS MATERIALIZED (SELECT id,project_id FROM "
                "provider_calls ORDER BY id LIMIT 65537)"
            ),
            _SQLITE_AR7_PROJECT_PROJECT_KEYS,
            _POSTGRESQL_AR6_PROJECT_PROJECT_CANDIDATE,
            _POSTGRESQL_AR6_PROJECT_PROJECTION,
        )
    ),
    ("ar7", "postgresql", "financial_project_body"): "".join(
        (
            (
                "WITH cbase AS MATERIALIZED (SELECT id,project_id FROM "
                "provider_calls ORDER BY id LIMIT 65537)"
            ),
            _SQLITE_AR7_PROJECT_PROJECT_KEYS,
            _POSTGRESQL_AR6_PROJECT_PROJECT_CANDIDATE,
            _POSTGRESQL_AR6_PROJECT_PROJECTION_2,
        )
    ),
}
