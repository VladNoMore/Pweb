#!/usr/bin/env python3
import socket
import argparse
import re
import sys
import os
import json
import time
import ssl
from urllib.parse import urlparse, quote_plus
from html.parser import HTMLParser

# Constants
DEFAULT_PORT = 80
DEFAULT_HTTPS_PORT = 443
USER_AGENT = "go2web/1.0"
# Store cache in the current directory instead of home directory
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".go2web_cache")
MAX_CACHE_AGE = 3600  # Cache expiry in seconds (1 hour)

# HTML Parser for cleaning HTML tags
class HTMLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.data = []
        self.in_title = False
        self.in_body = False
        self.links = []
        self.current_link = None
        self.current_link_text = ""
        self.search_results = []
        self.is_search_result = False
        self.result_count = 0
        self.max_results = 10

    def handle_starttag(self, tag, attrs):
        if tag == 'title':
            self.in_title = True
        elif tag == 'body':
            self.in_body = True
        elif tag == 'a':
            self.current_link = dict(attrs).get('href', '')
            self.current_link_text = ""
        
        # Special handling for search results (Google-specific format)
        if tag == 'div' and any(attr for attr in attrs if attr[0] == 'class' and 'g' in attr[1].split()):
            self.is_search_result = True

    def handle_endtag(self, tag):
        if tag == 'title':
            self.in_title = False
        elif tag == 'body':
            self.in_body = False
        elif tag == 'a' and self.current_link:
            self.links.append((self.current_link, self.current_link_text.strip()))
            self.current_link = None
            
            if self.is_search_result and self.result_count < self.max_results:
                self.search_results.append((self.current_link, self.current_link_text.strip()))
                self.result_count += 1
                
        elif tag == 'div' and self.is_search_result:
            self.is_search_result = False

    def handle_data(self, data):
        clean_data = data.strip()
        if clean_data:
            self.data.append(clean_data)
            if self.current_link is not None:
                self.current_link_text += clean_data + " "

    def get_data(self):
        return '\n'.join(self.data)
    
    def get_links(self):
        return self.links
        
    def get_search_results(self):
        return self.search_results


# Cache management functions
def ensure_cache_dir():
    """Ensure the cache directory exists"""
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR)

def get_cache_key(url):
    """Generate a cache key for a URL"""
    return os.path.join(CACHE_DIR, re.sub(r'[^\w]', '_', url))

def get_from_cache(url):
    """Try to get a response from cache"""
    cache_key = get_cache_key(url)
    if os.path.exists(cache_key):
        try:
            with open(cache_key, 'r') as f:
                cache_data = json.load(f)
                # Check if cache is still valid
                if time.time() - cache_data['timestamp'] <= MAX_CACHE_AGE:
                    return cache_data['content'], cache_data['content_type']
        except (json.JSONDecodeError, KeyError, IOError):
            # If any error occurs, ignore the cache
            pass
    return None, None

def save_to_cache(url, content, content_type):
    """Save a response to cache"""
    ensure_cache_dir()
    cache_key = get_cache_key(url)
    try:
        with open(cache_key, 'w') as f:
            json.dump({
                'timestamp': time.time(),
                'content': content,
                'content_type': content_type
            }, f)
    except IOError:
        # If we can't save to cache, just continue without caching
        pass


