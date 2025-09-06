#!/usr/bin/env python3

import os
import requests
import json
from yt_dlp import YoutubeDL

def test_direct_url_extraction():
    """Test direct URL extraction functionality"""
    test_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    
    print("Testing direct URL extraction...")
    print(f"Test URL: {test_url}")
    
    # Test yt-dlp extraction directly
    ydl_opts = {
        'format': 'best[ext=mp4]/best',
        'quiet': True,
    }
    
    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(test_url, download=False)
            
            print(f"Video title: {info.get('title', 'Unknown')}")
            
            # Check what formats are available
            if 'formats' in info:
                print(f"Number of formats: {len(info['formats'])}")
                
                # Look for direct URLs
                for i, fmt in enumerate(info['formats'][:5]):  # Show first 5 formats
                    print(f"Format {i}: ext={fmt.get('ext')}, url_exists={bool(fmt.get('url'))}")
            
            # Check if direct URL extraction would work
            if 'url' in info:
                print("✓ Direct URL available in info")
                return True
            elif 'formats' in info:
                has_url = any(fmt.get('url') for fmt in info['formats'])
                print(f"✓ URL available in formats: {has_url}")
                return has_url
            else:
                print("✗ No URL found")
                return False
                
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def test_flask_endpoint():
    """Test the Flask /get_download_url endpoint"""
    test_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    
    print("\nTesting Flask endpoint...")
    
    test_data = {
        "url": test_url,
        "format": "mp4",
        "quality": "best"
    }
    
    try:
        response = requests.post(
            "http://localhost:5000/get_download_url",
            json=test_data,
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        
        print(f"Response status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Response: {json.dumps(data, indent=2)}")
            
            if data.get('success') and data.get('direct_url'):
                print("✓ Direct download URL obtained!")
                return True
            elif data.get('needs_processing'):
                print("✓ Server-side processing needed (expected for audio)")
                return True
            else:
                print("✗ No direct URL or processing flag")
                return False
        else:
            print(f"✗ HTTP error: {response.text}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("✗ Cannot connect to Flask app. Make sure it's running on port 5000")
        print("Run: python3 app.py")
        return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

if __name__ == "__main__":
    print("=== Testing Direct Download Functionality ===\n")
    
    # Test 1: Direct yt-dlp extraction
    extraction_works = test_direct_url_extraction()
    
    # Test 2: Flask endpoint
    flask_works = test_flask_endpoint()
    
    print(f"\n=== Results ===")
    print(f"Direct extraction: {'✓ PASS' if extraction_works else '✗ FAIL'}")
    print(f"Flask endpoint: {'✓ PASS' if flask_works else '✗ FAIL'}")
    
    if extraction_works and flask_works:
        print("\n🎉 Direct download functionality should work!")
        print("Users should be able to download directly to their devices.")
    else:
        print("\n⚠️  Some issues found. Check the logs above.")
