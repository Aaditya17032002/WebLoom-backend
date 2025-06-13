# 🕷️ Advanced Web Crawler with JSON-LD Schema Generator

A modern, scalable web crawler that generates rich JSON-LD schemas for websites with both self-hosted and CDN integration options.

## ✨ Features

### 🚀 **Core Functionality**
- **Async web crawling** with JavaScript-rendered page support
- **Smart URL filtering** (blocks email, tel, social media, file downloads)
- **LinkedIn business profile support** for enhanced company data
- **Real-time progress tracking** with timeline visualization
- **Individual JSON files** for each crawled page
- **Automatic JSON-LD schema generation** using Google Gemini AI

### 🎯 **Integration Options**
1. **Self-Hosted**: Download ZIP folder with individual JSON files
2. **CDN Integration**: Copy-paste script tag for automatic schema loading

### 🎨 **Modern UI**
- **Glassmorphism design** with gradient backgrounds
- **Timeline progress visualization** like advanced research tools
- **Clickable page details** with comprehensive information
- **Real-time status updates** and error handling
- **No vertical scrolling** - content areas scroll independently

## 🛠️ **Installation & Setup**

### Prerequisites
```bash
# Python 3.8+
# Node.js (for UI development)
```

### Backend Setup
```bash
# Clone the repository
git clone <repository-url>
cd web-crawler

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium

# Set your Google Gemini API key
export GOOGLE_API_KEY="your-gemini-api-key"
# Or add it directly to the main.py file
```

### Run the Application
```bash
# Start the FastAPI server
python main.py

# Server will run on http://localhost:8000
# Open the HTML file in your browser to use the UI
```

## 📁 **Output Structure**

### Self-Hosted Option
When you download the ZIP file, you get:

```
website_domain_jobid/
├── index.json                 # Master index with all pages
├── homepage.json             # Homepage schema
├── about.json                # About page schema
├── services.json             # Services page schema
├── contact.json              # Contact page schema
├── schema-loader.js          # Auto-loading script
└── schema-loader.min.js      # Minified version
```

### Individual Page JSON Structure
```json
{
  "page_info": {
    "url": "https://example.com/about",
    "title": "About Us - Company Name",
    "description": "Learn about our company history...",
    "word_count": 1250,
    "crawled_at": "2025-06-13T10:30:00Z",
    "h1_tags": ["About Our Company"],
    "h2_tags": ["Our History", "Our Mission", "Our Team"],
    "internal_links_count": 8,
    "external_links_count": 3
  },
  "json_ld": {
    "@context": "https://schema.org",
    "@type": "AboutPage",
    "name": "About Us - Company Name",
    "description": "Learn about our company history...",
    "url": "https://example.com/about",
    "mainEntity": {
      "@type": "Organization",
      "name": "Company Name",
      "description": "...",
      "foundingDate": "2010",
      "employee": {...}
    }
  },
  "metadata": {...},
  "content_preview": "First 1000 characters of page content..."
}
```

## 🌐 **Integration Methods**

### Method 1: CDN Integration (Recommended)
Simply add this script tag to your website's `<head>` section:

```html
<script src="https://your-crawler-domain.com/cdn/domain_jobid/schema-loader.js"></script>
```

**Features:**
- ✅ Automatic page detection
- ✅ Dynamic schema injection
- ✅ No manual configuration
- ✅ Works with SPAs and traditional websites
- ✅ Real-time schema updates

### Method 2: Self-Hosted
1. Download the ZIP file
2. Extract to your web server
3. Reference individual JSON files or use the loader script

**Manual Integration:**
```html
<script type="application/ld+json">
  // Contents of your specific page JSON file
</script>
```

**Auto-loader Integration:**
```html
<script src="/path/to/schema-loader.js"></script>
```

## 🔧 **API Endpoints**

### Core Endpoints
```
POST /crawl                    # Start a new crawl job
GET /status/{job_id}          # Get crawl progress and status
GET /page/{job_id}/{index}    # Get detailed page information
```

### Download Endpoints
```
GET /download-folder/{job_id}  # Download ZIP with all files
GET /cdn-info/{job_id}        # Get CDN integration details
```

### Management Endpoints
```
GET /jobs                     # List all crawl jobs
DELETE /job/{job_id}          # Delete a specific job
GET /health                   # Health check
```

## 📊 **Schema Types Generated**

The crawler automatically detects and generates appropriate schemas:

- **WebPage** - Standard web pages
- **AboutPage** - About/company pages
- **ContactPage** - Contact information pages
- **FAQPage** - FAQ and Q&A content
- **Article** - Blog posts and articles
- **Service** - Service description pages
- **Product** - E-commerce product pages
- **Organization** - Company information
- **LocalBusiness** - Location-based businesses

