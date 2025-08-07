from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from duckduckgo_search import DDGS
import requests
from bs4 import BeautifulSoup
import re

app = FastAPI()

# Serve static and HTML
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

def scrape_full_text_and_images(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/113.0.0.0 Safari/537.36"
    }
    response = requests.get(url, headers=headers, timeout=10)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    # Clean
    for tag in soup(['script', 'style', 'header', 'footer', 'nav', 'aside', 'form', 'noscript']):
        tag.decompose()

    # Text
    text = soup.get_text(separator="\n")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    full_text = "\n".join(lines)

    # Images
    image_urls = []
    for img in soup.find_all("img"):
        src = img.get("src")
        if src and not src.startswith("data:"):
            if src.startswith("//"):
                src = "https:" + src
            elif src.startswith("/"):
                src = requests.compat.urljoin(url, src)
            elif not src.startswith("http"):
                src = requests.compat.urljoin(url, "/" + src)
            image_urls.append(src)

    return full_text, image_urls[:10]

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/api/search")
def api_search(q: str):
    results = []
    try:
        with DDGS() as ddgs:
            search_results = ddgs.text(q, max_results=5)

            for item in search_results:
                url = item["href"]
                title = item.get("title", "")
                snippet = item.get("body", "")
                try:
                    full_text, images = scrape_full_text_and_images(url)
                except Exception as e:
                    full_text, images = f"Failed to fetch content: {e}", []

                results.append({
                    "title": title,
                    "url": url,
                    "snippet": snippet,
                    "full_text": full_text[:5000],
                    "images": images
                })

        return JSONResponse(content={"results": results})

    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)
