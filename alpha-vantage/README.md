# Alpha Vantage MCP Integration

A Gradio-based chat interface for querying stock quotes using the Model Context Protocol (MCP) to integrate with Alpha Vantage financial data services.

## 🚀 Overview

This module provides a conversational interface for stock market queries, leveraging the MCP protocol to communicate with Alpha Vantage backend services. It combines natural language processing with async/await patterns for responsive, real-time stock information retrieval.

## 🎯 Key Features

### Natural Language Interface
- Chat-based interaction for intuitive stock queries
- Automatic ticker symbol extraction from user messages
- Support for various query formats: "What's TSLA price?" or "Check NVDA"

### MCP Protocol Integration
- Standardized Model Context Protocol for AI tool integration
- HTTP transport layer with async support
- Session management and initialization handling

### Async Architecture
- Non-blocking I/O operations for optimal performance
- Graceful error handling with detailed debugging
- Support for concurrent requests

### Robust Error Handling
- Configuration validation and error reporting
- Protocol-level error detection and user-friendly messages
- Debug mode for troubleshooting

## 📁 Project Structure

```
alpha-vantage/
├── hello-alpha-python-gradio.py  # Main Gradio application (184 lines)
├── test_hello_alpha.py           # Comprehensive test suite (237 lines)
├── requirements.txt              # Python dependencies
├── .env                          # Environment configuration (optional)
└── .vscode/
    └── mcp.json                  # MCP server configuration
```

## 🛠️ Installation

### Prerequisites
- Python 3.11 or higher
- MCP-compatible Alpha Vantage server running on accessible endpoint

### Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

Required packages:
- `gradio` - Chat interface framework
- `mcp` - Model Context Protocol client library
- `python-dotenv` - Environment variable management
- `pytest>=7.0.0` - Testing framework
- `pytest-asyncio>=0.21.0` - Async testing support

2. Configure MCP server:
Create `.vscode/mcp.json` with your Alpha Vantage server configuration:

```json
{
  "servers": {
    "alphavantage": {
      "type": "http",
      "url": "http://localhost:3000"
    }
  }
}
```

3. Optional debug mode:
Create `.env` file for enhanced logging:
```
ALPHA_VANTAGE_DEBUG=true
```

## 🚦 Running the Application

### Start the Gradio Interface

```bash
python hello-alpha-python-gradio.py
```

