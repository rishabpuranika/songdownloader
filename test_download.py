#!/usr/bin/env python3

import os
import time
import requests
import json

def test_download():
    # Test URL - use a short video that should be available
    test_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    
    print("Testing download functionality...")
    print(f"Test URL: {test_url}")
    
    # Test data
    test_data = {
        "url": test_url,
        "format": "mp4",
        "quality": "360p"
    }
    
    try:
        # Send request to Flask app (assuming it's running on port 5000)
        response = requests.post(
            "http://localhost:5000/download",
            json=test_data,
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        
        print(f"Response status: {response.status_code}")
        print(f"Response body: {response.text}")
        
        if response.status_code == 200:
            print("Download request sent successfully!")
            print("Check the temp_downloads directory and app logs for results.")
        else:
            print(f"Download request failed with status {response.status_code}")
            
    except requests.exceptions.ConnectionError:
        print("ERROR: Cannot connect to Flask app. Make sure it's running on port 5000")
        print("Run: python3 app.py")
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    test_download()
