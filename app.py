from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import asyncio
import time
import random
from urllib.parse import urljoin, urlparse
from typing import Set, List, Dict, Any, Optional
import json
from datetime import datetime
import google.generativeai as genai
import os
import uuid
from pathlib import Path
import re
import logging
import zipfile
import shutil

from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
import markdownify

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Web Crawler API", version="2.0.0")

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create directories for file storage
STORAGE_DIR = Path("crawler_data")
CDN_DIR = Path("cdn_files")
STORAGE_DIR.mkdir(exist_ok=True)
CDN_DIR.mkdir(exist_ok=True)

# Mount static files for CDN
app.mount("/cdn", StaticFiles(directory=CDN_DIR), name="cdn")

# === CONFIGURATION ===
MAX_PAGES = 50
RATE_LIMIT_DELAY = 1.5
PROXY_LIST = [None]
CDN_BASE_URL = "http://localhost:8000/cdn"  # Change this to your domain in production

# Configure Gemini
GOOGLE_API_KEY = "AIzaSyCt4tDhsg7yn8n98J1ufXBsWpxVX9J7P_M"
genai.configure(api_key=GOOGLE_API_KEY)

# Global storage for crawl jobs
crawl_jobs: Dict[str, Dict] = {}

# File extensions to ignore
IGNORED_EXTENSIONS = {
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
    '.zip', '.rar', '.tar', '.gz', '.7z',
    '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.ico',
    '.mp4', '.avi', '.mov', '.wmv', '.flv', '.webm',
    '.mp3', '.wav', '.flac', '.aac', '.ogg',
    '.exe', '.msi', '.dmg', '.deb', '.rpm',
    '.css', '.js', '.xml', '.json', '.txt'
}

# === MODELS ===
class CrawlRequest(BaseModel):
    url: str
    allow_backward: bool = False
    max_pages: Optional[int] = 20

class CrawlStatus(BaseModel):
    job_id: str
    status: str
    progress: int
    total_pages: int
    current_url: Optional[str] = None
    completed_pages: List[Dict] = []
    json_ld_data: Optional[Dict] = None
    errors: List[str] = []
    cdn_url: Optional[str] = None
    download_url: Optional[str] = None

# === HELPER FUNCTIONS ===
def is_valid_url(url: str) -> bool:
    """Check if URL is valid and crawlable"""
    try:
        parsed = urlparse(url)
        
        # Must have scheme and netloc
        if not parsed.scheme or not parsed.netloc:
            return False
            
        # Only allow http/https schemes
        if parsed.scheme not in ['http', 'https']:
            return False
            
        # Check for file extensions to ignore
        path = parsed.path.lower()
        if any(path.endswith(ext) for ext in IGNORED_EXTENSIONS):
            return False
            
        # Ignore anchor links
        if parsed.fragment and not parsed.path:
            return False
            
        # Ignore javascript links
        if url.lower().startswith('javascript:'):
            return False
            
        # Ignore tel: and mailto: links
        if parsed.scheme in ['mailto', 'tel', 'ftp', 'sftp']:
            return False
            
        # Ignore social media and external service links that don't provide useful content
        # But allow LinkedIn company pages and other business profiles
        excluded_domains = {
            'facebook.com', 'twitter.com', 'instagram.com', 'youtube.com',
            'pinterest.com', 'tiktok.com', 'snapchat.com',
            'maps.google.com', 'maps.app.goo.gl', 'goo.gl', 'bit.ly',
            't.co', 'tinyurl.com', 'forms.gle', 'docs.google.com'
        }
        
        # Special handling for LinkedIn - allow company pages but not personal profiles
        domain = parsed.netloc.lower()
        if 'linkedin.com' in domain:
            # Allow company pages and business profiles
            if '/company/' in parsed.path or '/school/' in parsed.path or '/showcase/' in parsed.path:
                return True
            else:
                return False
        
        # Check if domain is in excluded list
        if any(excluded in domain for excluded in excluded_domains):
            return False
            
        return True
        
    except Exception:
        return False

