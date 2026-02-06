import requests
import time
from fake_useragent import UserAgent

PROXY_URL = "http://04c2a2c98864ae89:QnjrV4yc@res.geonix.com:10006"
proxies = {
    "http": PROXY_URL,
    "https": PROXY_URL,
}
ua = UserAgent()

def test_proxy():
    print("Testing proxy connection...")
    try:
        # Get IP
        r = requests.get("http://httpbin.org/ip", proxies=proxies, timeout=10)
        print(f"IP Response: {r.text.strip()}")
        
        # Get UA
        random_ua = ua.random
        headers = {"User-Agent": random_ua}
        r = requests.get("http://httpbin.org/user-agent", proxies=proxies, headers=headers, timeout=10)
        print(f"UA Response: {r.text.strip()}")
        print(f"Sent UA: {random_ua}")
        
    except Exception as e:
        print(f"Proxy test failed: {e}")

if __name__ == "__main__":
    test_proxy()
