"""Fixed bounded original-value pages; caller values remain bind parameters."""

# Shared fragments have identical semantics across gate/body or page stages.

_GATE = (
    "\nSELECT count(*) AS candidate_count,\n  COALESCE(sum(__invalid),0) "
    "AS invalid_rows,\n  COALESCE(max(__bytes),0) AS max_row_bytes,\n  CO"
    "ALESCE(sum(CASE WHEN __running <= 16777216 THEN 1 ELSE 0 END),0) A"
    "S selected_count,\n  COALESCE(sum(CASE WHEN __running <= 16777216 T"
    "HEN __bytes ELSE 0 END),0) AS selected_bytes\nFROM ordered"
)

_SELECTED = (
    "\n), selected AS MATERIALIZED (\n  SELECT * FROM ordered WHERE __ord"
    "inal <= :selected_count AND __running <= 16777216\n)\nSELECT "
)

_SQLITE_API_KEYS_CANDIDATES = (
    'WITH candidate AS MATERIALIZED (\n  SELECT s."id" AS __k0,\n    (COA'
    'LESCE(length(CAST(s."id" AS BLOB)),0) + COALESCE(length(CAST(s."ha'
    'sh" AS BLOB)),0) + COALESCE(length(CAST(s."role" AS BLOB)),0) + CO'
    'ALESCE(length(CAST(s."name" AS BLOB)),0) + COALESCE(length(CAST(s.'
    '"expires" AS BLOB)),0) + COALESCE(length(CAST(s."revoked" AS BLOB)'
    "),0)) AS __bytes,\n    CASE WHEN (typeof(s.\"id\") IN ('null','intege"
    "r','text') OR (typeof(s.\"id\")='real' AND s.\"id\" BETWEEN -1.7976931"
    '348623157e308 AND 1.7976931348623157e308)) AND (typeof(s."hash") I'
    "N ('null','integer','text') OR (typeof(s.\"hash\")='real' AND s.\"has"
    'h" BETWEEN -1.7976931348623157e308 AND 1.7976931348623157e308)) AN'
    "D (typeof(s.\"role\") IN ('null','integer','text') OR (typeof(s.\"rol"
    'e")=\'real\' AND s."role" BETWEEN -1.7976931348623157e308 AND 1.7976'
    "931348623157e308)) AND (typeof(s.\"name\") IN ('null','integer','tex"
    't\') OR (typeof(s."name")=\'real\' AND s."name" BETWEEN -1.7976931348'
    '623157e308 AND 1.7976931348623157e308)) AND (typeof(s."expires") I'
    "N ('null','integer','text') OR (typeof(s.\"expires\")='real' AND s.\""
    'expires" BETWEEN -1.7976931348623157e308 AND 1.7976931348623157e30'
    "8)) AND (typeof(s.\"revoked\") IN ('null','integer','text') OR (type"
    'of(s."revoked")=\'real\' AND s."revoked" BETWEEN -1.7976931348623157'
    'e308 AND 1.7976931348623157e308)) AND s."id" IS NOT NULL THEN 0 EL'
    'SE 1 END AS __invalid\n  FROM "api_keys" AS s WHERE '
)

_SQLITE_API_KEYS_ORDER = (
    '\n  ORDER BY s."id" LIMIT 4096\n), ordered AS MATERIALIZED (\n  SELEC'
    "T candidate.*, row_number() OVER (ORDER BY __k0) AS __ordinal,\n   "
    " sum(__bytes) OVER (ORDER BY __k0 ROWS BETWEEN UNBOUNDED PRECEDING"
    " AND CURRENT ROW) AS __running\n  FROM candidate\n)"
)

_SQLITE_API_KEYS_FIRST = _SQLITE_API_KEYS_CANDIDATES + "TRUE" + _SQLITE_API_KEYS_ORDER
_SQLITE_API_KEYS_NEXT = (
    _SQLITE_API_KEYS_CANDIDATES + ('s."id" > :last_key') + _SQLITE_API_KEYS_ORDER
)

_SQLITE_API_KEYS_BODY_VALID = (
    "p.__invalid=0 AND ((typeof(b.\"id\") IN ('null','integer','text') OR"
    ' (typeof(b."id")=\'real\' AND b."id" BETWEEN -1.7976931348623157e308'
    " AND 1.7976931348623157e308)) AND (typeof(b.\"hash\") IN ('null','in"
    "teger','text') OR (typeof(b.\"hash\")='real' AND b.\"hash\" BETWEEN -1"
    '.7976931348623157e308 AND 1.7976931348623157e308)) AND (typeof(b."'
    "role\") IN ('null','integer','text') OR (typeof(b.\"role\")='real' AN"
    'D b."role" BETWEEN -1.7976931348623157e308 AND 1.7976931348623157e'
    "308)) AND (typeof(b.\"name\") IN ('null','integer','text') OR (typeo"
    'f(b."name")=\'real\' AND b."name" BETWEEN -1.7976931348623157e308 AN'
    "D 1.7976931348623157e308)) AND (typeof(b.\"expires\") IN ('null','in"
    "teger','text') OR (typeof(b.\"expires\")='real' AND b.\"expires\" BETW"
    "EEN -1.7976931348623157e308 AND 1.7976931348623157e308)) AND (type"
    "of(b.\"revoked\") IN ('null','integer','text') OR (typeof(b.\"revoked"
    '")=\'real\' AND b."revoked" BETWEEN -1.7976931348623157e308 AND 1.79'
    '76931348623157e308)) AND b."id" IS NOT NULL) AND (COALESCE(length('
    'CAST(b."id" AS BLOB)),0) + COALESCE(length(CAST(b."hash" AS BLOB))'
    ',0) + COALESCE(length(CAST(b."role" AS BLOB)),0) + COALESCE(length'
    '(CAST(b."name" AS BLOB)),0) + COALESCE(length(CAST(b."expires" AS '
    'BLOB)),0) + COALESCE(length(CAST(b."revoked" AS BLOB)),0))=p.__byt'
    "es AND p.__bytes<=16777216"
)

_SQLITE_API_KEYS_BODY = (
    ("CASE WHEN ")
    + _SQLITE_API_KEYS_BODY_VALID
    + (' THEN b."id" ELSE NULL END AS "id",\n  CASE WHEN ')
    + _SQLITE_API_KEYS_BODY_VALID
    + (' THEN b."hash" ELSE NULL END AS "hash",\n  CASE WHEN ')
    + _SQLITE_API_KEYS_BODY_VALID
    + (' THEN b."role" ELSE NULL END AS "role",\n  CASE WHEN ')
    + _SQLITE_API_KEYS_BODY_VALID
    + (' THEN b."name" ELSE NULL END AS "name",\n  CASE WHEN ')
    + _SQLITE_API_KEYS_BODY_VALID
    + (' THEN b."expires" ELSE NULL END AS "expires",\n  CASE WHEN ')
    + _SQLITE_API_KEYS_BODY_VALID
    + (
        ' THEN b."revoked" ELSE NULL END AS "revoked",\n  p.__ordinal AS sou'
        "rce_ordinal,\n  p.__bytes AS native_row_bytes,\n  CASE WHEN "
    )
    + _SQLITE_API_KEYS_BODY_VALID
    + (
        ' THEN 0 ELSE 1 END AS invalid_row\nFROM selected AS p JOIN "api_key'
        's" AS b ON b."id" = p.__k0\nORDER BY p.__ordinal LIMIT 4097'
    )
)

