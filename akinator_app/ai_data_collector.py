import requests
from bs4 import BeautifulSoup
from SPARQLWrapper import SPARQLWrapper, JSON

def get_wikipedia_summary(name):
    """
    Fetch a short summary from Wikipedia for the given character name.
    Tries multiple approaches for robustness.
    """
    headers = {"User-Agent": "Mozilla/5.0 (compatible; AkinatorBot/1.0; +https://example.com/bot)"}
    api_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{name.replace(' ', '_')}"
    response = requests.get(api_url, headers=headers)

    if response.status_code == 200:
        data = response.json()
        return data.get("extract")  # official Wikipedia summary

    # fallback to scraping
    url = f"https://en.wikipedia.org/wiki/{name.replace(' ', '_')}"
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        return None
    
    soup = BeautifulSoup(response.text, "html.parser")
    paragraphs = soup.find_all("p", recursive=True)
    for p in paragraphs:
        text = p.get_text().strip()
        if len(text) > 60 and "may refer to" not in text:
            return text
    return None




def get_wikidata_info(name):
    """
    Use Wikidata to find structured information (like occupation, gender, etc.)
    """
    endpoint_url = "https://query.wikidata.org/sparql"
    query = f"""
    SELECT ?item ?itemLabel ?genderLabel ?occupationLabel WHERE {{
      ?item ?label "{name}"@en;
            wdt:P21 ?gender;
            wdt:P106 ?occupation.
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }} LIMIT 1
    """

    sparql = SPARQLWrapper(endpoint_url)
    sparql.setQuery(query)
    sparql.setReturnFormat(JSON)
    results = sparql.query().convert()

    if results["results"]["bindings"]:
        info = results["results"]["bindings"][0]
        return {
            "gender": info.get("genderLabel", {}).get("value", "Unknown"),
            "occupation": info.get("occupationLabel", {}).get("value", "Unknown")
        }
    return None


def get_character_info(name):
    """
    Combine data from Wikipedia and Wikidata.
    """
    wiki_summary = get_wikipedia_summary(name)
    wikidata_info = get_wikidata_info(name)
    
    return {
        "name": name,
        "summary": wiki_summary,
        "details": wikidata_info
    }


if __name__ == "__main__":
    # Test it manually first
    data = get_character_info("Elon Musk")
    print(data)
