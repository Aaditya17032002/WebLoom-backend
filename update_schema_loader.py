import json
from pathlib import Path

def update_schema_loader(website_dir: Path, domain: str):
    """
    Update schema loader script to use CDN.js
    """
    loader_path = website_dir / "schema-loader.js"
    if not loader_path.exists():
        raise FileNotFoundError(f"Schema loader not found: {loader_path}")
    
    # Read the current loader
    with open(loader_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Update CDN base URL
    cdn_base_url = f"https://cdn.jsdelivr.net/gh/Aaditya17032002/webloom@main/schema_repo/{domain}"
    content = content.replace(
        "const SCHEMA_BASE_URL = 'http://localhost:8000/cdn/",
        f"const SCHEMA_BASE_URL = '{cdn_base_url}/"
    )
    
    # Write updated loader
    with open(loader_path, "w", encoding="utf-8") as f:
        f.write(content)
    
    # Also update minified version
    min_path = website_dir / "schema-loader.min.js"
    if min_path.exists():
        with open(min_path, "r", encoding="utf-8") as f:
            min_content = f.read()
        
        min_content = min_content.replace(
            "SCHEMA_BASE_URL='http://localhost:8000/cdn/",
            f"SCHEMA_BASE_URL='{cdn_base_url}/"
        )
        
        with open(min_path, "w", encoding="utf-8") as f:
            f.write(min_content)
    
    print(f"Updated schema loader for {domain}")
    print(f"CDN base URL: {cdn_base_url}")

if __name__ == "__main__":
    # Example usage
    domain = input("Enter website domain (e.g., example_com): ")
    website_dir = Path("schema_repo") / domain
    update_schema_loader(website_dir, domain) 