_SQLITE_AUDIT_CANDIDATES = (
    'WITH candidate AS MATERIALIZED (\n  SELECT s."id" AS __k0,\n    (COA'
    'LESCE(length(CAST(s."id" AS BLOB)),0) + COALESCE(length(CAST(s."cr'
    'eated" AS BLOB)),0) + COALESCE(length(CAST(s."actor" AS BLOB)),0) '
    '+ COALESCE(length(CAST(s."action" AS BLOB)),0) + COALESCE(length(C'
    'AST(s."target" AS BLOB)),0)) AS __bytes,\n    CASE WHEN (typeof(s."'
    "id\") IN ('null','integer','text') OR (typeof(s.\"id\")='real' AND s."
    '"id" BETWEEN -1.7976931348623157e308 AND 1.7976931348623157e308)) '
    "AND (typeof(s.\"created\") IN ('null','integer','text') OR (typeof(s"
    '."created")=\'real\' AND s."created" BETWEEN -1.7976931348623157e308'
    " AND 1.7976931348623157e308)) AND (typeof(s.\"actor\") IN ('null','i"
    "nteger','text') OR (typeof(s.\"actor\")='real' AND s.\"actor\" BETWEEN"
    " -1.7976931348623157e308 AND 1.7976931348623157e308)) AND (typeof("
    "s.\"action\") IN ('null','integer','text') OR (typeof(s.\"action\")='r"
    'eal\' AND s."action" BETWEEN -1.7976931348623157e308 AND 1.79769313'
    "48623157e308)) AND (typeof(s.\"target\") IN ('null','integer','text'"
    ') OR (typeof(s."target")=\'real\' AND s."target" BETWEEN -1.79769313'
    '48623157e308 AND 1.7976931348623157e308)) AND s."id" IS NOT NULL T'
    'HEN 0 ELSE 1 END AS __invalid\n  FROM "audit" AS s WHERE '
)

_SQLITE_AUDIT_ORDER = (
    '\n  ORDER BY s."id" LIMIT 4096\n), ordered AS MATERIALIZED (\n  SELEC'
    "T candidate.*, row_number() OVER (ORDER BY __k0) AS __ordinal,\n   "
    " sum(__bytes) OVER (ORDER BY __k0 ROWS BETWEEN UNBOUNDED PRECEDING"
    " AND CURRENT ROW) AS __running\n  FROM candidate\n)"
)

_SQLITE_AUDIT_FIRST = _SQLITE_AUDIT_CANDIDATES + "TRUE" + _SQLITE_AUDIT_ORDER
_SQLITE_AUDIT_NEXT = _SQLITE_AUDIT_CANDIDATES + ('s."id" > :last_key') + _SQLITE_AUDIT_ORDER

_SQLITE_AUDIT_BODY_VALID = (
    "p.__invalid=0 AND ((typeof(b.\"id\") IN ('null','integer','text') OR"
    ' (typeof(b."id")=\'real\' AND b."id" BETWEEN -1.7976931348623157e308'
    " AND 1.7976931348623157e308)) AND (typeof(b.\"created\") IN ('null',"
    "'integer','text') OR (typeof(b.\"created\")='real' AND b.\"created\" B"
    "ETWEEN -1.7976931348623157e308 AND 1.7976931348623157e308)) AND (t"
    "ypeof(b.\"actor\") IN ('null','integer','text') OR (typeof(b.\"actor\""
    ")='real' AND b.\"actor\" BETWEEN -1.7976931348623157e308 AND 1.79769"
    "31348623157e308)) AND (typeof(b.\"action\") IN ('null','integer','te"
    'xt\') OR (typeof(b."action")=\'real\' AND b."action" BETWEEN -1.79769'
    '31348623157e308 AND 1.7976931348623157e308)) AND (typeof(b."target'
    "\") IN ('null','integer','text') OR (typeof(b.\"target\")='real' AND "
    'b."target" BETWEEN -1.7976931348623157e308 AND 1.7976931348623157e'
    '308)) AND b."id" IS NOT NULL) AND (COALESCE(length(CAST(b."id" AS '
    'BLOB)),0) + COALESCE(length(CAST(b."created" AS BLOB)),0) + COALES'
    'CE(length(CAST(b."actor" AS BLOB)),0) + COALESCE(length(CAST(b."ac'
    'tion" AS BLOB)),0) + COALESCE(length(CAST(b."target" AS BLOB)),0))'
    "=p.__bytes AND p.__bytes<=16777216"
)

_SQLITE_AUDIT_BODY = (
    ("CASE WHEN ")
    + _SQLITE_AUDIT_BODY_VALID
    + (' THEN b."id" ELSE NULL END AS "id",\n  CASE WHEN ')
    + _SQLITE_AUDIT_BODY_VALID
    + (' THEN b."created" ELSE NULL END AS "created",\n  CASE WHEN ')
    + _SQLITE_AUDIT_BODY_VALID
    + (' THEN b."actor" ELSE NULL END AS "actor",\n  CASE WHEN ')
    + _SQLITE_AUDIT_BODY_VALID
    + (' THEN b."action" ELSE NULL END AS "action",\n  CASE WHEN ')
    + _SQLITE_AUDIT_BODY_VALID
    + (
        ' THEN b."target" ELSE NULL END AS "target",\n  p.__ordinal AS sourc'
        "e_ordinal,\n  p.__bytes AS native_row_bytes,\n  CASE WHEN "
    )
    + _SQLITE_AUDIT_BODY_VALID
    + (
        ' THEN 0 ELSE 1 END AS invalid_row\nFROM selected AS p JOIN "audit" '
        'AS b ON b."id" = p.__k0\nORDER BY p.__ordinal LIMIT 4097'
    )
)

_SQLITE_EVENTS_CANDIDATES = (
    'WITH candidate AS MATERIALIZED (\n  SELECT s."run_id" AS __k0, s."s'
    'tep" AS __k1,\n    (COALESCE(length(CAST(s."run_id" AS BLOB)),0) + '
    'COALESCE(length(CAST(s."step" AS BLOB)),0) + COALESCE(length(CAST('
    's."artifact" AS BLOB)),0) + COALESCE(length(CAST(s."hash" AS BLOB)'
    "),0)) AS __bytes,\n    CASE WHEN (typeof(s.\"run_id\") IN ('null','in"
    "teger','text') OR (typeof(s.\"run_id\")='real' AND s.\"run_id\" BETWEE"
    "N -1.7976931348623157e308 AND 1.7976931348623157e308)) AND (typeof"
    "(s.\"step\") IN ('null','integer','text') OR (typeof(s.\"step\")='real"
    '\' AND s."step" BETWEEN -1.7976931348623157e308 AND 1.7976931348623'
    "157e308)) AND (typeof(s.\"artifact\") IN ('null','integer','text') O"
    'R (typeof(s."artifact")=\'real\' AND s."artifact" BETWEEN -1.7976931'
    '348623157e308 AND 1.7976931348623157e308)) AND (typeof(s."hash") I'
    "N ('null','integer','text') OR (typeof(s.\"hash\")='real' AND s.\"has"
    'h" BETWEEN -1.7976931348623157e308 AND 1.7976931348623157e308)) AN'
    'D s."run_id" IS NOT NULL AND s."step" IS NOT NULL THEN 0 ELSE 1 EN'
    'D AS __invalid\n  FROM "events" AS s WHERE '
)

_SQLITE_EVENTS_ORDER = (
    '\n  ORDER BY s."run_id", s."step" LIMIT 4096\n), ordered AS MATERIAL'
    "IZED (\n  SELECT candidate.*, row_number() OVER (ORDER BY __k0, __k"
    "1) AS __ordinal,\n    sum(__bytes) OVER (ORDER BY __k0, __k1 ROWS B"
    "ETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS __running\n  FROM ca"
    "ndidate\n)"
)

_SQLITE_EVENTS_FIRST = _SQLITE_EVENTS_CANDIDATES + "TRUE" + _SQLITE_EVENTS_ORDER
_SQLITE_EVENTS_NEXT = (
    _SQLITE_EVENTS_CANDIDATES
    + ('(s."run_id" > :last_run OR (s."run_id" = :last_run AND s."step" > :last_step))')
    + _SQLITE_EVENTS_ORDER
)

