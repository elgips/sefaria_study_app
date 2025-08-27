import json
import sys
import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

def create_session():
    session = requests.Session()
    retries = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    session.mount("https://", HTTPAdapter(max_retries=retries))
    return session

def fetch_sefaria_data(title):
    print(f"Starting to fetch data for {title}...")
    progress = 0
    session = create_session()

    # Fetch index data
    print("Phase 1/2: Fetching index data...")
    start_time = time.time()
    index_url = f"https://www.sefaria.org/api/v2/raw/index/{title}"
    try:
        index_response = session.get(index_url, headers={"accept": "application/json"}, timeout=10)
        index_response.raise_for_status()
        index_data = index_response.json()
        print(f"Index data: {len(index_data.get('schema', {}).get('sectionNames', []))} sections found")
    except requests.exceptions.RequestException as e:
        print(f"Warning: Failed to fetch index data: {e}")
        index_data = {}
    progress += 50
    print(f"Progress: {progress}% - Index data fetched in {time.time() - start_time:.2f} seconds.")

    # Fetch texts data (versions)
    print("Phase 2/2: Fetching texts data...")
    start_time = time.time()
    texts_url = f"https://www.sefaria.org/api/v3/texts/{title}"
    try:
        texts_response = session.get(texts_url, headers={"accept": "application/json"}, timeout=10)
        texts_response.raise_for_status()
        texts_data = texts_response.json()
        print(f"Texts data: {len(texts_data.get('versions', []))} versions found")
    except requests.exceptions.RequestException as e:
        print(f"Warning: Failed to fetch texts data: {e}")
        texts_data = {}
    progress += 50
    print(f"Progress: {progress}% - Texts data fetched in {time.time() - start_time:.2f} seconds.")

    return index_data, texts_data

def build_shadow_trees(index_file, target_title):
    print(f"Building shadow trees for {target_title}...")
    start_time = time.time()
    shadow_trees = {}
    
    with open(index_file, "r", encoding="utf-8") as f:
        index_data = json.load(f)
    
    def search_contents(contents, current_path, target_title):
        for item in contents:
            categories = item.get("categories", [])
            dependence = item.get("dependence", "")
            base_text_titles = item.get("base_text_titles", [])
            he_title = item.get("heTitle", "")
            en_title = item.get("title", "")
            en_short_desc = item.get("enShortDesc", "").lower()
            
            # Skip modern commentaries
            if any(keyword in en_short_desc for keyword in ["modern", "contemporary", "21st-century", "20th-century"]):
                continue
            
            # Check if relevant to target_title
            is_specific = target_title in base_text_titles and len(base_text_titles) == 1
            is_category_specific = any(f"{target_title}" in cat for cat in categories)
            
            if ("Commentary" in categories or dependence == "Commentary" or "Targum" in categories) and (is_specific or is_category_specific):
                commentator_name = he_title or en_title
                if not commentator_name:
                    continue
                
                # Initialize commentator's tree
                if commentator_name not in shadow_trees:
                    shadow_trees[commentator_name] = {}
                
                # Build path for the current item
                item_path = current_path + [en_title or he_title]
                path_key = ".".join(item_path)
                
                # Add to shadow tree
                current_node = shadow_trees[commentator_name]
                for segment in item_path:
                    if segment not in current_node:
                        current_node[segment] = {}
                    current_node = current_node[segment]
                
                current_node["title"] = en_title or he_title
                current_node["path"] = item_path
                current_node["type"] = "Targum" if "Targum" in categories else "Commentary"
            
            # Recursively search nested contents
            if "contents" in item:
                search_contents(item["contents"], current_path + [en_title or he_title], target_title)
    
    search_contents(index_data, [], target_title)
    print(f"Built shadow trees with {len(shadow_trees)} commentators/targums in {time.time() - start_time:.2f} seconds")
    return shadow_trees

def search_shadow_trees(shadow_trees, search_path):
    print(f"Searching shadow trees for path: {search_path}...")
    results = []
    path_key = ".".join(search_path)
    
    for commentator, tree in shadow_trees.items():
        current_node = tree
        found = True
        for segment in search_path:
            if segment not in current_node:
                found = False
                break
            current_node = current_node[segment]
        
        if found and "title" in current_node:
            results.append({
                "מפרש_או_תרגום": commentator,
                "כותר": current_node["title"],
                "סוג": current_node["type"],
                "מסלול": current_node["path"]
            })
    
    print(f"Found {len(results)} matches for path {search_path}")
    return results

def extract_hebrew_data(index_data, texts_data, shadow_trees, title):
    print("Processing data...")
    result = {
        "חלוקות": {
            "פרקים_ופסוקים": {},
            "חלוקות_זמינות": f"פרשיות ועליות זמינות לחיפוש דרך https://www.sefaria.org/api/shape/{title}"
        },
        "גרסאות": [],
        "עצי_צל": shadow_trees
    }
    progress = 0

    # Extract divisions
    print("Phase 1/3: Extracting divisions...")
    if index_data.get("schema"):
        schema = index_data["schema"]
        result["חלוקות"]["פרקים_ופסוקים"] = {
            "שמות_חלקים": schema.get("sectionNames", []),
            "עומקים": schema.get("lengths", []),
            "כותרות_חלופיות": schema.get("heSectionNames", ["פרק", "פסוק"])
        }
    print(f"Extracted divisions for {len(result['חלוקות']['פרקים_ופסוקים'].get('עומקים', []))} levels")
    progress += 33
    print(f"Progress: {progress}% - Divisions extracted.")

    # Extract Hebrew versions
    print("Phase 2/3: Extracting Hebrew versions...")
    hebrew_version_titles = [
        "מקרא על פי המסורה", "תנ\"ך עם ניקוד", "תנ\"ך ללא טעמים", "מקרא מבואר"
    ]
    if texts_data.get("versions"):
        seen_versions = set()
        for version in texts_data["versions"]:
            version_title = version.get("versionTitle")
            if (version.get("language") == "he" or version_title in hebrew_version_titles) and version_title and version_title not in seen_versions:
                result["גרסאות"].append({
                    "שם_גרסה": version_title,
                    "מקור": version.get("versionSource", ""),
                    "סטטוס": version.get("status", "")
                })
                seen_versions.add(version_title)
    print(f"Extracted {len(result['גרסאות'])} Hebrew versions")
    progress += 33
    print(f"Progress: {progress}% - Hebrew versions extracted.")

    # Add shadow trees
    print("Phase 3/3: Adding shadow trees...")
    progress += 34
    print(f"Progress: {progress}% - Shadow trees added.")

    return result

def main():
    if len(sys.argv) < 3:
        print("Usage: python script.py <title> <index_file> (e.g., Genesis download.json)")
        sys.exit(1)
    
    start_time = time.time()
    print("Starting script execution...")
    
    title = sys.argv[1]
    index_file = sys.argv[2]
    try:
        index_data, texts_data = fetch_sefaria_data(title)
        shadow_trees = build_shadow_trees(index_file, title)
        hebrew_data = extract_hebrew_data(index_data, texts_data, shadow_trees, title)
        
        # Example search
        example_search_path = ["Tanakh", "Torah", title]
        search_results = search_shadow_trees(shadow_trees, example_search_path)
        print("Example search results:", json.dumps(search_results, ensure_ascii=False, indent=4))
        
        print("Saving data to JSON file...")
        output_file = f"{title}_hebrew_info.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(hebrew_data, f, ensure_ascii=False, indent=4)
        
        execution_time = time.time() - start_time
        print(f"Data saved to {output_file}")
        print(f"Execution time: {execution_time:.2f} seconds")
        
    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    main()