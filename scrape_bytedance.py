import asyncio
import json
import os
import re
from playwright.async_api import async_playwright
from markdownify import markdownify as md

OUTPUT_DIR = "data/bytedance"
os.makedirs(OUTPUT_DIR, exist_ok=True)

BASE_URL = "https://jobs.bytedance.com/campus/position/list"
API_PATTERN = "**/api/v1/search/job/posts*"

async def scrape_jobs():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            # viewport={"width": 1280, "height": 800} # default is fine
        )
        page = await context.new_page()

        # User Provided URL with filters
        USER_URL = "https://jobs.bytedance.com/campus/position/list?keywords=&category=6704215862603155720%2C6704215956018694411%2C6704215862557018372%2C6704215957146962184%2C6704215886108035339%2C6704215888985327886%2C6704215888985327886%2C6704216109274368264%2C6938376045242353957%2C6704215963966900491%2C6704219534724696331%2C6704215958816295181%2C6704217321877014787%2C6704216296701036811%2C6704216635923761412%2C6704219452277262596&location=&project=&type=&job_hot_flag=&current=1&limit=10&functionCategory=&tag="

        # Parse params to rebuild URL dynamically
        from urllib.parse import urlparse, parse_qs, urlencode
        parsed = urlparse(USER_URL)
        params = parse_qs(parsed.query)

        # Set higher limit for efficiency
        limit = 50
        params['limit'] = [str(limit)]

        jobs_collected = 0
        offset = 0
        total_jobs = -1 # Unknown initially

        print(f"Starting full scrape...")

        while True:
            # Update offset and current page
            # API uses offset, Frontend uses current
            params['offset'] = [str(offset)]
            current_page = (offset // limit) + 1
            params['current'] = [str(current_page)]

            # Construct new query string
            # Note: parse_qs returns lists, urlencode handles doseq=True to keep lists or we flatten
            new_query = urlencode(params, doseq=True)
            url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}?{new_query}"

            # Create a future to capture the response
            api_response_future = asyncio.Future()

            def handle_response(response):
                if API_PATTERN.strip("*") in response.url and response.status == 200:
                    if not api_response_future.done():
                        api_response_future.set_result(response)

            page.on("response", handle_response)

            print(f"Navigating to offset {offset} (Collected: {jobs_collected}/{total_jobs if total_jobs > 0 else '?'})...")
            # Relax wait condition since we monitor network explicitly
            await page.goto(url, wait_until="domcontentloaded")

            try:
                # Wait for the API response
                response = await asyncio.wait_for(api_response_future, timeout=15)
                data = await response.json()

                data_obj = data.get("data")
                if isinstance(data_obj, dict):
                    items = data_obj.get("items") or data_obj.get("job_post_list") or []
                    count = data_obj.get("count", 0)
                    if total_jobs == -1:
                        total_jobs = count
                        print(f"Total jobs available: {total_jobs}")
                else:
                    items = []

                if not items:
                    print("No more items found.")
                    break

                print(f"Found {len(items)} items on this page.")

                for job in items:
                    try:
                        process_job(job)
                        jobs_collected += 1
                    except Exception as e:
                        print(f"Error processing job: {e}")

                offset += limit

                # Check completion
                current_count_in_response = data_obj.get("count", total_jobs)
                if jobs_collected >= current_count_in_response:
                    print("Collected all available jobs.")
                    break

                # Rate limit prevention
                # await asyncio.sleep(0.5)

            except asyncio.TimeoutError:
                print("Timeout waiting for API response. Retrying same offset...")
                # Optional: break or retry logic. For now, break to avoid infinite loop
                break
            except Exception as e:
                print(f"Error processing page: {e}")
                break
            finally:
                page.remove_listener("response", handle_response)

        await browser.close()
        print(f"Scraping completed. Total jobs collected: {jobs_collected}")


