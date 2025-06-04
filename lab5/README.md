# go2web - Custom HTTP Client

A custom HTTP client that implements basic HTTP functionality without using built-in HTTP libraries. This client can make direct HTTP requests and perform web searches.

## Features

- Makes HTTP requests to specified URLs with `-u` option
- Performs web searches with `-s` option (using DuckDuckGo)
- Shows clean, human-readable output (no HTML tags)
- Implements HTTP redirects
- Includes a caching mechanism for faster repeated requests
- Supports content negotiation (HTML and JSON)

## Installation

1. Clone this repository
2. Make the scripts executable:
   ```bash
   chmod +x go2web.py go2web
   ```
3. Place the `go2web` script in your PATH:
   ```bash
   sudo cp go2web /usr/local/bin/
   ```
   (Or update the path in the `go2web` script to point to your `go2web.py` file)

## Usage

```
go2web -u <URL>         # make an HTTP request to the specified URL and print the response
go2web -s <search-term> # make an HTTP request to search the term using DuckDuckGo and print top 10 results
go2web -h               # show this help
```

## Example

![Demo of go2web](demo.gif)

## How It Works

This implementation avoids using HTTP-specific libraries by:

1. Establishing TCP socket connections directly
2. Crafting HTTP requests manually
3. Parsing HTTP responses to handle redirects
4. Implementing a caching mechanism
5. Supporting content negotiation between JSON and HTML

## Extra Features Implemented

- ✅ HTTP request redirects
- ✅ HTTP cache mechanism
- ✅ Content negotiation (JSON/HTML)
- ✅ Search engine results that can be accessed from CLI

## Limitations

- HTTPS support is not implemented (would require SSL/TLS libraries)
- Limited error handling
- Basic HTML parsing