_SQLITE_EVENTS_BODY_VALID = (
    "p.__invalid=0 AND ((typeof(b.\"run_id\") IN ('null','integer','text'"
    ') OR (typeof(b."run_id")=\'real\' AND b."run_id" BETWEEN -1.79769313'
    '48623157e308 AND 1.7976931348623157e308)) AND (typeof(b."step") IN'
    " ('null','integer','text') OR (typeof(b.\"step\")='real' AND b.\"step"
    '" BETWEEN -1.7976931348623157e308 AND 1.7976931348623157e308)) AND'
    " (typeof(b.\"artifact\") IN ('null','integer','text') OR (typeof(b.\""
    'artifact")=\'real\' AND b."artifact" BETWEEN -1.7976931348623157e308'
    " AND 1.7976931348623157e308)) AND (typeof(b.\"hash\") IN ('null','in"
    "teger','text') OR (typeof(b.\"hash\")='real' AND b.\"hash\" BETWEEN -1"
    '.7976931348623157e308 AND 1.7976931348623157e308)) AND b."run_id" '
    'IS NOT NULL AND b."step" IS NOT NULL) AND (COALESCE(length(CAST(b.'
    '"run_id" AS BLOB)),0) + COALESCE(length(CAST(b."step" AS BLOB)),0)'
    ' + COALESCE(length(CAST(b."artifact" AS BLOB)),0) + COALESCE(lengt'
    'h(CAST(b."hash" AS BLOB)),0))=p.__bytes AND p.__bytes<=16777216'
)

_SQLITE_EVENTS_BODY = (
    ("CASE WHEN ")
    + _SQLITE_EVENTS_BODY_VALID
    + (' THEN b."run_id" ELSE NULL END AS "run_id",\n  CASE WHEN ')
    + _SQLITE_EVENTS_BODY_VALID
    + (' THEN b."step" ELSE NULL END AS "step",\n  CASE WHEN ')
    + _SQLITE_EVENTS_BODY_VALID
    + (' THEN b."artifact" ELSE NULL END AS "artifact",\n  CASE WHEN ')
    + _SQLITE_EVENTS_BODY_VALID
    + (
        ' THEN b."hash" ELSE NULL END AS "hash",\n  p.__ordinal AS source_or'
        "dinal,\n  p.__bytes AS native_row_bytes,\n  CASE WHEN "
    )
    + _SQLITE_EVENTS_BODY_VALID
    + (
        ' THEN 0 ELSE 1 END AS invalid_row\nFROM selected AS p JOIN "events"'
        ' AS b ON b."run_id" = p.__k0 AND b."step" = p.__k1\nORDER BY p.__or'
        "dinal LIMIT 4097"
    )
)

_SQLITE_JOBS_CANDIDATES = (
    'WITH candidate AS MATERIALIZED (\n  SELECT s."id" AS __k0,\n    (COA'
    'LESCE(length(CAST(s."id" AS BLOB)),0) + COALESCE(length(CAST(s."ki'
    'nd" AS BLOB)),0) + COALESCE(length(CAST(s."created" AS BLOB)),0) +'
    ' COALESCE(length(CAST(s."payload" AS BLOB)),0) + COALESCE(length(C'
    'AST(s."status" AS BLOB)),0) + COALESCE(length(CAST(s."owner" AS BL'
    'OB)),0) + COALESCE(length(CAST(s."lease_until" AS BLOB)),0) + COAL'
    'ESCE(length(CAST(s."cancel" AS BLOB)),0) + COALESCE(length(CAST(s.'
    '"budget" AS BLOB)),0) + COALESCE(length(CAST(s."reserved" AS BLOB)'
    '),0) + COALESCE(length(CAST(s."result" AS BLOB)),0) + COALESCE(len'
    'gth(CAST(s."error" AS BLOB)),0) + COALESCE(length(CAST(s."actor" A'
    "S BLOB)),0)) AS __bytes,\n    CASE WHEN (typeof(s.\"id\") IN ('null',"
    "'integer','text') OR (typeof(s.\"id\")='real' AND s.\"id\" BETWEEN -1."
    '7976931348623157e308 AND 1.7976931348623157e308)) AND (typeof(s."k'
    "ind\") IN ('null','integer','text') OR (typeof(s.\"kind\")='real' AND"
    ' s."kind" BETWEEN -1.7976931348623157e308 AND 1.7976931348623157e3'
    "08)) AND (typeof(s.\"created\") IN ('null','integer','text') OR (typ"
    'eof(s."created")=\'real\' AND s."created" BETWEEN -1.797693134862315'
    '7e308 AND 1.7976931348623157e308)) AND (typeof(s."payload") IN (\'n'
    "ull','integer','text') OR (typeof(s.\"payload\")='real' AND s.\"paylo"
    'ad" BETWEEN -1.7976931348623157e308 AND 1.7976931348623157e308)) A'
    "ND (typeof(s.\"status\") IN ('null','integer','text') OR (typeof(s.\""
    'status")=\'real\' AND s."status" BETWEEN -1.7976931348623157e308 AND'
    " 1.7976931348623157e308)) AND (typeof(s.\"owner\") IN ('null','integ"
    "er','text') OR (typeof(s.\"owner\")='real' AND s.\"owner\" BETWEEN -1."
    '7976931348623157e308 AND 1.7976931348623157e308)) AND (typeof(s."l'
    "ease_until\") IN ('null','integer','text') OR (typeof(s.\"lease_unti"
    'l")=\'real\' AND s."lease_until" BETWEEN -1.7976931348623157e308 AND'
    " 1.7976931348623157e308)) AND (typeof(s.\"cancel\") IN ('null','inte"
    "ger','text') OR (typeof(s.\"cancel\")='real' AND s.\"cancel\" BETWEEN "
    "-1.7976931348623157e308 AND 1.7976931348623157e308)) AND (typeof(s"
    ".\"budget\") IN ('null','integer','text') OR (typeof(s.\"budget\")='re"
    'al\' AND s."budget" BETWEEN -1.7976931348623157e308 AND 1.797693134'
    "8623157e308)) AND (typeof(s.\"reserved\") IN ('null','integer','text"
    '\') OR (typeof(s."reserved")=\'real\' AND s."reserved" BETWEEN -1.797'
    '6931348623157e308 AND 1.7976931348623157e308)) AND (typeof(s."resu'
    "lt\") IN ('null','integer','text') OR (typeof(s.\"result\")='real' AN"
    'D s."result" BETWEEN -1.7976931348623157e308 AND 1.797693134862315'
    "7e308)) AND (typeof(s.\"error\") IN ('null','integer','text') OR (ty"
    'peof(s."error")=\'real\' AND s."error" BETWEEN -1.7976931348623157e3'
    "08 AND 1.7976931348623157e308)) AND (typeof(s.\"actor\") IN ('null',"
    "'integer','text') OR (typeof(s.\"actor\")='real' AND s.\"actor\" BETWE"
    'EN -1.7976931348623157e308 AND 1.7976931348623157e308)) AND s."id"'
    ' IS NOT NULL THEN 0 ELSE 1 END AS __invalid\n  FROM "jobs" AS s WHE'
    "RE "
)

_SQLITE_JOBS_ORDER = (
    '\n  ORDER BY s."id" LIMIT 4096\n), ordered AS MATERIALIZED (\n  SELEC'
    "T candidate.*, row_number() OVER (ORDER BY __k0) AS __ordinal,\n   "
    " sum(__bytes) OVER (ORDER BY __k0 ROWS BETWEEN UNBOUNDED PRECEDING"
    " AND CURRENT ROW) AS __running\n  FROM candidate\n)"
)

_SQLITE_JOBS_FIRST = _SQLITE_JOBS_CANDIDATES + "TRUE" + _SQLITE_JOBS_ORDER
_SQLITE_JOBS_NEXT = _SQLITE_JOBS_CANDIDATES + ('s."id" > :last_key') + _SQLITE_JOBS_ORDER