def process_job(job):
    job_id = job.get("id")
    job_code = job.get("code", "Unknown") # Job Code
    title = job.get("title", "Unknown Request")

    # Extract fields
    description_html = job.get("description", "")
    requirement_html = job.get("requirement", "")

    # Convert to Markdown
    description_md = md(description_html)
    requirement_md = md(requirement_html)

    # Parse Description Sections
    # 1. Team Intro (团队介绍/部门介绍)
    # 2. Core Work (核心工作/工作内容/职位描述/numbered list)

    team_intro = ""
    daily_intern = ""
    core_work = ""

    # Regex Patterns
    # Stop looking for team intro if we hit explicit core work header OR a numbered list (start of core work)
    team_intro_pattern = re.compile(r'(团队介绍|部门介绍)[:：](.*?)(?=(核心工作|工作内容|职位描述|1\.|1、|$))', re.DOTALL | re.IGNORECASE)
    core_work_pattern = re.compile(r'(核心工作|工作内容|职位描述)[:：]?(.*?)$', re.DOTALL | re.IGNORECASE)

    # Extract Team Intro
    team_match = team_intro_pattern.search(description_md)
    if team_match:
        team_intro = team_match.group(2).strip()
        # Daily intern is likely what's before team intro
        start_idx = team_match.start()
        daily_intern = description_md[:start_idx].strip()
    else:
        # If no team intro, checks needed. Assume daily intern is before Core Work if explicit
        core_match = core_work_pattern.search(description_md)
        if core_match:
            daily_intern = description_md[:core_match.start()].strip()

    # Extract Core Work
    # 1. Try explicit header first
    core_match = core_work_pattern.search(description_md)

    # Note: "职位描述" is ambiguous, it is the main header but also used for core work sometimes.
    # If the match is at the very beginning (index 0), it might be the general header, ignore it if content is long.
    # But here we are processing the CONTENT of "职位描述", so `description_md` IS the content.

    if core_match:
        # Verify if this match is "real" core work or just catching the section title?
        # Since we stripped the main title, any "职位描述" inside is likely a sub-header.
        # However, checking if it captures everything effectively.
        candidate_work = core_match.group(2).strip()
        if len(candidate_work) > 10: # arbitrary check for validity
             core_work = candidate_work

    # 2. If no explicit header found (or core work is empty), look for Implicit Numbered List after Team Intro
    if not core_work and team_match:
        # Check what's remaining after team intro
        remaining = description_md[team_match.end():].strip()
        # Does it start with 1. or 1、 ?
        if re.match(r'^(1\.|1、)', remaining):
            core_work = remaining

    if not core_work and not team_intro:
         # Fallback: if structure is completely missing, treat whole thing as... check logic
         # Use heuristic: if it looks like a list?
         pass # Leave empty or daily_intern takes it? Default to daily_intern usually catches intro

    # Clean up artifacts
    daily_intern = daily_intern.replace("日常实习：", "").strip()

    # Metadata
    city_list = job.get("city_list")
    city_info = job.get("city_info")

    if isinstance(city_list, list) and city_list:
        locations = ", ".join([c.get("name", "") for c in city_list if isinstance(c, dict)])
    elif isinstance(city_info, dict):
         locations = city_info.get("name", "Unknown")
    else:
         locations = "Unknown"

    job_categories = job.get("job_category", {})
    category = job_categories.get("name", "Unknown") if isinstance(job_categories, dict) else "Unknown"

    sub_categories = job.get("sub_job_category", {})
    sub_category = sub_categories.get("name", "") if isinstance(sub_categories, dict) else ""

    full_category = f"{category} - {sub_category}" if sub_category else category

    content = f"""# {title}

**ID**: {job_id}
**Code**: {job_code}
**Location**: {locations}
**Category**: {full_category}
**Type**: {job.get("recruit_type", {}).get("name", "Unknown")}

## 职位描述

### 团队介绍
{team_intro}

### 实习要求
{daily_intern}

### 核心工作
{core_work}

## 职位要求
{requirement_md}
"""

    # Save to file with ID only
    filename = f"{OUTPUT_DIR}/{job_id}.md"

    with open(filename, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"Saved: {filename}")

if __name__ == "__main__":
    asyncio.run(scrape_jobs())