# Socket-based HTTP request function
def http_request(url, headers=None, follow_redirects=True, max_redirects=5):
    """Make an HTTP request using sockets"""
    if headers is None:
        headers = {}
    
    # Check cache first
    cached_content, cached_content_type = get_from_cache(url)
    if cached_content:
        return cached_content, cached_content_type
    
    parsed_url = urlparse(url)
    
    # Set default scheme if not provided
    if not parsed_url.scheme:
        parsed_url = urlparse('http://' + url)
    
    host = parsed_url.netloc
    path = parsed_url.path if parsed_url.path else '/'
    if parsed_url.query:
        path += '?' + parsed_url.query
    
    # Handle ports
    if ':' in host:
        host, port = host.split(':', 1)
        port = int(port)
    else:
        port = DEFAULT_HTTPS_PORT if parsed_url.scheme == 'https' else DEFAULT_PORT
    
    # Prepare request headers
    default_headers = {
        'Host': parsed_url.netloc,
        'User-Agent': USER_AGENT,
        'Accept': 'text/html,application/json,*/*;q=0.9',
        'Connection': 'close'
    }
    
    # Merge with custom headers
    all_headers = {**default_headers, **headers}
    header_str = '\r\n'.join([f"{k}: {v}" for k, v in all_headers.items()]) + '\r\n\r\n'
    request = f"GET {path} HTTP/1.1\r\n{header_str}"
    
    # Create socket connection
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(10)  # Set timeout to avoid hanging
        
        # Handle HTTPS connections
        if parsed_url.scheme == 'https':
            context = ssl.create_default_context()
            s = context.wrap_socket(s, server_hostname=host)
        
        s.connect((host, port))
        s.sendall(request.encode())
        
        # Read the response
        response = b''
        while True:
            data = s.recv(4096)
            if not data:
                break
            response += data
        
        s.close()
        
        # Parse response headers and body
        if b'\r\n\r\n' in response:
            headers_raw, body = response.split(b'\r\n\r\n', 1)
            headers_raw = headers_raw.decode('utf-8', errors='ignore')
            
            # Extract status code
            status_match = re.search(r'HTTP/\d\.\d (\d+)', headers_raw)
            if status_match:
                status_code = int(status_match.group(1))
            else:
                status_code = 0
            
            # Handle redirects
            if status_code in (301, 302, 303, 307, 308) and follow_redirects and max_redirects > 0:
                location_match = re.search(r'Location: (.*)\r\n', headers_raw)
                if location_match:
                    redirect_url = location_match.group(1).strip()
                    
                    # Handle relative URLs
                    if redirect_url.startswith('/'):
                        scheme = parsed_url.scheme
                        redirect_url = f"{scheme}://{host}{redirect_url}"
                    
                    print(f"Redirecting to: {redirect_url}")
                    return http_request(redirect_url, headers, follow_redirects, max_redirects - 1)
            
            # Extract content type
            content_type_match = re.search(r'Content-Type: (.*)\r\n', headers_raw)
            content_type = content_type_match.group(1).strip() if content_type_match else 'text/plain'
            
            # Handle encoding issues in the body
            body_text = body.decode('utf-8', errors='ignore')
            
            # Save to cache
            save_to_cache(url, body_text, content_type)
            
            return body_text, content_type
        
        return response.decode('utf-8', errors='ignore'), 'text/plain'
    
    except Exception as e:
        print(f"Error making request: {e}")
        return f"Error: {e}", "text/plain"


def make_search_request(search_term):
    """Search using a search engine and return top results"""
    # Using DuckDuckGo's simple interface
    query = quote_plus(search_term)
    search_url = f"https://duckduckgo.com/html/?q={query}"
    
    content, content_type = http_request(search_url, follow_redirects=True)
    
    # Parse the HTML to extract search results
    parser = HTMLStripper()
    parser.feed(content)
    
    # Extract search results
    results = []
    links = parser.get_links()
    
    # Filter for actual search result links (this is DDG specific)
    for link, text in links:
        if link and not link.startswith(('javascript:', '#')) and len(text.strip()) > 0:
            if link.startswith('/'):
                link = f"https://duckduckgo.com{link}"
            results.append((link, text))
            if len(results) >= 10:
                break
    
    # Format and print results
    print(f"Search results for '{search_term}':\n")
    if results:
        for i, (link, text) in enumerate(results, 1):
            print(f"{i}. {text}")
            print(f"   URL: {link}")
            print()
    else:
        print("No results found or could not parse search results.")
        
    # Add option to visit one of the results
    if results:
        print("\nWould you like to visit one of these links? Enter the number (1-10) or 'n' to exit:")
        try:
            choice = input().strip()
            if choice.isdigit() and 1 <= int(choice) <= len(results):
                idx = int(choice) - 1
                print(f"\nVisiting: {results[idx][0]}")
                make_url_request(results[idx][0])
        except (ValueError, IndexError, KeyboardInterrupt):
            print("Exiting search results.")
    
    return results


def make_url_request(url):
    """Make a request to the specified URL and print the response"""
    content, content_type = http_request(url, follow_redirects=True)
    
    if 'json' in content_type.lower():
        # Handle JSON content
        try:
            data = json.loads(content)
            formatted_json = json.dumps(data, indent=2)
            print(formatted_json)
        except json.JSONDecodeError:
            print("Error parsing JSON response:")
            print(content)
    else:
        # Handle HTML content
        parser = HTMLStripper()
        parser.feed(content)
        clean_text = parser.get_data()
        print(clean_text)


def main():
    parser = argparse.ArgumentParser(description='Simple HTTP client')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('-u', '--url', help='make an HTTP request to the specified URL')
    group.add_argument('-s', '--search', help='search the term using a search engine', nargs='+')
    
    args = parser.parse_args()
    
    if args.url:
        make_url_request(args.url)
    elif args.search:
        search_term = ' '.join(args.search)
        make_search_request(search_term)


if __name__ == "__main__":
    main()