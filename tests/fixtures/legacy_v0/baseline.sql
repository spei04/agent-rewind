-- Frozen synthetic SQLite representation of the unversioned baseline.
-- No production data; never load this fixture into a running deployment.
CREATE TABLE records (
 id VARCHAR(32) NOT NULL PRIMARY KEY, kind VARCHAR(20) NOT NULL,
 created FLOAT NOT NULL, data JSON NOT NULL
);
CREATE TABLE events (
 run_id VARCHAR(32) NOT NULL, step INTEGER NOT NULL,
 artifact VARCHAR(64) NOT NULL, hash VARCHAR(64) NOT NULL,
 PRIMARY KEY (run_id, step)
);
CREATE TABLE jobs (
 id VARCHAR(32) NOT NULL PRIMARY KEY, kind VARCHAR(20) NOT NULL,
 created FLOAT NOT NULL, payload VARCHAR(64) NOT NULL, status VARCHAR(20) NOT NULL,
 owner VARCHAR(64), lease_until FLOAT, cancel BOOLEAN NOT NULL,
 budget BIGINT NOT NULL, reserved BIGINT NOT NULL, result VARCHAR(64),
 error VARCHAR(300), actor VARCHAR(256)
);
CREATE TABLE api_keys (
 id VARCHAR(32) NOT NULL PRIMARY KEY, hash VARCHAR(64) UNIQUE,
 role VARCHAR(20) NOT NULL, name VARCHAR(120) NOT NULL, expires FLOAT NOT NULL,
 revoked BOOLEAN
);
CREATE TABLE audit (
 id VARCHAR(32) NOT NULL PRIMARY KEY, created FLOAT NOT NULL,
 actor VARCHAR(256) NOT NULL, action VARCHAR(80) NOT NULL, target VARCHAR(64) NOT NULL
);
INSERT INTO records (id, kind, created, data) VALUES ('11111111111111111111111111111111', 'run', 1700000000.125, '{"branchable":true,"evaluation_ref":"3dc8b45803b6813c89c7fc385c63c1b3d5fc8429d04e72a4c90f891c8fa3ace9","final_workspace":"9a3f2d7e399068639af760b28002e44f482361e83b7ccaf2b9e15f410797fd90","fork_step":null,"head":"4ab082d2fb477caf41f19b982590f4a75bb6e9af3f13d32c3daf2f25660da80f","image":"synthetic.invalid/fixture@sha256:0000000000000000000000000000000000000000000000000000000000000000","intervention":null,"job_id":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","name":"Synthetic legacy repair","parent_id":null,"policy":{"adapter":"synthetic-fixture-v1","seed_supported":true},"seed":7,"status":"complete","steps":2,"success":false,"task_digest":"5931e9f5a9cc4e02fd9d892383e2dac625146052d7a32a8ec5ee49b13eeb7798","task_ref":"5931e9f5a9cc4e02fd9d892383e2dac625146052d7a32a8ec5ee49b13eeb7798"}');
INSERT INTO records (id, kind, created, data) VALUES ('22222222222222222222222222222222', 'run', 1700000000.125, '{"branchable":true,"evaluation_ref":"03a1ae6f45ae9b977d5e384ee63ce724f2722ecd5420f422657fbfe0d65e9317","final_workspace":"d47f886a8f044255bc1142690764ebfedf37abc166f17f93fe5a0a19c932a4a2","fork_step":2,"head":"621f83ebd9743c0ceb5a5e5d7241ac5105ff2fbed5b70112a03e8cd7548154ec","image":"synthetic.invalid/fixture@sha256:0000000000000000000000000000000000000000000000000000000000000000","intervention":{"action":{"command":"","content":"def value():\n    return 2\n","path":"source.py","tool":"write_file"},"kind":"action","label":"Synthetic repair","result":null,"step":2},"job_id":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","name":"Synthetic legacy repair","parent_id":"11111111111111111111111111111111","policy":{"adapter":"synthetic-fixture-v1","seed_supported":true},"seed":7,"status":"complete","steps":3,"success":true,"task_digest":"5931e9f5a9cc4e02fd9d892383e2dac625146052d7a32a8ec5ee49b13eeb7798","task_ref":"5931e9f5a9cc4e02fd9d892383e2dac625146052d7a32a8ec5ee49b13eeb7798"}');
INSERT INTO events (run_id, step, artifact, hash) VALUES ('11111111111111111111111111111111', 1, 'edede0265d459e80b2535694a12e6772f803efe492285b27adfad56d10a58f3b', '2265b0946f34d290184411d70a9cd77112c6239d0ad29a73feab61d38707d17e');
INSERT INTO events (run_id, step, artifact, hash) VALUES ('11111111111111111111111111111111', 2, '4adc27ab55fe7f55497ac438d4fa18a467e86ee8e95984204293c480b8b3701d', '4ab082d2fb477caf41f19b982590f4a75bb6e9af3f13d32c3daf2f25660da80f');
INSERT INTO events (run_id, step, artifact, hash) VALUES ('22222222222222222222222222222222', 2, 'aaba626c4ba6924263b2c609e08fd412a46d710daddfc89d2a279b3ddf9ee4cf', '4189495d2b6a96f613b24c736ab03d141291ac3c5ade7ac7b6b975652926da90');
INSERT INTO events (run_id, step, artifact, hash) VALUES ('22222222222222222222222222222222', 3, '86b7d5f77f55c094b0b070db4159ff27fcb26b317c73bf88d233f387fa953f5d', '621f83ebd9743c0ceb5a5e5d7241ac5105ff2fbed5b70112a03e8cd7548154ec');
INSERT INTO jobs (id, kind, created, payload, status, owner, lease_until, cancel, budget, reserved, result, error, actor) VALUES ('aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', 'run', 1699999999.5, '5931e9f5a9cc4e02fd9d892383e2dac625146052d7a32a8ec5ee49b13eeb7798', 'succeeded', 'synthetic-worker', 1700000060.0, 0, 10000000, 125000, 'a267ae7dbc7148acb58d0c3bf6cae6d36c8a1c867905daec7f32f7c21c2da364', NULL, 'synthetic:operator');
INSERT INTO jobs (id, kind, created, payload, status, owner, lease_until, cancel, budget, reserved, result, error, actor) VALUES ('bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb', 'branch', 1700000000.5, '96ba396a87c3a90af0a4522e079f9288534631a1331b6730ab8234d7c5be6788', 'succeeded', 'synthetic-worker', 1700000060.0, 0, 10000000, 85000, '57eb60562fe029943b1477697481df7474707ade097b26422e9d13e01aa04cb2', NULL, 'synthetic:operator');
INSERT INTO jobs (id, kind, created, payload, status, owner, lease_until, cancel, budget, reserved, result, error, actor) VALUES ('cccccccccccccccccccccccccccccccc', 'run', 1700000001.5, '5931e9f5a9cc4e02fd9d892383e2dac625146052d7a32a8ec5ee49b13eeb7798', 'failed', 'synthetic-worker', 1700000060.0, 0, 5000000, 35000, NULL, 'Synthetic pre-run failure.', 'synthetic:operator');
INSERT INTO api_keys (id, hash, role, name, expires, revoked) VALUES ('33333333333333333333333333333333', '658247c353d2c9686adaa2c9852a818ef0f6cc6b75addb443731a5afb76d2548', 'viewer', 'Synthetic expired fixture key', 1699999900.0, 0);
INSERT INTO api_keys (id, hash, role, name, expires, revoked) VALUES ('44444444444444444444444444444444', '1ec11395cf01e78c7301e6887468b951f7f1e20f32fc9358a165e1ebca18ab8b', 'operator', 'Synthetic expired fixture key', 1699999900.0, 1);
INSERT INTO audit (id, created, actor, action, target) VALUES ('55555555555555555555555555555555', 1699999999.5, 'synthetic:operator', 'job.create', 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa');
INSERT INTO audit (id, created, actor, action, target) VALUES ('66666666666666666666666666666666', 1700000000.5, 'synthetic:operator', 'job.create', 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb');
INSERT INTO audit (id, created, actor, action, target) VALUES ('77777777777777777777777777777777', 1700000001.5, 'synthetic:operator', 'job.create', 'cccccccccccccccccccccccccccccccc');