_SQLITE_JOBS_BODY_VALID = (
    "p.__invalid=0 AND ((typeof(b.\"id\") IN ('null','integer','text') OR"
    ' (typeof(b."id")=\'real\' AND b."id" BETWEEN -1.7976931348623157e308'
    " AND 1.7976931348623157e308)) AND (typeof(b.\"kind\") IN ('null','in"
    "teger','text') OR (typeof(b.\"kind\")='real' AND b.\"kind\" BETWEEN -1"
    '.7976931348623157e308 AND 1.7976931348623157e308)) AND (typeof(b."'
    "created\") IN ('null','integer','text') OR (typeof(b.\"created\")='re"
    'al\' AND b."created" BETWEEN -1.7976931348623157e308 AND 1.79769313'
    "48623157e308)) AND (typeof(b.\"payload\") IN ('null','integer','text"
    '\') OR (typeof(b."payload")=\'real\' AND b."payload" BETWEEN -1.79769'
    '31348623157e308 AND 1.7976931348623157e308)) AND (typeof(b."status'
    "\") IN ('null','integer','text') OR (typeof(b.\"status\")='real' AND "
    'b."status" BETWEEN -1.7976931348623157e308 AND 1.7976931348623157e'
    "308)) AND (typeof(b.\"owner\") IN ('null','integer','text') OR (type"
    'of(b."owner")=\'real\' AND b."owner" BETWEEN -1.7976931348623157e308'
    ' AND 1.7976931348623157e308)) AND (typeof(b."lease_until") IN (\'nu'
    "ll','integer','text') OR (typeof(b.\"lease_until\")='real' AND b.\"le"
    'ase_until" BETWEEN -1.7976931348623157e308 AND 1.7976931348623157e'
    "308)) AND (typeof(b.\"cancel\") IN ('null','integer','text') OR (typ"
    'eof(b."cancel")=\'real\' AND b."cancel" BETWEEN -1.7976931348623157e'
    '308 AND 1.7976931348623157e308)) AND (typeof(b."budget") IN (\'null'
    "','integer','text') OR (typeof(b.\"budget\")='real' AND b.\"budget\" B"
    "ETWEEN -1.7976931348623157e308 AND 1.7976931348623157e308)) AND (t"
    "ypeof(b.\"reserved\") IN ('null','integer','text') OR (typeof(b.\"res"
    'erved")=\'real\' AND b."reserved" BETWEEN -1.7976931348623157e308 AN'
    "D 1.7976931348623157e308)) AND (typeof(b.\"result\") IN ('null','int"
    "eger','text') OR (typeof(b.\"result\")='real' AND b.\"result\" BETWEEN"
    " -1.7976931348623157e308 AND 1.7976931348623157e308)) AND (typeof("
    "b.\"error\") IN ('null','integer','text') OR (typeof(b.\"error\")='rea"
    'l\' AND b."error" BETWEEN -1.7976931348623157e308 AND 1.79769313486'
    "23157e308)) AND (typeof(b.\"actor\") IN ('null','integer','text') OR"
    ' (typeof(b."actor")=\'real\' AND b."actor" BETWEEN -1.79769313486231'
    '57e308 AND 1.7976931348623157e308)) AND b."id" IS NOT NULL) AND (C'
    'OALESCE(length(CAST(b."id" AS BLOB)),0) + COALESCE(length(CAST(b."'
    'kind" AS BLOB)),0) + COALESCE(length(CAST(b."created" AS BLOB)),0)'
    ' + COALESCE(length(CAST(b."payload" AS BLOB)),0) + COALESCE(length'
    '(CAST(b."status" AS BLOB)),0) + COALESCE(length(CAST(b."owner" AS '
    'BLOB)),0) + COALESCE(length(CAST(b."lease_until" AS BLOB)),0) + CO'
    'ALESCE(length(CAST(b."cancel" AS BLOB)),0) + COALESCE(length(CAST('
    'b."budget" AS BLOB)),0) + COALESCE(length(CAST(b."reserved" AS BLO'
    'B)),0) + COALESCE(length(CAST(b."result" AS BLOB)),0) + COALESCE(l'
    'ength(CAST(b."error" AS BLOB)),0) + COALESCE(length(CAST(b."actor"'
    " AS BLOB)),0))=p.__bytes AND p.__bytes<=16777216"
)

_SQLITE_JOBS_BODY = (
    ("CASE WHEN ")
    + _SQLITE_JOBS_BODY_VALID
    + (' THEN b."id" ELSE NULL END AS "id",\n  CASE WHEN ')
    + _SQLITE_JOBS_BODY_VALID
    + (' THEN b."kind" ELSE NULL END AS "kind",\n  CASE WHEN ')
    + _SQLITE_JOBS_BODY_VALID
    + (' THEN b."created" ELSE NULL END AS "created",\n  CASE WHEN ')
    + _SQLITE_JOBS_BODY_VALID
    + (' THEN b."payload" ELSE NULL END AS "payload",\n  CASE WHEN ')
    + _SQLITE_JOBS_BODY_VALID
    + (' THEN b."status" ELSE NULL END AS "status",\n  CASE WHEN ')
    + _SQLITE_JOBS_BODY_VALID
    + (' THEN b."owner" ELSE NULL END AS "owner",\n  CASE WHEN ')
    + _SQLITE_JOBS_BODY_VALID
    + (' THEN b."lease_until" ELSE NULL END AS "lease_until",\n  CASE WHEN ')
    + _SQLITE_JOBS_BODY_VALID
    + (' THEN b."cancel" ELSE NULL END AS "cancel",\n  CASE WHEN ')
    + _SQLITE_JOBS_BODY_VALID
    + (' THEN b."budget" ELSE NULL END AS "budget",\n  CASE WHEN ')
    + _SQLITE_JOBS_BODY_VALID
    + (' THEN b."reserved" ELSE NULL END AS "reserved",\n  CASE WHEN ')
    + _SQLITE_JOBS_BODY_VALID
    + (' THEN b."result" ELSE NULL END AS "result",\n  CASE WHEN ')
    + _SQLITE_JOBS_BODY_VALID
    + (' THEN b."error" ELSE NULL END AS "error",\n  CASE WHEN ')
    + _SQLITE_JOBS_BODY_VALID
    + (
        ' THEN b."actor" ELSE NULL END AS "actor",\n  p.__ordinal AS source_'
        "ordinal,\n  p.__bytes AS native_row_bytes,\n  CASE WHEN "
    )
    + _SQLITE_JOBS_BODY_VALID
    + (
        ' THEN 0 ELSE 1 END AS invalid_row\nFROM selected AS p JOIN "jobs" A'
        'S b ON b."id" = p.__k0\nORDER BY p.__ordinal LIMIT 4097'
    )
)

_SQLITE_RECORDS_CANDIDATES = (
    'WITH candidate AS MATERIALIZED (\n  SELECT s."id" AS __k0,\n    (COA'
    'LESCE(length(CAST(s."id" AS BLOB)),0) + COALESCE(length(CAST(s."ki'
    'nd" AS BLOB)),0) + COALESCE(length(CAST(s."created" AS BLOB)),0) +'
    ' COALESCE(length(CAST(s."data" AS BLOB)),0)) AS __bytes,\n    CASE '
    "WHEN (typeof(s.\"id\") IN ('null','integer','text') OR (typeof(s.\"id"
    '")=\'real\' AND s."id" BETWEEN -1.7976931348623157e308 AND 1.7976931'
    "348623157e308)) AND (typeof(s.\"kind\") IN ('null','integer','text')"
    ' OR (typeof(s."kind")=\'real\' AND s."kind" BETWEEN -1.7976931348623'
    '157e308 AND 1.7976931348623157e308)) AND (typeof(s."created") IN ('
    "'null','integer','text') OR (typeof(s.\"created\")='real' AND s.\"cre"
    'ated" BETWEEN -1.7976931348623157e308 AND 1.7976931348623157e308))'
    " AND (typeof(CAST(s.\"data\" AS TEXT)) IN ('null','integer','text') "
    'OR (typeof(CAST(s."data" AS TEXT))=\'real\' AND CAST(s."data" AS TEX'
    "T) BETWEEN -1.7976931348623157e308 AND 1.7976931348623157e308)) AN"
    'D s."id" IS NOT NULL THEN 0 ELSE 1 END AS __invalid\n  FROM "record'
    's" AS s WHERE '
)

