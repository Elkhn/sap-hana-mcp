import os
import csv
import io
import logging
from hdbcli import dbapi
from dotenv import load_dotenv
from fastmcp import FastMCP

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sap-hana-mcp")

# Configuration from environment variables
HANA_HOST = os.getenv("HANA_HOST", "")
HANA_PORT = int(os.getenv("HANA_PORT", "443"))
HANA_USER = os.getenv("HANA_USER", "")
HANA_PASSWORD = os.getenv("HANA_PASSWORD", "")
HANA_SCHEMA = os.getenv("HANA_SCHEMA", "")

SERVER_PORT = int(os.getenv("SERVER_PORT", "8000"))

FORMAT_DESC = "The output will be returned in CSV format, with the first line containing column headers."

mcp = FastMCP("SAP HANA MCP Server")


def _get_connection():
    """Create a new SAP HANA database connection."""
    return dbapi.connect(
        address=HANA_HOST,
        port=HANA_PORT,
        user=HANA_USER,
        password=HANA_PASSWORD
    )


def _resultset_to_csv(cursor, columns=None):
    """Convert a cursor result set to CSV string.

    Args:
        cursor: Database cursor with executed query results.
        columns: Optional list of (db_col_index, header_name) tuples.
                 If None, uses cursor description for headers.
    """
    output = io.StringIO()
    writer = csv.writer(output)

    if columns:
        writer.writerow([col[1] for col in columns])
    else:
        writer.writerow([desc[0] for desc in cursor.description])

    for row in cursor.fetchall():
        if columns:
            writer.writerow([row[col[0]] for col in columns])
        else:
            writer.writerow(row)

    return output.getvalue()


@mcp.tool()
async def sap_hana_get_tables(catalog: str = "", schema: str = "") -> str:
    """Retrieves a list of tables available in the SAP HANA data source.

    Use the `sap_hana_get_columns` tool to list available columns on a table.
    Both `catalog` and `schema` are optional parameters.
    The output will be returned in CSV format, with the first line containing column headers.

    Args:
        catalog: The catalog name (optional)
        schema: The schema name (optional, defaults to configured HANA_SCHEMA)
    """
    logger.info("sap_hana_get_tables(catalog=%s, schema=%s)", catalog, schema)
    effective_schema = schema or HANA_SCHEMA

    try:
        conn = _get_connection()
        cursor = conn.cursor()

        query = """
            SELECT SCHEMA_NAME, TABLE_NAME, COMMENTS
            FROM SYS.TABLES
            WHERE IS_USER_DEFINED_TYPE = 'FALSE'
        """
        params = []
        if effective_schema:
            query += " AND SCHEMA_NAME = ?"
            params.append(effective_schema)

        query += " ORDER BY SCHEMA_NAME, TABLE_NAME"
        cursor.execute(query, params)

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Schema", "Table", "Description"])
        for row in cursor.fetchall():
            writer.writerow([row[0], row[1], row[2] or ""])

        result = output.getvalue()

        if effective_schema:
            result += f"\nDefault Schema: {effective_schema}"

        cursor.close()
        conn.close()
        return result

    except Exception as ex:
        raise RuntimeError(f"ERROR: {ex}")


@mcp.tool()
async def sap_hana_get_columns(table: str, catalog: str = "", schema: str = "") -> str:
    """Retrieves a list of columns for a table in SAP HANA.

    Use the `sap_hana_get_tables` tool to get a list of available tables.
    The output will be returned in CSV format, with the first line containing column headers.

    Args:
        table: The table name (required)
        catalog: The catalog name (optional)
        schema: The schema name (optional, defaults to configured HANA_SCHEMA)
    """
    logger.info("sap_hana_get_columns(catalog=%s, schema=%s, table=%s)", catalog, schema, table)
    effective_schema = schema or HANA_SCHEMA

    try:
        conn = _get_connection()
        cursor = conn.cursor()

        query = """
            SELECT SCHEMA_NAME, TABLE_NAME, COLUMN_NAME, DATA_TYPE_NAME, COMMENTS
            FROM SYS.TABLE_COLUMNS
            WHERE TABLE_NAME = ?
        """
        params = [table]
        if effective_schema:
            query += " AND SCHEMA_NAME = ?"
            params.append(effective_schema)

        query += " ORDER BY POSITION"
        cursor.execute(query, params)

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Schema", "Table", "Column", "DataType", "Remarks"])
        for row in cursor.fetchall():
            writer.writerow([row[0], row[1], row[2], row[3], row[4] or ""])

        result = output.getvalue()
        cursor.close()
        conn.close()
        return result

    except Exception as ex:
        raise RuntimeError(f"ERROR: {ex}")


@mcp.tool()
async def sap_hana_run_query(sql: str) -> str:
    """Execute a SQL SELECT statement against SAP HANA.

    Use the `sap_hana_get_tables` tool to get a list of available tables,
    and the `sap_hana_get_columns` tool to list table columns.
    Identifiers should be quoted using double quotes.
    The SQL dialect is mostly based around SQL-92.
    Valid clauses: FROM, INNER JOIN, LEFT JOIN, GROUP BY, ORDER BY, LIMIT/OFFSET.
    The output will be returned in CSV format, with the first line containing column headers.

    Args:
        sql: The SELECT statement to execute
    """
    logger.info("sap_hana_run_query(%s)", sql)

    try:
        conn = _get_connection()
        cursor = conn.cursor()
        cursor.execute(sql)

        result = _resultset_to_csv(cursor)
        cursor.close()
        conn.close()
        return result

    except Exception as ex:
        raise RuntimeError(f"ERROR: {ex}")


@mcp.resource("sap_hana://tables/{schema}/{table}")
async def get_table_metadata(schema: str, table: str) -> str:
    """Get column metadata for a specific table.

    Args:
        schema: The schema name
        table: The table name
    """
    try:
        conn = _get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT SCHEMA_NAME, TABLE_NAME, COLUMN_NAME, DATA_TYPE_NAME, COMMENTS
            FROM SYS.TABLE_COLUMNS
            WHERE SCHEMA_NAME = ? AND TABLE_NAME = ?
            ORDER BY POSITION
            """,
            [schema, table],
        )

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Schema", "Table", "Column", "DataType", "Remarks"])
        for row in cursor.fetchall():
            writer.writerow([row[0], row[1], row[2], row[3], row[4] or ""])

        result = output.getvalue()
        cursor.close()
        conn.close()
        return result

    except Exception as ex:
        raise RuntimeError(f"ERROR: {ex}")


if __name__ == "__main__":
    print(f"Starting SAP HANA MCP server on port {SERVER_PORT}...")
    print(f"Connect to this server using http://localhost:{SERVER_PORT}/sse")
    mcp.run(transport="sse", host="0.0.0.0", port=SERVER_PORT)