def normalize_url(url: str) -> str:
    """Normalize URL by removing fragments and query parameters that don't affect content"""
    try:
        parsed = urlparse(url)
        # Remove fragment (anchor)
        normalized = parsed._replace(fragment='').geturl()
        return normalized
    except Exception:
        return url

async def fetch_rendered_page(url: str, proxy: str = None, max_retries: int = 3) -> str:
    """Fetch page content with better error handling"""
    for attempt in range(max_retries):
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=['--no-sandbox', '--disable-dev-shm-usage']
                )
                context = await browser.new_context(
                    proxy={"server": proxy} if proxy else None,
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                    ignore_https_errors=True
                )
                page = await context.new_page()

                # Set shorter timeouts
                page.set_default_timeout(20000)
                
                # Navigate with error handling
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                    # Wait for dynamic content but not too long
                    await asyncio.sleep(1)
                    content = await page.content()
                    await browser.close()
                    
                    if content and len(content) > 100:  # Ensure we got meaningful content
                        return content
                        
                except Exception as e:
                    logger.warning(f"Navigation failed for {url}: {e}")
                    await browser.close()
                    
        except Exception as e:
            logger.warning(f"Attempt {attempt + 1}/{max_retries} failed for {url}: {e}")
            
        # Exponential backoff
        if attempt < max_retries - 1:
            await asyncio.sleep(1 * (attempt + 1))

    logger.error(f"All attempts failed for {url}")
    return ""

def extract_links(html: str, base_url: str) -> List[str]:
    """Extract and filter valid links from HTML"""
    soup = BeautifulSoup(html, "html.parser")
    links = set()  # Use set to avoid duplicates
    
    for tag in soup.find_all("a", href=True):
        href = tag['href'].strip()
        
        # Skip empty hrefs
        if not href:
            continue
            
        # Convert relative URLs to absolute
        try:
            full_url = urljoin(base_url, href)
            normalized_url = normalize_url(full_url)
            
            # Validate the URL
            if is_valid_url(normalized_url):
                links.add(normalized_url)
                
        except Exception as e:
            logger.debug(f"Error processing link {href}: {e}")
            continue
    
    return list(links)

