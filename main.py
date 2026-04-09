import os
import csv
import io
import logging
import base64
import httpx
from bs4 import BeautifulSoup
from hdbcli import dbapi
from dotenv import load_dotenv
from fastmcp import FastMCP
from fastmcp.server.dependencies import CurrentHeaders

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


def _parse_basic_auth(headers: dict) -> tuple[str, str]:
    """Extract username and password from Authorization: Basic header."""
    auth = headers.get("authorization", "")
    if not auth.startswith("Basic "):
        return "", ""
    try:
        decoded = base64.b64decode(auth[6:]).decode("utf-8")
        user, password = decoded.split(":", 1)
        return user, password
    except Exception:
        return "", ""


def _get_connection(headers: dict = None):
    """Create a new SAP HANA database connection.

    Uses credentials from the Authorization header if provided,
    otherwise falls back to environment variables.
    """
    user, password = "", ""
    if headers:
        user, password = _parse_basic_auth(headers)
    if not user or not password:
        raise RuntimeError("Authorization required. Provide an Authorization: Basic header with SAP HANA credentials.")
    return dbapi.connect(
        address=HANA_HOST,
        port=HANA_PORT,
        user=user,
        password=password
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
async def sap_hana_get_tables(catalog: str = "", schema: str = "", headers: dict = CurrentHeaders()) -> str:
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
        conn = _get_connection(headers)
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
async def sap_hana_get_columns(table: str, catalog: str = "", schema: str = "", headers: dict = CurrentHeaders()) -> str:
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
        conn = _get_connection(headers)
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
async def sap_hana_run_query(sql: str, headers: dict = CurrentHeaders()) -> str:
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
        conn = _get_connection(headers)
        cursor = conn.cursor()
        cursor.execute(sql)

        result = _resultset_to_csv(cursor)
        cursor.close()
        conn.close()
        return result

    except Exception as ex:
        raise RuntimeError(f"ERROR: {ex}")


@mcp.resource("sap_hana://tables/{schema}/{table}")
async def get_table_metadata(schema: str, table: str, headers: dict = CurrentHeaders()) -> str:
    """Get column metadata for a specific table.

    Args:
        schema: The schema name
        table: The table name
    """
    try:
        conn = _get_connection(headers)
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


async def _fetch_leanx_table(table_name: str):
    """Fetch and parse SAP table metadata from leanx.eu using httpx + BeautifulSoup."""
    url = f"https://leanx.eu/sap/table/{table_name.lower()}/"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, headers={"User-Agent": "sap-hana-mcp/0.1"})

    if resp.status_code == 404:
        return None, []

    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # Table description from the h2 subtitle
    h2 = soup.find("h2", class_="text-xl")
    description = h2.get_text(strip=True) if h2 else ""

    # Field rows from the main data table (skip thead)
    fields = []
    table_el = soup.find("table")
    if table_el:
        tbody = table_el.find("tbody")
        if tbody:
            for tr in tbody.find_all("tr"):
                cells = tr.find_all("td")
                if len(cells) < 6:
                    continue
                # Cell 0: field name (first div) + description (second div)
                divs = cells[0].find_all("div")
                field_name = divs[0].get_text(strip=True) if divs else ""
                field_desc = divs[1].get_text(strip=True) if len(divs) > 1 else ""
                data_element = cells[1].get_text(strip=True)
                datatype = cells[3].find("div").get_text(strip=True) if cells[3].find("div") else cells[3].get_text(strip=True)
                length = cells[4].get_text(strip=True)
                decimals = cells[5].get_text(strip=True)
                fields.append((field_name, field_desc, data_element, datatype, length, decimals))

    return description, fields


@mcp.tool()
async def sap_hana_lookup_table_info(table: str) -> str:
    """Look up SAP table and field descriptions from an external reference (leanx.eu).

    Use this when SAP HANA system catalog has no comments/descriptions for tables or columns.
    Returns the table description and a CSV of fields with their metadata.

    Args:
        table: The SAP table name (e.g. ANLA, BKPF, MARA)
    """
    logger.info("sap_hana_lookup_table_info(table=%s)", table)

    description, fields = await _fetch_leanx_table(table)

    if description is None:
        return f"Table '{table.upper()}' not found on leanx.eu."

    output = io.StringIO()
    writer = csv.writer(output)

    if description:
        output.write(f"Table: {table.upper()}\n")
        output.write(f"Description: {description}\n\n")

    writer.writerow(["Field", "Description", "DataElement", "Datatype", "Length", "Decimals"])
    for field_name, field_desc, data_element, datatype, length, decimals in fields:
        writer.writerow([field_name, field_desc, data_element, datatype, length, decimals])

    return output.getvalue()


if __name__ == "__main__":
    print(f"Starting SAP HANA MCP server on port {SERVER_PORT}...")
    print(f"Connect to this server using http://localhost:{SERVER_PORT}/sse")
    mcp.run(transport="sse", host="0.0.0.0", port=SERVER_PORT)