_SQLITE_RECORDS_ORDER = (
    '\n  ORDER BY s."id" LIMIT 4096\n), ordered AS MATERIALIZED (\n  SELEC'
    "T candidate.*, row_number() OVER (ORDER BY __k0) AS __ordinal,\n   "
    " sum(__bytes) OVER (ORDER BY __k0 ROWS BETWEEN UNBOUNDED PRECEDING"
    " AND CURRENT ROW) AS __running\n  FROM candidate\n)"
)

_SQLITE_RECORDS_FIRST = _SQLITE_RECORDS_CANDIDATES + "TRUE" + _SQLITE_RECORDS_ORDER
_SQLITE_RECORDS_NEXT = _SQLITE_RECORDS_CANDIDATES + ('s."id" > :last_key') + _SQLITE_RECORDS_ORDER

_SQLITE_RECORDS_BODY_VALID = (
    "p.__invalid=0 AND ((typeof(b.\"id\") IN ('null','integer','text') OR"
    ' (typeof(b."id")=\'real\' AND b."id" BETWEEN -1.7976931348623157e308'
    " AND 1.7976931348623157e308)) AND (typeof(b.\"kind\") IN ('null','in"
    "teger','text') OR (typeof(b.\"kind\")='real' AND b.\"kind\" BETWEEN -1"
    '.7976931348623157e308 AND 1.7976931348623157e308)) AND (typeof(b."'
    "created\") IN ('null','integer','text') OR (typeof(b.\"created\")='re"
    'al\' AND b."created" BETWEEN -1.7976931348623157e308 AND 1.79769313'
    "48623157e308)) AND (typeof(CAST(b.\"data\" AS TEXT)) IN ('null','int"
    "eger','text') OR (typeof(CAST(b.\"data\" AS TEXT))='real' AND CAST(b"
    '."data" AS TEXT) BETWEEN -1.7976931348623157e308 AND 1.79769313486'
    '23157e308)) AND b."id" IS NOT NULL) AND (COALESCE(length(CAST(b."i'
    'd" AS BLOB)),0) + COALESCE(length(CAST(b."kind" AS BLOB)),0) + COA'
    'LESCE(length(CAST(b."created" AS BLOB)),0) + COALESCE(length(CAST('
    'b."data" AS BLOB)),0))=p.__bytes AND p.__bytes<=16777216'
)

_SQLITE_RECORDS_BODY = (
    ("CASE WHEN ")
    + _SQLITE_RECORDS_BODY_VALID
    + (' THEN b."id" ELSE NULL END AS "id",\n  CASE WHEN ')
    + _SQLITE_RECORDS_BODY_VALID
    + (' THEN b."kind" ELSE NULL END AS "kind",\n  CASE WHEN ')
    + _SQLITE_RECORDS_BODY_VALID
    + (' THEN b."created" ELSE NULL END AS "created",\n  CASE WHEN ')
    + _SQLITE_RECORDS_BODY_VALID
    + (
        ' THEN CAST(b."data" AS TEXT) ELSE NULL END AS "data",\n  p.__ordina'
        "l AS source_ordinal,\n  p.__bytes AS native_row_bytes,\n  CASE WHEN "
    )
    + _SQLITE_RECORDS_BODY_VALID
    + (
        ' THEN 0 ELSE 1 END AS invalid_row\nFROM selected AS p JOIN "records'
        '" AS b ON b."id" = p.__k0\nORDER BY p.__ordinal LIMIT 4097'
    )
)

_POSTGRESQL_API_KEYS_CANDIDATES = (
    'WITH candidate AS MATERIALIZED (\n  SELECT s."id" AS __k0,\n    (COA'
    'LESCE(octet_length(CAST(s."id" AS TEXT)),0) + COALESCE(octet_lengt'
    'h(CAST(s."hash" AS TEXT)),0) + COALESCE(octet_length(CAST(s."role"'
    ' AS TEXT)),0) + COALESCE(octet_length(CAST(s."name" AS TEXT)),0) +'
    ' COALESCE(octet_length(CAST(s."expires" AS TEXT)),0) + COALESCE(oc'
    'tet_length(CAST(s."revoked" AS TEXT)),0)) AS __bytes,\n    CASE WHE'
    'N (s."expires" IS NULL OR (s."expires" > \'-Infinity\'::double preci'
    'sion AND s."expires" < \'Infinity\'::double precision)) AND s."id" I'
    'S NOT NULL THEN 0 ELSE 1 END AS __invalid\n  FROM "api_keys" AS s W'
    "HERE "
)

_POSTGRESQL_API_KEYS_ORDER = (
    '\n  ORDER BY s."id" LIMIT 4096\n), ordered AS MATERIALIZED (\n  SELEC'
    "T candidate.*, row_number() OVER (ORDER BY __k0) AS __ordinal,\n   "
    " sum(__bytes) OVER (ORDER BY __k0 ROWS BETWEEN UNBOUNDED PRECEDING"
    " AND CURRENT ROW) AS __running\n  FROM candidate\n)"
)

_POSTGRESQL_API_KEYS_FIRST = _POSTGRESQL_API_KEYS_CANDIDATES + "TRUE" + _POSTGRESQL_API_KEYS_ORDER
_POSTGRESQL_API_KEYS_NEXT = (
    _POSTGRESQL_API_KEYS_CANDIDATES + ('s."id" > :last_key') + _POSTGRESQL_API_KEYS_ORDER
)

_POSTGRESQL_API_KEYS_BODY_VALID = (
    'p.__invalid=0 AND ((b."expires" IS NULL OR (b."expires" > \'-Infini'
    "ty'::double precision AND b.\"expires\" < 'Infinity'::double precisi"
    'on)) AND b."id" IS NOT NULL) AND (COALESCE(octet_length(CAST(b."id'
    '" AS TEXT)),0) + COALESCE(octet_length(CAST(b."hash" AS TEXT)),0) '
    '+ COALESCE(octet_length(CAST(b."role" AS TEXT)),0) + COALESCE(octe'
    't_length(CAST(b."name" AS TEXT)),0) + COALESCE(octet_length(CAST(b'
    '."expires" AS TEXT)),0) + COALESCE(octet_length(CAST(b."revoked" A'
    "S TEXT)),0))=p.__bytes AND p.__bytes<=16777216"
)

_POSTGRESQL_API_KEYS_BODY = (
    ("CASE WHEN ")
    + _POSTGRESQL_API_KEYS_BODY_VALID
    + (' THEN b."id" ELSE NULL END AS "id",\n  CASE WHEN ')
    + _POSTGRESQL_API_KEYS_BODY_VALID
    + (' THEN b."hash" ELSE NULL END AS "hash",\n  CASE WHEN ')
    + _POSTGRESQL_API_KEYS_BODY_VALID
    + (' THEN b."role" ELSE NULL END AS "role",\n  CASE WHEN ')
    + _POSTGRESQL_API_KEYS_BODY_VALID
    + (' THEN b."name" ELSE NULL END AS "name",\n  CASE WHEN ')
    + _POSTGRESQL_API_KEYS_BODY_VALID
    + (' THEN b."expires" ELSE NULL END AS "expires",\n  CASE WHEN ')
    + _POSTGRESQL_API_KEYS_BODY_VALID
    + (
        ' THEN b."revoked" ELSE NULL END AS "revoked",\n  p.__ordinal AS sou'
        "rce_ordinal,\n  p.__bytes AS native_row_bytes,\n  CASE WHEN "
    )
    + _POSTGRESQL_API_KEYS_BODY_VALID
    + (
        ' THEN 0 ELSE 1 END AS invalid_row\nFROM selected AS p JOIN "api_key'
        's" AS b ON b."id" = p.__k0\nORDER BY p.__ordinal LIMIT 4097'
    )
)