def clean_content(html: str, url: str) -> Dict:
    """Extract and clean content from HTML with better error handling"""
    try:
        soup = BeautifulSoup(html, "html.parser")
        
        # Remove script and style elements
        for script in soup(["script", "style", "nav", "footer", "header"]):
            script.decompose()
        
        metadata = {
            "title": "",
            "description": "",
            "robots": "",
            "keywords": "",
            "canonical_url": "",
            "h1_tags": [],
            "h2_tags": [],
            "h3_tags": [],
            "image_alt_texts": [],
            "internal_links": [],
            "external_links": [],
            "word_count": 0,
            "language": ""
        }
        
        # Extract title
        title_tag = soup.find("title")
        if title_tag:
            metadata["title"] = title_tag.get_text(strip=True)
        
        # Extract meta tags safely
        meta_tags = {
            "description": soup.find("meta", attrs={"name": "description"}),
            "robots": soup.find("meta", attrs={"name": "robots"}),
            "keywords": soup.find("meta", attrs={"name": "keywords"}),
            "canonical": soup.find("link", attrs={"rel": "canonical"}),
            "language": soup.find("meta", attrs={"name": "language"}) or soup.find("html", attrs={"lang": True})
        }
        
        for key, tag in meta_tags.items():
            if tag:
                if key == "canonical":
                    metadata["canonical_url"] = tag.get("href", "")
                elif key == "language":
                    metadata["language"] = tag.get("content", "") or tag.get("lang", "")
                else:
                    metadata[key] = tag.get("content", "")
        
        # Extract headings
        metadata["h1_tags"] = [h.get_text(strip=True) for h in soup.find_all("h1") if h.get_text(strip=True)]
        metadata["h2_tags"] = [h.get_text(strip=True) for h in soup.find_all("h2") if h.get_text(strip=True)]
        metadata["h3_tags"] = [h.get_text(strip=True) for h in soup.find_all("h3") if h.get_text(strip=True)]
        
        # Extract image alt texts
        metadata["image_alt_texts"] = [
            img.get("alt", "").strip() 
            for img in soup.find_all("img") 
            if img.get("alt", "").strip()
        ]
        
        # Extract and categorize links
        base_domain = urlparse(url).netloc
        for link in soup.find_all("a", href=True):
            href = link.get("href", "").strip()
            if not href:
                continue
                
            try:
                full_url = urljoin(url, href)
                if is_valid_url(full_url):
                    link_domain = urlparse(full_url).netloc
                    if link_domain == base_domain:
                        metadata["internal_links"].append(full_url)
                    else:
                        metadata["external_links"].append(full_url)
            except Exception:
                continue
        
        # Calculate word count from main content
        # Remove common non-content elements
        for element in soup.find_all(['nav', 'header', 'footer', 'aside', 'script', 'style']):
            element.decompose()
            
        text_content = soup.get_text()
        # Clean up whitespace and count words
        clean_text = ' '.join(text_content.split())
        metadata["word_count"] = len(clean_text.split()) if clean_text else 0
        
        # Convert to markdown with better formatting
        markdown = markdownify.markdownify(
            html, 
            heading_style="ATX",
            bullets="-"
        )
        
        return {
            "metadata": metadata,
            "markdown": markdown,
            "html": html,
            "text_content": clean_text[:1000] + "..." if len(clean_text) > 1000 else clean_text
        }
        
    except Exception as e:
        logger.error(f"Error cleaning content for {url}: {e}")
        return {
            "metadata": {
                "title": "Error processing page",
                "description": "",
                "word_count": 0,
                "h1_tags": [],
                "h2_tags": [],
                "h3_tags": [],
                "image_alt_texts": [],
                "internal_links": [],
                "external_links": []
            },
            "markdown": "",
            "html": html,
            "text_content": ""
        }

def create_website_folder_structure(job_id: str, website_domain: str, pages_data: List[Dict]) -> tuple[str, str]:
    """Create folder structure with individual JSON files for each page"""
    
    # Clean domain name for folder
    clean_domain = re.sub(r'[^\w\-_.]', '_', website_domain)
    website_folder = STORAGE_DIR / f"{clean_domain}_{job_id}"
    website_folder.mkdir(exist_ok=True)
    
    # Create individual JSON files for each page
    page_files = []
    for i, page_data in enumerate(pages_data):
        try:
            # Generate individual JSON-LD for this page
            json_ld = generate_json_ld(page_data)
            
            # Create filename from URL
            url_path = urlparse(page_data['url']).path
            if url_path == '/' or url_path == '':
                filename = 'homepage.json'
            else:
                # Clean path for filename
                filename = re.sub(r'[^\w\-_.]', '_', url_path.strip('/').replace('/', '_'))
                if not filename.endswith('.json'):
                    filename += '.json'
            
            # Ensure unique filename
            file_path = website_folder / filename
            counter = 1
            while file_path.exists():
                name, ext = filename.rsplit('.', 1)
                file_path = website_folder / f"{name}_{counter}.{ext}"
                counter += 1
            
            # Create comprehensive page data
            page_json_data = {
                "page_info": {
                    "url": page_data['url'],
                    "title": page_data['metadata']['title'],
                    "description": page_data['metadata']['description'],
                    "word_count": page_data['metadata']['word_count'],
                    "crawled_at": datetime.now().isoformat(),
                    "h1_tags": page_data['metadata']['h1_tags'],
                    "h2_tags": page_data['metadata']['h2_tags'],
                    "internal_links_count": len(page_data['metadata']['internal_links']),
                    "external_links_count": len(page_data['metadata']['external_links'])
                },
                "json_ld": json_ld,
                "metadata": page_data['metadata'],
                "content_preview": page_data.get('text_content', '')[:1000]
            }
            
            # Write individual page JSON file
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(page_json_data, f, indent=2, ensure_ascii=False)
            
            page_files.append({
                "filename": file_path.name,
                "url": page_data['url'],
                "title": page_data['metadata']['title']
            })
            
        except Exception as e:
            logger.error(f"Error creating file for {page_data['url']}: {e}")
            continue
    
    # Create master index file
    index_data = {
        "website": {
            "domain": website_domain,
            "crawl_date": datetime.now().isoformat(),
            "total_pages": len(page_files),
            "job_id": job_id
        },
        "pages": page_files,
        "usage_instructions": {
            "self_hosted": "Copy all JSON files to your server and reference them individually",
            "cdn_integration": f"Use our CDN: {CDN_BASE_URL}/{clean_domain}_{job_id}/",
            "script_tag": f'<script src="{CDN_BASE_URL}/{clean_domain}_{job_id}/schema-loader.js"></script>'
        }
    }
    
    with open(website_folder / 'index.json', 'w', encoding='utf-8') as f:
        json.dump(index_data, f, indent=2, ensure_ascii=False)
    
    # Create schema loader script for CDN integration
    create_schema_loader_script(website_folder, clean_domain, job_id, page_files)
    
    # Create ZIP file for download
    zip_path = STORAGE_DIR / f"{clean_domain}_{job_id}.zip"
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file_path in website_folder.rglob('*'):
            if file_path.is_file():
                zipf.write(file_path, file_path.relative_to(website_folder))
    
    # Copy to CDN directory for hosting
    cdn_website_folder = CDN_DIR / f"{clean_domain}_{job_id}"
    if cdn_website_folder.exists():
        shutil.rmtree(cdn_website_folder)
    shutil.copytree(website_folder, cdn_website_folder)
    
    return str(zip_path), f"{CDN_BASE_URL}/{clean_domain}_{job_id}/"

