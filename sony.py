import time
import requests
from telegraph import Telegraph
from requests.exceptions import ConnectionError, Timeout

def create_telegraph_page(retries=3, delay=2):
    # Create Telegraph account
    telegraph = Telegraph()
    
    # Try to create an account with retries
    for attempt in range(retries):
        try:
            print(f"Attempt {attempt+1}: Creating Telegraph account...")
            telegraph.create_account(short_name='XtRoN')
            break
        except (ConnectionError, Timeout) as e:
            if attempt < retries - 1:
                print(f"Connection error: {e}")
                print(f"Retrying in {delay} seconds...")
                time.sleep(delay)
                delay *= 2  # Exponential backoff
            else:
                print(f"Failed to connect after {retries} attempts.")
                print("Please check your internet connection and try again later.")
                return False
    
    # Define the HTML content
    html_content = """
<b>📥 DRM Downloader Bot – Professional Media Extraction Tool</b><br><br>

<b>Author:</b> <a href="https://t.me/XtRoN69xBot">XtRoN</a><br><br>

<b>🔹 Description:</b><br>
The <b>DRM Downloader Bot</b> is a reverse-engineered tool designed to interact with various OTT (Over-the-Top) platforms. It enables users to <b>download DRM-protected content</b> and <b>upload it directly as Telegram files or to Google Drive</b>. Built for efficiency and versatility, the bot supports a wide range of platforms (as listed in its capabilities), offering streamlined media management for personal use.

<hr>

<b>⚠️ Service Terms & Important Considerations (No Refund Policy)</b><br><br>

<b>1. Technical Nature & API Reliability</b><br>
- This service interacts with external APIs from OTT platforms, which may occasionally result in errors or downtime.<br>
- Such issues may originate from our side or the OTT provider and are beyond direct control.<br><br>

<b>2. Service Availability & Compensation Policy</b><br>
- The bot offers access to <b>multiple OTT platforms</b>, but does <b>not guarantee constant availability</b> of each individual service.<br>
- Access depends on resource and account availability. If one OTT service is down, you may continue using others — and this still counts as using the service.<br>
- <b>No compensation</b> is provided for individual platform outages unless you've purchased this <b>dedicated</b> solely for that platform and you're not using anything else.<br><br>

<b>3. Usage & Rate Limits</b><br>
- Continuous use of the same OTT service may trigger API rate limits, affecting all users.<br>
- To avoid this, users who require heavy usage are advised to purchase a <b>private bot</b>, which is available at <b>50% extra cost</b>.<br><br>

<b>4. Extended Downtime Policy</b><br>
- If the <b>entire bot remains non-functional for over 24 hours</b>, your validity will be <b>extended by one day</b> for each day of downtime.<br>
- In extreme cases (e.g., 7+ days of outage), you may be eligible for a <b>pro-rata refund</b> based on your remaining subscription duration.<br><br>

<b>5. Concurrency & Task Limits</b><br>
- <b>1 OTT service per task</b> and a <b>maximum of 3 concurrent tasks</b> across 3 different OTT platforms is allowed.<br><br>

<b>6. Bonus Support via TMDB</b><br>
- The bot integrates support from <b>TMDB</b>, allowing access to <b>high-quality content (up to 4K)</b>, including content from platforms like <b>Netflix</b>.<br>
- This feature is considered a <b>bonus</b>, especially useful for accessing rented or temporarily unavailable content. It is <b>not a guaranteed service</b>.<br><br>

<hr>

<b>🛠 Support & Assistance</b><br>
If you require help or have questions, please contact our support bot: <a href="https://t.me/XzEcHxAcessbot">@XzEcHxAcessbot</a>
"""

    # Try to create the page with retries
    for attempt in range(retries):
        try:
            print(f"Attempt {attempt+1}: Creating Telegraph page...")
            response = telegraph.create_page(
                title='DRM Downloader Bot – Service Description',
                author_name='XtRoN',
                author_url='https://t.me/XtRoN69xBot',
                html_content=html_content
            )
            
            # Output the link
            print("✅ Telegraph Page Created Successfully!")
            print("🔗 URL:", response['url'])
            return True
            
        except (ConnectionError, Timeout) as e:
            if attempt < retries - 1:
                print(f"Connection error: {e}")
                print(f"Retrying in {delay} seconds...")
                time.sleep(delay)
                delay *= 2  # Exponential backoff
            else:
                print(f"Failed to create page after {retries} attempts.")
                print("Please check your internet connection and try again later.")
                return False
        except Exception as e:
            print(f"Unexpected error: {e}")
            return False

if __name__ == "__main__":
    create_telegraph_page()