_POSTGRESQL_AUDIT_CANDIDATES = (
    'WITH candidate AS MATERIALIZED (\n  SELECT s."id" AS __k0,\n    (COA'
    'LESCE(octet_length(CAST(s."id" AS TEXT)),0) + COALESCE(octet_lengt'
    'h(CAST(s."created" AS TEXT)),0) + COALESCE(octet_length(CAST(s."ac'
    'tor" AS TEXT)),0) + COALESCE(octet_length(CAST(s."action" AS TEXT)'
    '),0) + COALESCE(octet_length(CAST(s."target" AS TEXT)),0)) AS __by'
    'tes,\n    CASE WHEN (s."created" IS NULL OR (s."created" > \'-Infini'
    "ty'::double precision AND s.\"created\" < 'Infinity'::double precisi"
    'on)) AND s."id" IS NOT NULL THEN 0 ELSE 1 END AS __invalid\n  FROM '
    '"audit" AS s WHERE '
)

_POSTGRESQL_AUDIT_ORDER = (
    '\n  ORDER BY s."id" LIMIT 4096\n), ordered AS MATERIALIZED (\n  SELEC'
    "T candidate.*, row_number() OVER (ORDER BY __k0) AS __ordinal,\n   "
    " sum(__bytes) OVER (ORDER BY __k0 ROWS BETWEEN UNBOUNDED PRECEDING"
    " AND CURRENT ROW) AS __running\n  FROM candidate\n)"
)

_POSTGRESQL_AUDIT_FIRST = _POSTGRESQL_AUDIT_CANDIDATES + "TRUE" + _POSTGRESQL_AUDIT_ORDER
_POSTGRESQL_AUDIT_NEXT = (
    _POSTGRESQL_AUDIT_CANDIDATES + ('s."id" > :last_key') + _POSTGRESQL_AUDIT_ORDER
)

_POSTGRESQL_AUDIT_BODY_VALID = (
    'p.__invalid=0 AND ((b."created" IS NULL OR (b."created" > \'-Infini'
    "ty'::double precision AND b.\"created\" < 'Infinity'::double precisi"
    'on)) AND b."id" IS NOT NULL) AND (COALESCE(octet_length(CAST(b."id'
    '" AS TEXT)),0) + COALESCE(octet_length(CAST(b."created" AS TEXT)),'
    '0) + COALESCE(octet_length(CAST(b."actor" AS TEXT)),0) + COALESCE('
    'octet_length(CAST(b."action" AS TEXT)),0) + COALESCE(octet_length('
    'CAST(b."target" AS TEXT)),0))=p.__bytes AND p.__bytes<=16777216'
)

_POSTGRESQL_AUDIT_BODY = (
    ("CASE WHEN ")
    + _POSTGRESQL_AUDIT_BODY_VALID
    + (' THEN b."id" ELSE NULL END AS "id",\n  CASE WHEN ')
    + _POSTGRESQL_AUDIT_BODY_VALID
    + (' THEN b."created" ELSE NULL END AS "created",\n  CASE WHEN ')
    + _POSTGRESQL_AUDIT_BODY_VALID
    + (' THEN b."actor" ELSE NULL END AS "actor",\n  CASE WHEN ')
    + _POSTGRESQL_AUDIT_BODY_VALID
    + (' THEN b."action" ELSE NULL END AS "action",\n  CASE WHEN ')
    + _POSTGRESQL_AUDIT_BODY_VALID
    + (
        ' THEN b."target" ELSE NULL END AS "target",\n  p.__ordinal AS sourc'
        "e_ordinal,\n  p.__bytes AS native_row_bytes,\n  CASE WHEN "
    )
    + _POSTGRESQL_AUDIT_BODY_VALID
    + (
        ' THEN 0 ELSE 1 END AS invalid_row\nFROM selected AS p JOIN "audit" '
        'AS b ON b."id" = p.__k0\nORDER BY p.__ordinal LIMIT 4097'
    )
)

_POSTGRESQL_EVENTS_CANDIDATES = (
    'WITH candidate AS MATERIALIZED (\n  SELECT s."run_id" AS __k0, s."s'
    'tep" AS __k1,\n    (COALESCE(octet_length(CAST(s."run_id" AS TEXT))'
    ',0) + COALESCE(octet_length(CAST(s."step" AS TEXT)),0) + COALESCE('
    'octet_length(CAST(s."artifact" AS TEXT)),0) + COALESCE(octet_lengt'
    'h(CAST(s."hash" AS TEXT)),0)) AS __bytes,\n    CASE WHEN s."run_id"'
    ' IS NOT NULL AND s."step" IS NOT NULL THEN 0 ELSE 1 END AS __inval'
    'id\n  FROM "events" AS s WHERE '
)

_POSTGRESQL_EVENTS_ORDER = (
    '\n  ORDER BY s."run_id", s."step" LIMIT 4096\n), ordered AS MATERIAL'
    "IZED (\n  SELECT candidate.*, row_number() OVER (ORDER BY __k0, __k"
    "1) AS __ordinal,\n    sum(__bytes) OVER (ORDER BY __k0, __k1 ROWS B"
    "ETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS __running\n  FROM ca"
    "ndidate\n)"
)

_POSTGRESQL_EVENTS_FIRST = _POSTGRESQL_EVENTS_CANDIDATES + "TRUE" + _POSTGRESQL_EVENTS_ORDER
_POSTGRESQL_EVENTS_NEXT = (
    _POSTGRESQL_EVENTS_CANDIDATES
    + ('(s."run_id" > :last_run OR (s."run_id" = :last_run AND s."step" > :last_step))')
    + _POSTGRESQL_EVENTS_ORDER
)

_POSTGRESQL_EVENTS_BODY_VALID = (
    'p.__invalid=0 AND (b."run_id" IS NOT NULL AND b."step" IS NOT NULL'
    ') AND (COALESCE(octet_length(CAST(b."run_id" AS TEXT)),0) + COALES'
    'CE(octet_length(CAST(b."step" AS TEXT)),0) + COALESCE(octet_length'
    '(CAST(b."artifact" AS TEXT)),0) + COALESCE(octet_length(CAST(b."ha'
    'sh" AS TEXT)),0))=p.__bytes AND p.__bytes<=16777216'
)

_POSTGRESQL_EVENTS_BODY = (
    ("CASE WHEN ")
    + _POSTGRESQL_EVENTS_BODY_VALID
    + (' THEN b."run_id" ELSE NULL END AS "run_id",\n  CASE WHEN ')
    + _POSTGRESQL_EVENTS_BODY_VALID
    + (' THEN b."step" ELSE NULL END AS "step",\n  CASE WHEN ')
    + _POSTGRESQL_EVENTS_BODY_VALID
    + (' THEN b."artifact" ELSE NULL END AS "artifact",\n  CASE WHEN ')
    + _POSTGRESQL_EVENTS_BODY_VALID
    + (
        ' THEN b."hash" ELSE NULL END AS "hash",\n  p.__ordinal AS source_or'
        "dinal,\n  p.__bytes AS native_row_bytes,\n  CASE WHEN "
    )
    + _POSTGRESQL_EVENTS_BODY_VALID
    + (
        ' THEN 0 ELSE 1 END AS invalid_row\nFROM selected AS p JOIN "events"'
        ' AS b ON b."run_id" = p.__k0 AND b."step" = p.__k1\nORDER BY p.__or'
        "dinal LIMIT 4097"
    )
)