def create_schema_loader_script(folder_path: Path, domain: str, job_id: str, page_files: List[Dict]):
    """Create a JavaScript file that automatically loads appropriate JSON-LD schema"""
    
    script_content = f"""
// Schema Loader for {domain}
// Generated on {datetime.now().isoformat()}
// Job ID: {job_id}

(function() {{
    'use strict';
    
    const SCHEMA_BASE_URL = '{CDN_BASE_URL}/{domain}_{job_id}/';
    const PAGE_SCHEMAS = {json.dumps(page_files, indent=4)};
    
    function getCurrentPageSchema() {{
        const currentUrl = window.location.href;
        const currentPath = window.location.pathname;
        
        // Find matching schema based on URL or path
        for (const page of PAGE_SCHEMAS) {{
            const pageUrl = new URL(page.url);
            const pagePath = pageUrl.pathname;
            
            // Exact URL match
            if (currentUrl === page.url) {{
                return page.filename;
            }}
            
            // Path match
            if (currentPath === pagePath) {{
                return page.filename;
            }}
            
            // Homepage match
            if ((currentPath === '/' || currentPath === '') && 
                (pagePath === '/' || page.filename === 'homepage.json')) {{
                return page.filename;
            }}
        }}
        
        // Default to homepage schema if no match found
        return PAGE_SCHEMAS.find(p => p.filename === 'homepage.json')?.filename || PAGE_SCHEMAS[0]?.filename;
    }}
    
    async function loadAndInjectSchema() {{
        try {{
            const schemaFile = getCurrentPageSchema();
            if (!schemaFile) {{
                console.warn('No schema file found for current page');
                return;
            }}
            
            const response = await fetch(SCHEMA_BASE_URL + schemaFile);
            if (!response.ok) {{
                throw new Error(`Failed to load schema: ${{response.status}}`);
            }}
            
            const schemaData = await response.json();
            const jsonLd = schemaData.json_ld;
            
            // Create and inject script tag
            const script = document.createElement('script');
            script.type = 'application/ld+json';
            script.textContent = JSON.stringify(jsonLd, null, 2);
            
            // Remove existing schema if any
            const existing = document.querySelector('script[type="application/ld+json"][data-crawler-generated]');
            if (existing) {{
                existing.remove();
            }}
            
            script.setAttribute('data-crawler-generated', 'true');
            document.head.appendChild(script);
            
            console.log('Schema loaded successfully:', schemaFile);
            
            // Dispatch custom event
            window.dispatchEvent(new CustomEvent('schemaLoaded', {{
                detail: {{ schemaFile, jsonLd, pageInfo: schemaData.page_info }}
            }}));
            
        }} catch (error) {{
            console.error('Error loading schema:', error);
        }}
    }}
    
    // Load schema when DOM is ready
    if (document.readyState === 'loading') {{
        document.addEventListener('DOMContentLoaded', loadAndInjectSchema);
    }} else {{
        loadAndInjectSchema();
    }}
    
    // Expose utility functions
    window.SchemaLoader = {{
        reload: loadAndInjectSchema,
        getAvailableSchemas: () => PAGE_SCHEMAS,
        getCurrentSchema: getCurrentPageSchema,
        baseUrl: SCHEMA_BASE_URL
    }};
    
}})();
"""
    
    script_path = folder_path / 'schema-loader.js'
    with open(script_path, 'w', encoding='utf-8') as f:
        f.write(script_content)
    
    # Also create a minified version
    minified_content = re.sub(r'\s+', ' ', script_content).strip()
    minified_path = folder_path / 'schema-loader.min.js'
    with open(minified_path, 'w', encoding='utf-8') as f:
        f.write(minified_content)
    """Generate JSON-LD schema with better error handling"""
    try:
        model = genai.GenerativeModel('gemini-2.0-flash')

        def classify_content_type(md_text: str, metadata: Dict) -> str:
            lower_text = md_text.lower()
            title = metadata.get('title', '').lower()
            
            # More sophisticated content type detection
            if any(word in lower_text for word in ['faq', 'frequently asked', 'questions and answers']):
                return "FAQPage"
            elif any(word in lower_text for word in ['buy now', 'add to cart', 'purchase', 'price', '$', '₹']):
                return "Product"
            elif any(word in title + lower_text for word in ['service', 'consulting', 'solution']):
                return "Service"
            elif any(word in lower_text for word in ['about us', 'about', 'company', 'team', 'history']):
                return "AboutPage"
            elif any(word in lower_text for word in ['contact', 'reach us', 'get in touch', 'address']):
                return "ContactPage"
            elif any(word in lower_text for word in ['blog', 'article', 'news', 'post', 'published']):
                return "Article"
            else:
                return "WebPage"

        content_type = classify_content_type(page_data['markdown'], page_data['metadata'])
        content_snippet = page_data['markdown'][:3000]  # Reasonable limit for API

        prompt = f"""
        Generate a comprehensive JSON-LD schema for this webpage. Focus on creating rich, semantic markup that will help search engines and AI systems understand the content.

        Page Details:
        URL: {page_data['url']}
        Title: {page_data['metadata']['title']}
        Description: {page_data['metadata']['description']}
        Content Type: {content_type}
        H1 Tags: {page_data['metadata']['h1_tags'][:3]}
        H2 Tags: {page_data['metadata']['h2_tags'][:5]}
        Word Count: {page_data['metadata']['word_count']}

        Content Preview:
        {content_snippet}

        Requirements:
        1. Use schema.org vocabulary with @context
        2. Include appropriate @type based on content analysis
        3. Add Organization schema if business-related
        4. Include BreadcrumbList for navigation
        5. Add relevant properties like name, description, url
        6. Include dateModified as current date
        7. Add author/publisher information when applicable
        8. Ensure all URLs are absolute

        Return only valid JSON-LD without markdown formatting.
        """

        response = model.generate_content(prompt)
        json_ld_text = response.text.strip()

        # Clean response
        if json_ld_text.startswith("```json"):
            json_ld_text = json_ld_text.replace("```json", "").replace("```", "").strip()
        elif json_ld_text.startswith("```"):
            json_ld_text = json_ld_text.replace("```", "").strip()

        json_ld = json.loads(json_ld_text)
        
        # Validate and ensure required fields
        if not isinstance(json_ld, dict):
            raise ValueError("Generated JSON-LD is not a valid object")
            
        # Ensure context and type are present
        json_ld["@context"] = json_ld.get("@context", "https://schema.org")
        if "@type" not in json_ld:
            json_ld["@type"] = content_type
            
        return json_ld

    except Exception as e:
        logger.error(f"Error generating JSON-LD for {page_data['url']}: {e}")
        # Return fallback schema
        return {
            "@context": "https://schema.org",
            "@type": "WebPage",
            "name": page_data['metadata']['title'] or "Untitled Page",
            "url": page_data['url'],
            "description": page_data['metadata']['description'] or "No description available",
            "dateModified": datetime.now().isoformat(),
            "wordCount": page_data['metadata']['word_count']
        }

