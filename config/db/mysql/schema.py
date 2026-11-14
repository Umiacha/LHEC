from django.db.backends.mysql.schema import DatabaseSchemaEditor as MySQLSchemaEditor


class DatabaseSchemaEditor(MySQLSchemaEditor):
    # Used by CreateModel, automatic M2M tables and MigrationRecorder alike.
    # Keep Django's column, constraint, index and deferred-FK generation intact.
    sql_create_table = (
        'CREATE TABLE %(table)s (%(definition)s) '
        'ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 '
        'COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC'
    )