_POSTGRESQL_JOBS_CANDIDATES = (
    'WITH candidate AS MATERIALIZED (\n  SELECT s."id" AS __k0,\n    (COA'
    'LESCE(octet_length(CAST(s."id" AS TEXT)),0) + COALESCE(octet_lengt'
    'h(CAST(s."kind" AS TEXT)),0) + COALESCE(octet_length(CAST(s."creat'
    'ed" AS TEXT)),0) + COALESCE(octet_length(CAST(s."payload" AS TEXT)'
    '),0) + COALESCE(octet_length(CAST(s."status" AS TEXT)),0) + COALES'
    'CE(octet_length(CAST(s."owner" AS TEXT)),0) + COALESCE(octet_lengt'
    'h(CAST(s."lease_until" AS TEXT)),0) + COALESCE(octet_length(CAST(s'
    '."cancel" AS TEXT)),0) + COALESCE(octet_length(CAST(s."budget" AS '
    'TEXT)),0) + COALESCE(octet_length(CAST(s."reserved" AS TEXT)),0) +'
    ' COALESCE(octet_length(CAST(s."result" AS TEXT)),0) + COALESCE(oct'
    'et_length(CAST(s."error" AS TEXT)),0) + COALESCE(octet_length(CAST'
    '(s."actor" AS TEXT)),0)) AS __bytes,\n    CASE WHEN (s."created" IS'
    ' NULL OR (s."created" > \'-Infinity\'::double precision AND s."creat'
    'ed" < \'Infinity\'::double precision)) AND (s."lease_until" IS NULL '
    'OR (s."lease_until" > \'-Infinity\'::double precision AND s."lease_u'
    'ntil" < \'Infinity\'::double precision)) AND s."id" IS NOT NULL THEN'
    ' 0 ELSE 1 END AS __invalid\n  FROM "jobs" AS s WHERE '
)

_POSTGRESQL_JOBS_ORDER = (
    '\n  ORDER BY s."id" LIMIT 4096\n), ordered AS MATERIALIZED (\n  SELEC'
    "T candidate.*, row_number() OVER (ORDER BY __k0) AS __ordinal,\n   "
    " sum(__bytes) OVER (ORDER BY __k0 ROWS BETWEEN UNBOUNDED PRECEDING"
    " AND CURRENT ROW) AS __running\n  FROM candidate\n)"
)

_POSTGRESQL_JOBS_FIRST = _POSTGRESQL_JOBS_CANDIDATES + "TRUE" + _POSTGRESQL_JOBS_ORDER
_POSTGRESQL_JOBS_NEXT = (
    _POSTGRESQL_JOBS_CANDIDATES + ('s."id" > :last_key') + _POSTGRESQL_JOBS_ORDER
)

_POSTGRESQL_JOBS_BODY_VALID = (
    'p.__invalid=0 AND ((b."created" IS NULL OR (b."created" > \'-Infini'
    "ty'::double precision AND b.\"created\" < 'Infinity'::double precisi"
    'on)) AND (b."lease_until" IS NULL OR (b."lease_until" > \'-Infinity'
    "'::double precision AND b.\"lease_until\" < 'Infinity'::double preci"
    'sion)) AND b."id" IS NOT NULL) AND (COALESCE(octet_length(CAST(b."'
    'id" AS TEXT)),0) + COALESCE(octet_length(CAST(b."kind" AS TEXT)),0'
    ') + COALESCE(octet_length(CAST(b."created" AS TEXT)),0) + COALESCE'
    '(octet_length(CAST(b."payload" AS TEXT)),0) + COALESCE(octet_lengt'
    'h(CAST(b."status" AS TEXT)),0) + COALESCE(octet_length(CAST(b."own'
    'er" AS TEXT)),0) + COALESCE(octet_length(CAST(b."lease_until" AS T'
    'EXT)),0) + COALESCE(octet_length(CAST(b."cancel" AS TEXT)),0) + CO'
    'ALESCE(octet_length(CAST(b."budget" AS TEXT)),0) + COALESCE(octet_'
    'length(CAST(b."reserved" AS TEXT)),0) + COALESCE(octet_length(CAST'
    '(b."result" AS TEXT)),0) + COALESCE(octet_length(CAST(b."error" AS'
    ' TEXT)),0) + COALESCE(octet_length(CAST(b."actor" AS TEXT)),0))=p.'
    "__bytes AND p.__bytes<=16777216"
)

_POSTGRESQL_JOBS_BODY = (
    ("CASE WHEN ")
    + _POSTGRESQL_JOBS_BODY_VALID
    + (' THEN b."id" ELSE NULL END AS "id",\n  CASE WHEN ')
    + _POSTGRESQL_JOBS_BODY_VALID
    + (' THEN b."kind" ELSE NULL END AS "kind",\n  CASE WHEN ')
    + _POSTGRESQL_JOBS_BODY_VALID
    + (' THEN b."created" ELSE NULL END AS "created",\n  CASE WHEN ')
    + _POSTGRESQL_JOBS_BODY_VALID
    + (' THEN b."payload" ELSE NULL END AS "payload",\n  CASE WHEN ')
    + _POSTGRESQL_JOBS_BODY_VALID
    + (' THEN b."status" ELSE NULL END AS "status",\n  CASE WHEN ')
    + _POSTGRESQL_JOBS_BODY_VALID
    + (' THEN b."owner" ELSE NULL END AS "owner",\n  CASE WHEN ')
    + _POSTGRESQL_JOBS_BODY_VALID
    + (' THEN b."lease_until" ELSE NULL END AS "lease_until",\n  CASE WHEN ')
    + _POSTGRESQL_JOBS_BODY_VALID
    + (' THEN b."cancel" ELSE NULL END AS "cancel",\n  CASE WHEN ')
    + _POSTGRESQL_JOBS_BODY_VALID
    + (' THEN b."budget" ELSE NULL END AS "budget",\n  CASE WHEN ')
    + _POSTGRESQL_JOBS_BODY_VALID
    + (' THEN b."reserved" ELSE NULL END AS "reserved",\n  CASE WHEN ')
    + _POSTGRESQL_JOBS_BODY_VALID
    + (' THEN b."result" ELSE NULL END AS "result",\n  CASE WHEN ')
    + _POSTGRESQL_JOBS_BODY_VALID
    + (' THEN b."error" ELSE NULL END AS "error",\n  CASE WHEN ')
    + _POSTGRESQL_JOBS_BODY_VALID
    + (
        ' THEN b."actor" ELSE NULL END AS "actor",\n  p.__ordinal AS source_'
        "ordinal,\n  p.__bytes AS native_row_bytes,\n  CASE WHEN "
    )
    + _POSTGRESQL_JOBS_BODY_VALID
    + (
        ' THEN 0 ELSE 1 END AS invalid_row\nFROM selected AS p JOIN "jobs" A'
        'S b ON b."id" = p.__k0\nORDER BY p.__ordinal LIMIT 4097'
    )
)

_POSTGRESQL_RECORDS_CANDIDATES = (
    'WITH candidate AS MATERIALIZED (\n  SELECT s."id" AS __k0,\n    (COA'
    'LESCE(octet_length(CAST(s."id" AS TEXT)),0) + COALESCE(octet_lengt'
    'h(CAST(s."kind" AS TEXT)),0) + COALESCE(octet_length(CAST(s."creat'
    'ed" AS TEXT)),0) + COALESCE(octet_length(CAST(s."data" AS TEXT)),0'
    ')) AS __bytes,\n    CASE WHEN (s."created" IS NULL OR (s."created" '
    "> '-Infinity'::double precision AND s.\"created\" < 'Infinity'::doub"
    'le precision)) AND s."id" IS NOT NULL THEN 0 ELSE 1 END AS __inval'
    'id\n  FROM "records" AS s WHERE '
)

_POSTGRESQL_RECORDS_ORDER = (
    '\n  ORDER BY s."id" LIMIT 4096\n), ordered AS MATERIALIZED (\n  SELEC'
    "T candidate.*, row_number() OVER (ORDER BY __k0) AS __ordinal,\n   "
    " sum(__bytes) OVER (ORDER BY __k0 ROWS BETWEEN UNBOUNDED PRECEDING"
    " AND CURRENT ROW) AS __running\n  FROM candidate\n)"
)

_POSTGRESQL_RECORDS_FIRST = _POSTGRESQL_RECORDS_CANDIDATES + "TRUE" + _POSTGRESQL_RECORDS_ORDER
_POSTGRESQL_RECORDS_NEXT = (
    _POSTGRESQL_RECORDS_CANDIDATES + ('s."id" > :last_key') + _POSTGRESQL_RECORDS_ORDER
)