# === CRAWLER ===
class AsyncCrawler:
    def __init__(self, start_url: str, job_id: str, allow_backward: bool = False, max_pages: int = 20):
        self.start_url = start_url
        self.job_id = job_id
        self.allow_backward = allow_backward
        self.max_pages = max_pages
        self.visited: Set[str] = set()
        self.queue: List[str] = [start_url]
        self.domain = urlparse(start_url).netloc
        self.results = []
        self.errors = []

    def should_visit(self, url: str) -> bool:
        """Determine if URL should be crawled"""
        # Normalize URL for comparison
        normalized_url = normalize_url(url)
        
        if normalized_url in self.visited:
            return False
            
        if not is_valid_url(normalized_url):
            return False
            
        # Domain restriction
        if not self.allow_backward:
            url_domain = urlparse(normalized_url).netloc
            if url_domain != self.domain:
                return False
                
        return True

    async def crawl(self):
        """Main crawling logic with improved error handling"""
        try:
            crawl_jobs[self.job_id]["status"] = "crawling"
            logger.info(f"Starting crawl for job {self.job_id} with URL: {self.start_url}")
            
            while self.queue and len(self.visited) < self.max_pages:
                url = self.queue.pop(0)
                normalized_url = normalize_url(url)
                
                if not self.should_visit(normalized_url):
                    continue
                
                # Update current URL being processed
                crawl_jobs[self.job_id]["current_url"] = normalized_url
                crawl_jobs[self.job_id]["progress"] = len(self.visited)
                
                logger.info(f"Crawling: {normalized_url}")

                # Fetch page content
                proxy = random.choice(PROXY_LIST)
                html = await fetch_rendered_page(normalized_url, proxy)
                
                if not html:
                    error_msg = f"Failed to fetch content from {normalized_url}"
                    self.errors.append(error_msg)
                    logger.warning(error_msg)
                    continue

                # Mark as visited
                self.visited.add(normalized_url)
                
                # Process content
                try:
                    content = clean_content(html, normalized_url)
                    page_result = {"url": normalized_url, **content}
                    self.results.append(page_result)
                    
                    # Update completed pages with more detailed information
                    crawl_jobs[self.job_id]["completed_pages"].append({
                        "url": normalized_url,
                        "title": content["metadata"]["title"] or "Untitled",
                        "word_count": content["metadata"]["word_count"],
                        "description": content["metadata"]["description"][:200] + "..." if len(content["metadata"]["description"]) > 200 else content["metadata"]["description"],
                        "h1_tags": content["metadata"]["h1_tags"][:3],
                        "h2_tags": content["metadata"]["h2_tags"][:5],
                        "status": "completed",
                        "timestamp": datetime.now().isoformat(),
                        "content_preview": content["text_content"][:500] + "..." if len(content["text_content"]) > 500 else content["text_content"],
                        "internal_links_count": len(content["metadata"]["internal_links"]),
                        "external_links_count": len(content["metadata"]["external_links"])
                    })
                    
                    # Extract and queue new links
                    new_links = extract_links(html, normalized_url)
                    for link in new_links:
                        if self.should_visit(link) and link not in self.queue:
                            self.queue.append(link)
                    
                    logger.info(f"Successfully processed {normalized_url} - Found {len(new_links)} links")
                    
                except Exception as e:
                    error_msg = f"Error processing content from {normalized_url}: {str(e)}"
                    self.errors.append(error_msg)
                    logger.error(error_msg)

                # Rate limiting
                await asyncio.sleep(RATE_LIMIT_DELAY)

            # Generate individual page files
            logger.info(f"Creating individual JSON files for {len(self.results)} pages")
            website_domain = urlparse(self.start_url).netloc
            zip_path, cdn_url = create_website_folder_structure(self.job_id, website_domain, self.results)
            
            # Generate consolidated JSON-LD for backward compatibility
            json_ld_data = {
                "website": website_domain,
                "crawl_date": datetime.now().isoformat(),
                "total_pages_crawled": len(self.results),
                "errors": self.errors,
                "cdn_url": cdn_url,
                "download_url": f"/download-folder/{self.job_id}",
                "integration": {
                    "cdn_script": f'<script src="{cdn_url}schema-loader.js"></script>',
                    "self_hosted": "Download the ZIP file and host the JSON files on your server"
                },
                "pages": []
            }
            
            for page in self.results:
                try:
                    page_schema = {
                        "url": page['url'],
                        "title": page['metadata']['title'],
                        "word_count": page['metadata']['word_count'],
                        "json_ld": generate_json_ld(page)
                    }
                    json_ld_data["pages"].append(page_schema)
                except Exception as e:
                    error_msg = f"Error generating JSON-LD for {page['url']}: {str(e)}"
                    self.errors.append(error_msg)
                    logger.error(error_msg)
            
            # Update final job status
            crawl_jobs[self.job_id]["json_ld_data"] = json_ld_data
            crawl_jobs[self.job_id]["status"] = "completed"
            crawl_jobs[self.job_id]["progress"] = len(self.visited)
            crawl_jobs[self.job_id]["errors"] = self.errors
            crawl_jobs[self.job_id]["cdn_url"] = cdn_url
            crawl_jobs[self.job_id]["download_url"] = f"/download-folder/{self.job_id}"
            
            logger.info(f"Crawl completed for job {self.job_id}. Processed {len(self.results)} pages with {len(self.errors)} errors")
            
        except Exception as e:
            error_msg = f"Critical error in crawl job {self.job_id}: {str(e)}"
            logger.error(error_msg)
            crawl_jobs[self.job_id]["status"] = "failed"
            crawl_jobs[self.job_id]["errors"] = self.errors + [error_msg]

        return self.results

