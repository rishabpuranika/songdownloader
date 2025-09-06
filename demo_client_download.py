#!/usr/bin/env python3
"""
Demo script to show how the client-side download works
This simulates what happens when a user clicks download on the website
"""

import requests
import json
import webbrowser
import time

def simulate_client_download():
    """Simulate the client-side download process"""
    
    # Step 1: User enters YouTube URL
    test_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    print(f"🎬 User enters YouTube URL: {test_url}")
    
    # Step 2: Website extracts direct download URL
    print("\n📡 Website extracting direct download URL...")
    
    request_data = {
        "url": test_url,
        "format": "mp4", 
        "quality": "360p"
    }
    
    try:
        # This simulates what happens when user clicks download
        response = requests.post(
            "http://localhost:5000/get_download_url",
            json=request_data,
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            print("✅ Server response received")
            
            if data.get('success') and data.get('direct_url'):
                # Step 3: Browser downloads file directly to user's device
                print(f"🎥 Video title: {data.get('title', 'Unknown')}")
                print(f"📁 Filename: {data.get('filename', 'video.mp4')}")
                print(f"🔗 Direct URL obtained (length: {len(data['direct_url'])} chars)")
                
                print("\n🎯 SUCCESS: Direct download URL ready!")
                print("   In the browser, this would automatically trigger a download")
                print("   The file downloads directly to the user's device")
                print("   No files are stored on the server!")
                
                # Optional: Open the direct URL in browser (uncomment to test)
                # print(f"\n🌐 Opening direct download URL in browser...")
                # webbrowser.open(data['direct_url'])
                
                return True
                
            elif data.get('needs_processing'):
                print("🔄 Server-side processing needed (audio conversion)")
                print("   This would fall back to server processing")
                return True
            else:
                print("❌ No direct URL available")
                return False
        else:
            print(f"❌ Server error: {response.status_code}")
            print(response.text)
            return False
            
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to Flask app")
        print("   Run: python3 app.py")
        print("   Then run this script again")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("🚀 DEMO: CLIENT-SIDE YOUTUBE DOWNLOAD")
    print("=" * 60)
    print("This demonstrates how videos download directly to user devices")
    print()
    
    success = simulate_client_download()
    
    print("\n" + "=" * 60)
    if success:
        print("✅ DEMO SUCCESSFUL!")
        print("   Videos will download directly to client devices")
        print("   No server storage used on Render")
    else:
        print("❌ DEMO FAILED")
        print("   Check if Flask app is running: python3 app.py")
    print("=" * 60)
