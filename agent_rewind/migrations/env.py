"""Alembic runs only inside the validated operator transaction."""

from alembic import context

connection = context.config.attributes.get("connection")
if connection is None or context.config.attributes.get("validated_operator") is not True:
    raise RuntimeError("Use the explicit rewind migrate operator commands.")
context.configure(connection=connection, transactional_ddl=True)
with context.begin_transaction():
    context.run_migrations()