# === API ENDPOINTS ===
@app.post("/crawl")
async def start_crawl(request: CrawlRequest, background_tasks: BackgroundTasks):
    """Start a new crawl job"""
    job_id = str(uuid.uuid4())
    
    # Validate URL
    if not is_valid_url(request.url):
        raise HTTPException(status_code=400, detail="Invalid URL provided")
    
    # Initialize job status
    crawl_jobs[job_id] = {
        "job_id": job_id,
        "status": "initializing",
        "progress": 0,
        "total_pages": min(request.max_pages or MAX_PAGES, MAX_PAGES),
        "current_url": None,
        "completed_pages": [],
        "json_ld_data": None,
        "errors": [],
        "start_time": datetime.now().isoformat(),
        "config": {
            "start_url": request.url,
            "allow_backward": request.allow_backward,
            "max_pages": min(request.max_pages or MAX_PAGES, MAX_PAGES)
        }
    }
    
    # Start crawling in background
    async def run_crawl():
        crawler = AsyncCrawler(
            request.url, 
            job_id, 
            request.allow_backward, 
            min(request.max_pages or MAX_PAGES, MAX_PAGES)
        )
        await crawler.crawl()
    
    background_tasks.add_task(run_crawl)
    
    return {"job_id": job_id, "status": "started", "message": "Crawl job initiated"}

