import requests
import json
import sys

def fetch_sefaria_data(title):
    # Fetch index data
    index_url = f"https://www.sefaria.org/api/v2/raw/index/{title}"
    index_response = requests.get(index_url)
    if index_response.status_code != 200:
        raise ValueError(f"Failed to fetch index for {title}: {index_response.text}")
    index_data = index_response.json()

    # Fetch texts data
    texts_url = f"https://www.sefaria.org/api/v3/texts/{title}"
    texts_response = requests.get(texts_url)
    if texts_response.status_code != 200:
        raise ValueError(f"Failed to fetch texts for {title}: {texts_response.text}")
    texts_data = texts_response.json()

    return index_data, texts_data

def extract_hebrew_only(index_data, texts_data):
    result = {
        "חלוקות": {},
        "מפרשים": [],
        "גרסאות": []
    }

    # Extract divisions (חלוקות) from index schema
    if "schema" in index_data:
        schema = index_data["schema"]
        result["חלוקות"]["שמות_חלקים"] = schema.get("sectionNames", [])
        result["חלוקות"]["עומקים"] = schema.get("lengths", [])
        result["חלוקות"]["כותרות_חלופיות"] = schema.get("heSectionNames", [])

    # Extract Hebrew versions (גרסאות)
    if "versions" in texts_data:
        for version in texts_data["versions"]:
            if version.get("language") == "he":
                result["גרסאות"].append({
                    "שם_גרסה": version.get("versionTitle"),
                    "מקור": version.get("versionSource"),
                    "סטטוס": version.get("status")
                })

    # Extract commentators (מפרשים) - look for dependence: Commentary
    if "dependence" in index_data and index_data["dependence"] == "Commentary":
        result["מפרשים"].append(index_data.get("collectiveTitle", "לא ידוע"))
    elif "commentary" in index_data:
        for comm in index_data["commentary"]:
            if comm.get("language") == "he" or "he" in comm.get("categories", []):
                result["מפרשים"].append(comm.get("collectiveTitle", comm.get("title")))

    # Additional Hebrew-specific from texts
    if "heVersions" in texts_data:
        for hv in texts_data["heVersions"]:
            result["גרסאות"].append({
                "שם_גרסה": hv.get("versionTitle"),
                "מקור": hv.get("versionSource")
            })

    return result

def main():
    if len(sys.argv) < 2:
        print("Usage: python script.py <title> (e.g., Genesis)")
        sys.exit(1)
    
    title = sys.argv[1]
    try:
        index_data, texts_data = fetch_sefaria_data(title)
        hebrew_data = extract_hebrew_only(index_data, texts_data)
        
        # Output to file
        output_file = f"{title}_hebrew_info.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(hebrew_data, f, ensure_ascii=False, indent=4)
        
        print(f"Data saved to {output_file}")
    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    main()