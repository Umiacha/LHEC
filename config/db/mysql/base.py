"""Django's MySQL backend with explicit table creation options."""

from django.db.backends.mysql.base import DatabaseWrapper as MySQLDatabaseWrapper

from .schema import DatabaseSchemaEditor


class DatabaseWrapper(MySQLDatabaseWrapper):
    SchemaEditorClass = DatabaseSchemaEditor