@app.get("/status/{job_id}")
async def get_crawl_status(job_id: str):
    """Get the current status of a crawl job"""
    if job_id not in crawl_jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return crawl_jobs[job_id]

@app.get("/download-folder/{job_id}")
async def download_folder(job_id: str):
    """Download the complete website folder as ZIP"""
    if job_id not in crawl_jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = crawl_jobs[job_id]
    if job["status"] != "completed":
        raise HTTPException(status_code=400, detail="Crawl not completed")
    
    # Find the ZIP file
    website_domain = urlparse(job["config"]["start_url"]).netloc
    clean_domain = re.sub(r'[^\w\-_.]', '_', website_domain)
    zip_path = STORAGE_DIR / f"{clean_domain}_{job_id}.zip"
    
    if not zip_path.exists():
        raise HTTPException(status_code=404, detail="Download file not found")
    
    return FileResponse(
        path=zip_path,
        filename=f"{clean_domain}_schema_files.zip",
        media_type='application/zip'
    )

@app.get("/cdn-info/{job_id}")
async def get_cdn_info(job_id: str):
    """Get CDN integration information"""
    if job_id not in crawl_jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = crawl_jobs[job_id]
    if job["status"] != "completed" or not job.get("cdn_url"):
        raise HTTPException(status_code=400, detail="CDN not ready")
    
    website_domain = urlparse(job["config"]["start_url"]).netloc
    clean_domain = re.sub(r'[^\w\-_.]', '_', website_domain)
    
    return {
        "cdn_base_url": job["cdn_url"],
        "script_url": f"{job['cdn_url']}schema-loader.js",
        "script_url_min": f"{job['cdn_url']}schema-loader.min.js",
        "integration_code": f'<script src="{job["cdn_url"]}schema-loader.js"></script>',
        "integration_code_min": f'<script src="{job["cdn_url"]}schema-loader.min.js"></script>',
        "usage_instructions": {
            "step1": "Copy the script tag below",
            "step2": "Paste it in the <head> section of your website",
            "step3": "The script will automatically load the appropriate JSON-LD schema for each page",
            "features": [
                "Automatic page detection",
                "Dynamic schema injection",
                "No manual configuration required",
                "Works with SPAs and traditional websites"
            ]
        },
        "api_endpoints": {
            "list_files": f"{job['cdn_url']}index.json",
            "individual_pages": f"{job['cdn_url']}[filename].json"
        }
    }