This will:
- Load MCP configuration from `.vscode/mcp.json`
- Start the Gradio web server (default: http://127.0.0.1:7860)
- Display the "Alpha Vantage Assistant" chat interface

### Example Queries

Try these natural language queries in the chat interface:

- "What's happening with TSLA?"
- "Check current quote value for NVDA"
- "AAPL stock price today"
- "Show me information about Microsoft"

## 🔧 Configuration

### MCP Server Configuration

The application requires MCP configuration in `.vscode/mcp.json`:

```json
{
  "servers": {
    "alphavantage": {
      "type": "http",
      "url": "http://your-server-endpoint:port"
    }
  }
}
```

**Configuration Validation:**
- Server type must be `"http"`
- URL must be a valid HTTP endpoint
- Server name `"alphavantage"` is required

### Environment Variables

Optional environment variables for enhanced functionality:

| Variable | Default | Description |
|----------|---------|-------------|
| `ALPHA_VANTAGE_DEBUG` | `false` | Enable verbose debug logging (true/false/1/yes) |
| `OPENAI_API_KEY` | _(unset)_ | OpenAI API key for AI analysis. Omit to disable AI features (chat still works with raw quotes). |
| `OPENAI_MODEL` | `gpt-4o-mini` | OpenAI model id used for analysis (the smallest/cheapest OpenAI model; no "nano" model exists). |

## 🧪 Testing

### Run All Tests

```bash
pytest test_hello_alpha.py -v
```

### Test Categories

#### Configuration Tests (`TestLoadMcpConfig`)
- ✅ Valid configuration loading
- ✅ Configuration file not found handling
- ✅ Server name validation
- ✅ Transport type validation

#### Ticker Extraction Tests (`TestExtractTicker`)
- ✅ Valid ticker symbol extraction
- ✅ Multiple symbols handling
- ✅ No valid symbol handling
- ✅ Case-insensitive extraction

#### MCP Integration Tests (`TestCallAlphaVantageMcp`)
- ✅ Successful MCP calls
- ✅ Configuration error handling
- ✅ Empty response handling
- ✅ Protocol error scenarios

#### Chat Interface Tests (`TestChatWithMcp`)
- ✅ Valid ticker queries
- ✅ Invalid input handling
- ✅ Message formatting

### Example Test Commands

```bash
# Run specific test class
pytest test_hello_alpha.py::TestExtractTicker -v

# Run with coverage
pytest test_hello_alpha.py --cov=. --cov-report=html

# Run with debug output
pytest test_hello_alpha.py -v -s
```

## 🔌 API Reference

### Core Functions

#### `load_mcp_config_from_vscode(server_name: str) -> str`

Parses `.vscode/mcp.json` to fetch MCP server configuration.

**Parameters:**
- `server_name` - Server identifier (default: "alphavantage")

**Returns:**
- `str` - MCP endpoint URL

**Raises:**
- `FileNotFoundError` - Configuration file missing
- `KeyError` - Server name not found
- `ValueError` - Invalid transport type or missing URL

**Features:**
- URL caching for performance optimization
- Comprehensive validation
- Debug logging support

---

#### `extract_ticker(message: str) -> str | None`

Extracts stock ticker symbol from user message using regex patterns.

**Parameters:**
- `message` - User's natural language query

**Returns:**
- `str | None` - Extracted ticker symbol or None if not found

**Algorithm:**
1. Remove special characters and convert to uppercase
2. Find 1-5 letter uppercase words
3. Filter out common English words
4. Return last valid ticker (often most relevant in queries)

---

#### `async call_alpha_vantage_mcp(ticker: str) -> str`

Executes MCP transaction for stock quote retrieval.

**Parameters:**
- `ticker` - Stock ticker symbol

**Returns:**
- `str` - Formatted stock quote data or error message

**Error Handling:**
- Configuration errors with detailed messages
- Protocol errors with exception details
- Empty response handling
- Sub-exception reporting for ExceptionGroup

---

#### `async chat_with_mcp(message: str, history: list) -> str`

Main Gradio chat interface function for user interaction.

**Parameters:**
- `message` - User's query message
- `history` - Chat history array

**Returns:**
- `str` - Formatted analysis response with ticker and MCP data

**Workflow:**
1. Extract ticker from user message
2. Validate ticker extraction
3. Call Alpha Vantage MCP
4. Format response with markdown structure

## 🏗️ Technical Architecture

### Async Design Pattern

The application follows async/await patterns for optimal performance:

```python
async def call_alpha_vantage_mcp(ticker: str) -> str:
    # Non-blocking MCP client initialization
    async with streamablehttp_client(url) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            response = await session.call_tool(...)
```

### MCP Protocol Flow

1. **Configuration Loading**: Parse `.vscode/mcp.json` with validation
2. **Connection Establishment**: Create streamable HTTP client
3. **Session Initialization**: Initialize MCP session
4. **Tool Execution**: Call `get_stock_quote` tool with ticker parameter
5. **Response Processing**: Extract and format returned data

### Ticker Extraction Algorithm

The intelligent ticker extraction uses:
- Regex pattern matching for 1-5 letter uppercase words
- Common word filtering (excludes "WHAT", "PRICE", "CHECK", etc.)
- Reverse scanning for relevance (last ticker often most important)
- Case-insensitive processing

### Error Handling Strategy

Comprehensive error handling at multiple levels:

**Configuration Level:**
- File existence validation
- JSON parsing error handling
- Schema validation (type, URL presence)

**Protocol Level:**
- Connection error catching
- Exception group sub-exception extraction
- Empty response detection

**User Interface Level:**
- Friendly error messages with markdown formatting
- Debug information when enabled
- Graceful fallback for invalid inputs

## 🔍 Debugging

### Enable Debug Mode

Set environment variable or create `.env` file:

```bash
export ALPHA_VANTAGE_DEBUG=true
```

Or create `.env` file:
```
ALPHA_VANTAGE_DEBUG=true
```

### Debug Output

Debug mode provides detailed logging:
- Configuration loading steps
- URL resolution and caching
- Ticker extraction process
- MCP connection details
- Response metadata
- Error stack traces

### Common Issues

**Configuration File Not Found:**
```
FileNotFoundError: Configuration profile missing at location: '.vscode/mcp.json'
```
Ensure `.vscode/mcp.json` exists in the application directory.

**Server Type Invalid:**
```
ValueError: Invalid transport schema 'websocket'. Expected 'http'.
```
Verify server type is set to `"http"` in configuration.

**Connection Timeout:**
```
Protocol Transport Fault: Unable to fulfill network transaction
```
Check MCP server endpoint accessibility and network connectivity.

## 🎓 Usage Examples

### Basic Query

```python
result = await chat_with_mcp("What's the price of AAPL?", [])
# Returns: "### Analysis for **AAPL** via Workspace Protocol Hub:\n\n{stock_data}"
```

### MCP Configuration Loading

```python
url = load_mcp_config_from_vscode("alphavantage")
# Returns: "http://localhost:3000"
```

### Ticker Extraction

```python
ticker = extract_ticker("Check current value for NVDA")
# Returns: "NVDA"

ticker = extract_ticker("What's the weather?")
# Returns: None
```

### Direct MCP Call

```python
quote = await call_alpha_vantage_mcp("TSLA")
# Returns: Formatted stock quote data
```

## 🔒 Security Considerations

### Configuration Security
- Store MCP endpoints in configuration files, not hardcoded
- Use environment variables for sensitive data
- Avoid committing `.env` files to version control

### Input Validation
- Ticker extraction filters common words to prevent injection
- MCP tool calls validate ticker format
- Error messages don't expose internal details

### Network Security
- Supports HTTP/HTTPS endpoints
- No credentials stored in application code
- Configuration-based endpoint management

## 📚 Additional Resources

- [Gradio Documentation](https://www.gradio.app/docs)
- [Model Context Protocol](https://modelcontextprotocol.io/)
- [Alpha Vantage API](https://www.alphavantage.co/documentation/)
- [Python Async/Await Patterns](https://docs.python.org/3/library/asyncio.html)

## 🤝 Contributing

Contributions are welcome! Please ensure:
- All tests pass with `pytest -v`
- Async functions maintain proper error handling
- Debug logging is comprehensive
- Documentation is updated for new features

## 📄 License

See parent LICENSE file for details.