## 🎛️ **Configuration Options**

### Crawl Settings
```json
{
  "url": "https://example.com",
  "max_pages": 20,
  "allow_backward": false
}
```

### Backend Configuration
```python
MAX_PAGES = 50                # Maximum pages per crawl
RATE_LIMIT_DELAY = 1.5       # Delay between requests (seconds)
CDN_BASE_URL = "https://..."  # Your CDN domain
```

## 🔍 **Smart Filtering**

### Allowed URLs
✅ Regular web pages (HTML)  
✅ LinkedIn company pages  
✅ Business directories  
✅ Same-domain pages (when allow_backward=False)  

### Blocked URLs
❌ Email links (mailto:)  
❌ Phone links (tel:)  
❌ File downloads (.pdf, .doc, .zip, etc.)  
❌ Social media personal profiles  
❌ JavaScript links  
❌ Fragment-only links (#section)  
❌ Google Maps and short URLs  

## 🚀 **Production Deployment**

### Environment Variables
```bash
GOOGLE_API_KEY=your-gemini-api-key
CDN_BASE_URL=https://your-domain.com/cdn
MAX_PAGES=100
RATE_LIMIT_DELAY=2.0
```

### Docker Deployment
```dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
RUN playwright install chromium

COPY . .
EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Nginx Configuration
```nginx
server {
    listen 80;
    server_name your-domain.com;
    
    location /api/ {
        proxy_pass http://localhost:8000/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
    
    location /cdn/ {
        proxy_pass http://localhost:8000/cdn/;
        add_header Access-Control-Allow-Origin *;
        add_header Cache-Control "public, max-age=3600";
    }
}
```

## 🧪 **Testing Your Integration**

### Verify Schema Loading
```javascript
// Listen for schema loading events
window.addEventListener('schemaLoaded', function(event) {
    console.log('Schema loaded:', event.detail);
});

// Check if schemas are available
if (window.SchemaLoader) {
    console.log('Available schemas:', window.SchemaLoader.getAvailableSchemas());
}
```

### Google Rich Results Test
1. Visit [Google Rich Results Test](https://search.google.com/test/rich-results)
2. Enter your website URL
3. Verify that structured data is detected

### JSON-LD Validation
```javascript
// Validate JSON-LD syntax
const scripts = document.querySelectorAll('script[type="application/ld+json"]');
scripts.forEach(script => {
    try {
        JSON.parse(script.textContent);
        console.log('✅ Valid JSON-LD');
    } catch (e) {
        console.error('❌ Invalid JSON-LD:', e);
    }
});
```

## 🎯 **Use Cases**

### E-commerce Websites
- Product schema generation
- Organization information
- Breadcrumb navigation
- Review and rating data

### Service Businesses
- LocalBusiness schema
- Service descriptions
- Contact information
- FAQ pages

### Content Websites
- Article schema for blog posts
- Author information
- Publication dates
- Content categorization

### Corporate Websites
- Organization schema
- About page optimization
- Team member information
- Company history and values

## 🔧 **Troubleshooting**

### Common Issues

**Schema Not Loading**
- Check console for JavaScript errors
- Verify CDN URL is accessible
- Ensure script tag is in `<head>` section

**Missing Page Schemas**
- Page might not have been crawled
- Check crawl logs for errors
- Verify URL filtering settings

**CDN Timeout**
- Check server status
- Verify network connectivity
- Try manual JSON file access

### Debug Mode
```javascript
// Enable debug mode
window.SchemaLoader.debug = true;

// Manual schema reload
window.SchemaLoader.reload();
```

## 📈 **Performance Optimization**

### Crawler Performance
- Adjust `RATE_LIMIT_DELAY` for faster crawling
- Use proxy rotation for large sites
- Implement caching for repeated crawls

### CDN Performance
- Enable gzip compression
- Set appropriate cache headers
- Use a proper CDN service (Cloudflare, AWS CloudFront)

### Browser Performance
- Use minified schema-loader.js
- Implement lazy loading for large schemas
- Cache schemas locally when possible

## 🤝 **Contributing**

We welcome contributions! Please see our [Contributing Guidelines](CONTRIBUTING.md) for details.

### Development Setup
```bash
# Frontend development
npm install
npm run dev

# Backend development with auto-reload
uvicorn main:app --reload

# Run tests
pytest tests/
```

## 📄 **License**

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 **Acknowledgments**

- Google Gemini AI for schema generation
- Playwright for reliable web scraping
- FastAPI for the robust backend framework
- The Schema.org community for structured data standards

---

**Happy Crawling! 🕷️✨**