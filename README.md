# SAP HANA MCP Server (Python)

A Model Context Protocol (MCP) server for SAP HANA, built with [FastMCP](https://github.com/jlowin/fastmcp) and the official SAP HANA Python driver (`hdbcli`).

This server exposes SAP HANA database capabilities (listing tables, columns, running queries) as MCP tools that AI assistants can use.

## Prerequisites

- Python 3.10+
- Access to a SAP HANA instance (on-premise or SAP HANA Cloud)
- SAP HANA client libraries (installed automatically with `hdbcli`)

## Installation

```bash
# Clone and enter the directory
cd sap-hana-mcp-server-python

# Install dependencies
pip install -r requirements.txt
```

## Configuration

Copy the example environment file and fill in your SAP HANA credentials:

```bash
cp .env.example .env
```

Edit `.env` with your connection details:

| Variable | Description | Default |
|---|---|---|
| `HANA_HOST` | SAP HANA server hostname | *(required)* |
| `HANA_PORT` | SAP HANA server port | `443` |
| `HANA_USER` | Database username | *(required)* |
| `HANA_PASSWORD` | Database password | *(required)* |
| `HANA_SCHEMA` | Default schema to filter tables | *(optional)* |
| `SERVER_PORT` | MCP server HTTP port | `8000` |

## Running the Server

### Locally

```bash
python main.py
```

The server starts on `http://localhost:8000/sse` using SSE transport.

### With Docker

```bash
docker build -t sap-hana-mcp .
docker run -p 8000:8000 --env-file .env sap-hana-mcp
```

## MCP Tools

### `sap_hana_get_tables`

Lists tables available in the SAP HANA instance. Returns CSV with columns: `Schema`, `Table`, `Description`.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `catalog` | string | No | Catalog name filter |
| `schema` | string | No | Schema name filter (defaults to `HANA_SCHEMA`) |

### `sap_hana_get_columns`

Lists columns for a specific table. Returns CSV with columns: `Schema`, `Table`, `Column`, `DataType`, `Remarks`.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `table` | string | Yes | Table name |
| `catalog` | string | No | Catalog name filter |
| `schema` | string | No | Schema name filter (defaults to `HANA_SCHEMA`) |

### `sap_hana_run_query`

Executes a SQL SELECT statement. Returns results in CSV format. The SQL dialect is based on SQL-92. Identifiers should be quoted with double quotes.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `sql` | string | Yes | The SELECT statement to execute |

## MCP Resources

### `sap_hana://tables/{schema}/{table}`

Returns column metadata for a given schema and table in CSV format.

## Connecting to AI Clients

### Claude Desktop

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "sap-hana": {
      "url": "http://localhost:8000/sse"
    }
  }
}
```

### Cursor / Other MCP Clients

Use the SSE endpoint: `http://localhost:8000/sse`

## Project Structure

```
sap-hana-mcp-server-python/
  main.py            # MCP server with tools and resources
  requirements.txt   # Python dependencies
  .env.example       # Environment variable template
  Dockerfile         # Docker container build
  pyproject.toml     # Project metadata
  README.md          # This file
```

## License

MIT
