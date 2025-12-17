import os
import json
import time
from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By

def setup_firefox_profile():
    """Setup Firefox profile with devtools enabled"""
    options = Options()
    
    # Enable headless mode
    options.add_argument('--headless')
    
    # Use existing profile from current directory
    profile_path = os.path.abspath(os.path.join(os.getcwd(), "firefox_profile"))
    
    # Enable network monitoring
    options.set_preference("devtools.netmonitor.enabled", True)
    options.set_preference("devtools.debugger.remote-enabled", True)
    options.set_preference("devtools.chrome.enabled", True)
    options.set_preference("devtools.debugger.prompt-connection", False)
    options.set_preference("devtools.debugger.force-local", False)
    
    # Set the profile path
    options.add_argument("-profile")
    options.add_argument(profile_path)
    
    return options

def extract_tokens():
    """Extract bearer and access tokens from zee5.com network requests"""
    options = setup_firefox_profile()
    driver = None
    
    try:
        driver = webdriver.Firefox(options=options)
        
        # First inject our interceptor before navigating
        inject_script = """
        window.zee5Monitor = {
            tokens: null,
            requests: [],
            lastPrintedIndex: 0,
            
            init: function() {
                // Clear existing entries
                performance.clearResourceTimings();
                this.requests = [];
                this.tokens = null;
                this.lastPrintedIndex = 0;
                
                // Setup fetch interceptor
                if (!window.originalFetch) {
                    window.originalFetch = window.fetch;
                    
                    window.fetch = async (...args) => {
                        const [url, options = {}] = args;
                        
                        try {
                            // Only track GET requests
                            if (options.method && options.method !== 'GET') {
                                return window.originalFetch.apply(window, args);
                            }
                            
                            // Make the request and get response
                            const response = await window.originalFetch.apply(window, args);
                            
                            // Only track successful requests
                            if (response.status === 200) {
                                // Store request details
                                const requestInfo = {
                                    url: url.toString(),
                                    method: options.method || 'GET',
                                    status: response.status,
                                    headers: {}
                                };
                                
                                // Get request headers
                                if (options.headers) {
                                    if (options.headers instanceof Headers) {
                                        for (let [key, value] of options.headers.entries()) {
                                            requestInfo.headers[key] = value;
                                        }
                                    } else {
                                        requestInfo.headers = {...options.headers};
                                    }
                                }
                                
                                this.requests.push(requestInfo);
                                console.log('Request captured:', requestInfo);
                                
                                // Check for any request with both tokens
                                if ((requestInfo.headers['Authorization'] || requestInfo.headers['authorization']) && 
                                    requestInfo.headers['x-access-token']) {
                                    this.tokens = {
                                        bearer_token: requestInfo.headers['Authorization'] || requestInfo.headers['authorization'],
                                        access_token: requestInfo.headers['x-access-token']
                                    };
                                    console.log('Tokens found:', this.tokens);
                                }
                            }
                            
                            return response;
                        } catch (e) {
                            console.error('Error in fetch interceptor:', e);
                            return window.originalFetch.apply(window, args);
                        }
                    };
                }
            }
        };

        // Add methods to prototype to ensure they persist
        window.zee5Monitor.getNewRequests = function() {
            const newRequests = this.requests.slice(this.lastPrintedIndex);
            this.lastPrintedIndex = this.requests.length;
            return newRequests;
        };
        
        window.zee5Monitor.getTokens = function() {
            return this.tokens;
        };

        // Initialize monitoring
        window.zee5Monitor.init();
        """
        
        # Function to ensure monitor is active
        ensure_monitor_script = """
        if (!window.zee5Monitor || !window.originalFetch) {
            """ + inject_script + """
        } else {
            // Ensure methods are available
            window.zee5Monitor.getNewRequests = function() {
                const newRequests = this.requests.slice(this.lastPrintedIndex);
                this.lastPrintedIndex = this.requests.length;
                return newRequests;
            };
            
            window.zee5Monitor.getTokens = function() {
                return this.tokens;
            };
            
            window.zee5Monitor.init();
        }
        return true;
        """
        
        def ensure_monitoring():
            try:
                driver.execute_script(ensure_monitor_script)
                # Verify methods exist
                check_script = """
                return {
                    hasMonitor: !!window.zee5Monitor,
                    hasGetNewRequests: typeof window.zee5Monitor.getNewRequests === 'function',
                    hasGetTokens: typeof window.zee5Monitor.getTokens === 'function'
                };
                """
                status = driver.execute_script(check_script)
                if not all(status.values()):
                    print("Warning: Monitor methods not properly initialized")
                    return False
                return True
            except Exception as e:
                return False
        
        print("Setting up monitoring...")
        ensure_monitoring()
        
        print("Navigating to zee5.com...")
        driver.get("https://www.zee5.com")
        print("Refreshing page to capture tokens...")
        driver.execute_script("window.location.reload();")
        
        print("\nMonitoring requests to capture tokens...")
        
        while True:
            if ensure_monitoring():
                new_requests = driver.execute_script("return window.zee5Monitor.getNewRequests();")
                if new_requests:
                    for req in new_requests:
                        headers = req.get('headers', {})
                        auth_token = headers.get('Authorization') or headers.get('authorization')
                        access_token = headers.get('x-access-token')
                        
                        if auth_token and access_token:
                            print("\n")
                            print("Found Tokens:")
                            print("="*50)
                            print("")
                            print(f"Authorization: bearer {auth_token.replace('bearer ', '')}")
                            print("")
                            print(f"x-access-token: {access_token}")
                            print("")
                            print("="*50)
                            print("")
                            
                            # Save tokens to file
                            os.makedirs("data", exist_ok=True)
                            with open("data/zee_tokens.json", "w") as f:
                                json.dump({
                                    "bearer_token": auth_token.replace('bearer ', ''),
                                    "access_token": access_token,
                                    "timestamp": time.time()
                                }, f, indent=4)
                            print("Tokens saved to data/zee_tokens.json")
                            return  # Clean exit after finding tokens                
    except Exception as e:
        print(f"Error: {str(e)}")
    finally:
        if driver:
            driver.quit()

def check_existing_tokens():
    """Check if existing tokens are less than 24 hours old"""
    try:
        if os.path.exists("data/zee_tokens.json"):
            with open("data/zee_tokens.json", "r") as f:
                data = json.load(f)
                if "timestamp" in data:
                    age = time.time() - data["timestamp"]
                    if age < 24 * 3600:  # Less than 24 hours
                        print("Using existing tokens (less than 24 hours old)")
                        print("\nExisting Tokens:")
                        print("="*50)
                        print("")
                        print(f"Authorization: bearer {data['bearer_token']}")
                        print("")
                        print(f"x-access-token: {data['access_token']}")
                        print("")
                        print("="*50)
                        return True
    except Exception as e:
        print(f"Error checking existing tokens: {str(e)}")
    return False

if __name__ == "__main__":
    if not check_existing_tokens():
        extract_tokens() 