_POSTGRESQL_RECORDS_BODY_VALID = (
    'p.__invalid=0 AND ((b."created" IS NULL OR (b."created" > \'-Infini'
    "ty'::double precision AND b.\"created\" < 'Infinity'::double precisi"
    'on)) AND b."id" IS NOT NULL) AND (COALESCE(octet_length(CAST(b."id'
    '" AS TEXT)),0) + COALESCE(octet_length(CAST(b."kind" AS TEXT)),0) '
    '+ COALESCE(octet_length(CAST(b."created" AS TEXT)),0) + COALESCE(o'
    'ctet_length(CAST(b."data" AS TEXT)),0))=p.__bytes AND p.__bytes<=1'
    "6777216"
)

_POSTGRESQL_RECORDS_BODY = (
    ("CASE WHEN ")
    + _POSTGRESQL_RECORDS_BODY_VALID
    + (' THEN b."id" ELSE NULL END AS "id",\n  CASE WHEN ')
    + _POSTGRESQL_RECORDS_BODY_VALID
    + (' THEN b."kind" ELSE NULL END AS "kind",\n  CASE WHEN ')
    + _POSTGRESQL_RECORDS_BODY_VALID
    + (' THEN b."created" ELSE NULL END AS "created",\n  CASE WHEN ')
    + _POSTGRESQL_RECORDS_BODY_VALID
    + (
        ' THEN CAST(b."data" AS TEXT) ELSE NULL END AS "data",\n  p.__ordina'
        "l AS source_ordinal,\n  p.__bytes AS native_row_bytes,\n  CASE WHEN "
    )
    + _POSTGRESQL_RECORDS_BODY_VALID
    + (
        ' THEN 0 ELSE 1 END AS invalid_row\nFROM selected AS p JOIN "records'
        '" AS b ON b."id" = p.__k0\nORDER BY p.__ordinal LIMIT 4097'
    )
)

SQL = {
    ("sqlite", "source_gate_api_keys_first"): _SQLITE_API_KEYS_FIRST + _GATE,
    ("sqlite", "source_body_api_keys_first"): _SQLITE_API_KEYS_FIRST[:-2]
    + _SELECTED
    + _SQLITE_API_KEYS_BODY,
    ("sqlite", "source_gate_api_keys_next"): _SQLITE_API_KEYS_NEXT + _GATE,
    ("sqlite", "source_body_api_keys_next"): _SQLITE_API_KEYS_NEXT[:-2]
    + _SELECTED
    + _SQLITE_API_KEYS_BODY,
    ("sqlite", "source_gate_audit_first"): _SQLITE_AUDIT_FIRST + _GATE,
    ("sqlite", "source_body_audit_first"): _SQLITE_AUDIT_FIRST[:-2]
    + _SELECTED
    + _SQLITE_AUDIT_BODY,
    ("sqlite", "source_gate_audit_next"): _SQLITE_AUDIT_NEXT + _GATE,
    ("sqlite", "source_body_audit_next"): _SQLITE_AUDIT_NEXT[:-2] + _SELECTED + _SQLITE_AUDIT_BODY,
    ("sqlite", "source_gate_events_first"): _SQLITE_EVENTS_FIRST + _GATE,
    ("sqlite", "source_body_events_first"): _SQLITE_EVENTS_FIRST[:-2]
    + _SELECTED
    + _SQLITE_EVENTS_BODY,
    ("sqlite", "source_gate_events_next"): _SQLITE_EVENTS_NEXT + _GATE,
    ("sqlite", "source_body_events_next"): _SQLITE_EVENTS_NEXT[:-2]
    + _SELECTED
    + _SQLITE_EVENTS_BODY,
    ("sqlite", "source_gate_jobs_first"): _SQLITE_JOBS_FIRST + _GATE,
    ("sqlite", "source_body_jobs_first"): _SQLITE_JOBS_FIRST[:-2] + _SELECTED + _SQLITE_JOBS_BODY,
    ("sqlite", "source_gate_jobs_next"): _SQLITE_JOBS_NEXT + _GATE,
    ("sqlite", "source_body_jobs_next"): _SQLITE_JOBS_NEXT[:-2] + _SELECTED + _SQLITE_JOBS_BODY,
    ("sqlite", "source_gate_records_first"): _SQLITE_RECORDS_FIRST + _GATE,
    ("sqlite", "source_body_records_first"): _SQLITE_RECORDS_FIRST[:-2]
    + _SELECTED
    + _SQLITE_RECORDS_BODY,
    ("sqlite", "source_gate_records_next"): _SQLITE_RECORDS_NEXT + _GATE,
    ("sqlite", "source_body_records_next"): _SQLITE_RECORDS_NEXT[:-2]
    + _SELECTED
    + _SQLITE_RECORDS_BODY,
    ("postgresql", "source_gate_api_keys_first"): _POSTGRESQL_API_KEYS_FIRST + _GATE,
    ("postgresql", "source_body_api_keys_first"): _POSTGRESQL_API_KEYS_FIRST[:-2]
    + _SELECTED
    + _POSTGRESQL_API_KEYS_BODY,
    ("postgresql", "source_gate_api_keys_next"): _POSTGRESQL_API_KEYS_NEXT + _GATE,
    ("postgresql", "source_body_api_keys_next"): _POSTGRESQL_API_KEYS_NEXT[:-2]
    + _SELECTED
    + _POSTGRESQL_API_KEYS_BODY,
    ("postgresql", "source_gate_audit_first"): _POSTGRESQL_AUDIT_FIRST + _GATE,
    ("postgresql", "source_body_audit_first"): _POSTGRESQL_AUDIT_FIRST[:-2]
    + _SELECTED
    + _POSTGRESQL_AUDIT_BODY,
    ("postgresql", "source_gate_audit_next"): _POSTGRESQL_AUDIT_NEXT + _GATE,
    ("postgresql", "source_body_audit_next"): _POSTGRESQL_AUDIT_NEXT[:-2]
    + _SELECTED
    + _POSTGRESQL_AUDIT_BODY,
    ("postgresql", "source_gate_events_first"): _POSTGRESQL_EVENTS_FIRST + _GATE,
    ("postgresql", "source_body_events_first"): _POSTGRESQL_EVENTS_FIRST[:-2]
    + _SELECTED
    + _POSTGRESQL_EVENTS_BODY,
    ("postgresql", "source_gate_events_next"): _POSTGRESQL_EVENTS_NEXT + _GATE,
    ("postgresql", "source_body_events_next"): _POSTGRESQL_EVENTS_NEXT[:-2]
    + _SELECTED
    + _POSTGRESQL_EVENTS_BODY,
    ("postgresql", "source_gate_jobs_first"): _POSTGRESQL_JOBS_FIRST + _GATE,
    ("postgresql", "source_body_jobs_first"): _POSTGRESQL_JOBS_FIRST[:-2]
    + _SELECTED
    + _POSTGRESQL_JOBS_BODY,
    ("postgresql", "source_gate_jobs_next"): _POSTGRESQL_JOBS_NEXT + _GATE,
    ("postgresql", "source_body_jobs_next"): _POSTGRESQL_JOBS_NEXT[:-2]
    + _SELECTED
    + _POSTGRESQL_JOBS_BODY,
    ("postgresql", "source_gate_records_first"): _POSTGRESQL_RECORDS_FIRST + _GATE,
    ("postgresql", "source_body_records_first"): _POSTGRESQL_RECORDS_FIRST[:-2]
    + _SELECTED
    + _POSTGRESQL_RECORDS_BODY,
    ("postgresql", "source_gate_records_next"): _POSTGRESQL_RECORDS_NEXT + _GATE,
    ("postgresql", "source_body_records_next"): _POSTGRESQL_RECORDS_NEXT[:-2]
    + _SELECTED
    + _POSTGRESQL_RECORDS_BODY,
}
