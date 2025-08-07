from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from duckduckgo_search import DDGS
import requests
from bs4 import BeautifulSoup
import json

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
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        for tag in soup(['script', 'style', 'header', 'footer', 'nav', 'aside', 'form', 'noscript']):
            tag.decompose()

        text = soup.get_text(separator="\n")
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        full_text = "\n".join(lines)

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
    except requests.RequestException as e:
        print(f"Error fetching {url}: {e}")
        return f"Failed to fetch content: {e}", []


def get_ollama_answer(context: str, query: str):
    ollama_url = "http://localhost:11434/api/generate"
    prompt = (
        f"Based on the following information, please provide a comprehensive answer to the user's query: '{query}'.\n\n"
        f"--- Information ---\n{context}\n\n--- End of Information ---\n\n"
        "Please structure your answer clearly. If the information is insufficient, state that."
    )

    payload = {
        "model": "llama3",
        "prompt": prompt,
        "stream": False
    }

    try:
        response = requests.post(ollama_url, json=payload, timeout=300)
        response.raise_for_status()
        # The new logic assumes response is a single JSON object when stream=False
        return response.json().get("response", "").strip()

    except requests.RequestException as e:
        return f"Error contacting Ollama: {e}"
    except Exception as e:
        return f"An unexpected error occurred with Ollama: {e}"


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/api/search")
def api_search(q: str):
    results = []
    all_scraped_text = ""
    try:
        with DDGS() as ddgs:
            # --- FIX APPLIED HERE ---
            # Explicitly set the region to 'wt-wt' for international/English results
            search_results = ddgs.text(q, region='wt-wt', max_results=10)

            for i, item in enumerate(search_results):
                url = item["href"]
                title = item.get("title", "")
                snippet = item.get("body", "")
                try:
                    full_text, images = scrape_full_text_and_images(url)
                    if full_text and not full_text.startswith("Failed to fetch"):
                        all_scraped_text += f"Source {i+1} ({url}):\n{full_text}\n\n"
                except Exception as e:
                    full_text, images = f"Failed to fetch content: {e}", []

                results.append({
                    "title": title,
                    "url": url,
                    "snippet": snippet,
                    "full_text": full_text[:5000],
                    "images": images
                })
        
        ollama_answer = get_ollama_answer(all_scraped_text, q)

        return JSONResponse(content={"results": results, "ollama_answer": ollama_answer})

    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)