@app.get("/page/{job_id}/{page_index}")
async def get_page_details(job_id: str, page_index: int):
    """Get detailed information about a specific crawled page"""
    if job_id not in crawl_jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = crawl_jobs[job_id]
    if page_index < 0 or page_index >= len(job["completed_pages"]):
        raise HTTPException(status_code=404, detail="Page not found")
    
    # Find the corresponding page in results
    page_url = job["completed_pages"][page_index]["url"]
    
    # Since we don't store full results in memory, we'll return the enhanced completed page data
    # In a production system, you might store this in a database
    return {
        "page_info": job["completed_pages"][page_index],
        "job_id": job_id,
        "page_index": page_index
    }

@app.delete("/job/{job_id}")
async def delete_job(job_id: str):
    """Delete a crawl job and its data"""
    if job_id not in crawl_jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    del crawl_jobs[job_id]
    return {"message": "Job deleted successfully"}

@app.get("/jobs")
async def list_jobs():
    """List all crawl jobs"""
    return {
        "jobs": [
            {
                "job_id": job_id,
                "status": job["status"],
                "start_time": job["start_time"],
                "progress": job["progress"],
                "total_pages": job["total_pages"]
            }
            for job_id, job in crawl_jobs.items()
        ]
    }

@app.get("/")
async def root():
    return {
        "message": "Advanced Web Crawler API",
        "version": "2.0.0",
        "features": [
            "Robust URL filtering",
            "Smart content extraction",
            "JSON-LD schema generation",
            "Real-time progress tracking",
            "Error handling and reporting"
        ]
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}