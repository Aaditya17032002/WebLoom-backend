import os
import json
import shutil
from pathlib import Path
from datetime import datetime

def create_schema_repository(crawl_job_id: str, website_domain: str):
    """
    Create a repository structure for JSON-LD schema files
    """
    # Create repository directory
    repo_dir = Path("schema_repo")
    repo_dir.mkdir(exist_ok=True)
    
    # Create website directory
    clean_domain = website_domain.replace('.', '_').replace(':', '_')
    website_dir = repo_dir / clean_domain
    website_dir.mkdir(exist_ok=True)
    
    # Copy JSON files from crawler_data
    source_dir = Path("crawler_data") / f"{clean_domain}_{crawl_job_id}"
    if not source_dir.exists():
        raise FileNotFoundError(f"Source directory not found: {source_dir}")
    
    # Create README.md
    readme_content = f"""# JSON-LD Schema Repository for {website_domain}

This repository contains JSON-LD schema files for {website_domain}.

## Usage

### CDN.js Integration

Add the following script tag to your website:

```html
<script src="https://cdn.jsdelivr.net/gh/Aaditya17032002/webloom@main/schema_repo/{clean_domain}/schema-loader.js"></script>
```

### Manual Integration

1. Download the JSON files from this repository
2. Host them on your server
3. Include the schema-loader.js file in your website

## Files

- `schema-loader.js`: Main loader script
- `schema-loader.min.js`: Minified version of the loader
- `index.json`: Index of all available schemas
- Individual JSON files for each page

## Last Updated

{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
    
    with open(website_dir / "README.md", "w", encoding="utf-8") as f:
        f.write(readme_content)
    
    # Copy all JSON files
    for file in source_dir.glob("*.json"):
        shutil.copy2(file, website_dir)
    
    # Copy schema loader scripts
    for file in source_dir.glob("schema-loader*.js"):
        shutil.copy2(file, website_dir)
    
    # Create .gitignore
    gitignore_content = """# System files
.DS_Store
Thumbs.db

# IDE files
.idea/
.vscode/
*.swp
*.swo

# Logs
*.log
"""
    
    with open(repo_dir / ".gitignore", "w", encoding="utf-8") as f:
        f.write(gitignore_content)
    
    # Create main README.md
    main_readme = """# WebLoom JSON-LD Schema Repository

This repository contains JSON-LD schema files for various websites crawled using WebLoom.

## Usage

Each website has its own directory containing:
- JSON-LD schema files
- Schema loader script
- README with integration instructions

## CDN Integration

All files are available through CDN.js:

```
https://cdn.jsdelivr.net/gh/Aaditya17032002/webloom@main/schema_repo/[website]/[file]
```

## Contributing

This repository is automatically updated by the WebLoom crawler. Please do not make manual changes.
"""
    
    with open(repo_dir / "README.md", "w", encoding="utf-8") as f:
        f.write(main_readme)
    
    print(f"Repository structure created at: {repo_dir}")
    print(f"Website files created at: {website_dir}")
    print("\nNext steps:")
    print("1. Initialize git repository:")
    print(f"   cd {repo_dir}")
    print("   git init")
    print("   git add .")
    print('   git commit -m "Initial commit"')
    print("2. Add remote repository:")
    print("   git remote add origin https://github.com/Aaditya17032002/webloom.git")
    print("3. Push to GitHub:")
    print("   git push -u origin main")

if __name__ == "__main__":
    # Example usage
    job_id = input("Enter crawl job ID: ")
    domain = input("Enter website domain: ")
    create_schema_repository(job_id, domain) 