"""
NEXA Smart Actions v2.0
Intelligent command interpreter for complex, multi-step tasks.

Handles:
 - Web searches across services (Google, YouTube, Spotify, Amazon, etc.)
 - Opening specific content on platforms (play song, watch video, read article)
 - Multi-step workflows (open app + perform action)
 - System automation chains
 - Smart file operations with context
"""

import os
import platform
import subprocess
import shutil
import webbrowser
import urllib.parse

SYSTEM = platform.system()

# ======================================================================
# WEB SERVICE URL TEMPLATES
# ======================================================================
# Each service maps to a URL pattern.  {q} is replaced with the
# URL-encoded query string.

WEB_SERVICES = {
    # Search engines
    "google":       "https://www.google.com/search?q={q}",
    "bing":         "https://www.bing.com/search?q={q}",
    "duckduckgo":   "https://duckduckgo.com/?q={q}",
    "ddg":          "https://duckduckgo.com/?q={q}",
    "brave":        "https://search.brave.com/search?q={q}",

    # Video
    "youtube":      "https://www.youtube.com/results?search_query={q}",
    "yt":           "https://www.youtube.com/results?search_query={q}",
    "twitch":       "https://www.twitch.tv/search?term={q}",
    "vimeo":        "https://vimeo.com/search?q={q}",
    "dailymotion":  "https://www.dailymotion.com/search/{q}",

    # Music / Audio
    "spotify":      "https://open.spotify.com/search/{q}",
    "soundcloud":   "https://soundcloud.com/search?q={q}",
    "apple music":  "https://music.apple.com/search?term={q}",
    "applemusic":   "https://music.apple.com/search?term={q}",
    "deezer":       "https://www.deezer.com/search/{q}",
    "tidal":        "https://listen.tidal.com/search?q={q}",
    "pandora":      "https://www.pandora.com/search/{q}",

    # Shopping
    "amazon":       "https://www.amazon.com/s?k={q}",
    "ebay":         "https://www.ebay.com/sch/i.html?_nkw={q}",
    "aliexpress":   "https://www.aliexpress.com/wholesale?SearchText={q}",
    "walmart":      "https://www.walmart.com/search?q={q}",
    "etsy":         "https://www.etsy.com/search?q={q}",
    "target":       "https://www.target.com/s?searchTerm={q}",
    "bestbuy":      "https://www.bestbuy.com/site/searchpage.jsp?st={q}",

    # Social
    "twitter":      "https://twitter.com/search?q={q}",
    "x":            "https://x.com/search?q={q}",
    "reddit":       "https://www.reddit.com/search/?q={q}",
    "instagram":    "https://www.instagram.com/explore/tags/{q}/",
    "tiktok":       "https://www.tiktok.com/search?q={q}",
    "facebook":     "https://www.facebook.com/search/top/?q={q}",
    "linkedin":     "https://www.linkedin.com/search/results/all/?keywords={q}",
    "pinterest":    "https://www.pinterest.com/search/pins/?q={q}",
    "threads":      "https://www.threads.net/search?q={q}",

    # Knowledge / Reference
    "wikipedia":    "https://en.wikipedia.org/wiki/Special:Search?search={q}",
    "wiki":         "https://en.wikipedia.org/wiki/Special:Search?search={q}",
    "stackoverflow":"https://stackoverflow.com/search?q={q}",
    "so":           "https://stackoverflow.com/search?q={q}",
    "quora":        "https://www.quora.com/search?q={q}",
    "wolfram":      "https://www.wolframalpha.com/input?i={q}",
    "arxiv":        "https://arxiv.org/search/?query={q}",

    # Dev / Code
    "github":       "https://github.com/search?q={q}",
    "gh":           "https://github.com/search?q={q}",
    "gitlab":       "https://gitlab.com/search?search={q}",
    "npm":          "https://www.npmjs.com/search?q={q}",
    "pypi":         "https://pypi.org/search/?q={q}",
    "dockerhub":    "https://hub.docker.com/search?q={q}",
    "crates":       "https://crates.io/search?q={q}",
    "mdn":          "https://developer.mozilla.org/en-US/search?q={q}",

    # Maps / Travel
    "maps":         "https://www.google.com/maps/search/{q}",
    "google maps":  "https://www.google.com/maps/search/{q}",
    "gmaps":        "https://www.google.com/maps/search/{q}",
    "openstreetmap":"https://www.openstreetmap.org/search?query={q}",
    "osm":          "https://www.openstreetmap.org/search?query={q}",
    "flights":      "https://www.google.com/travel/flights?q={q}",
    "booking":      "https://www.booking.com/searchresults.html?ss={q}",
    "airbnb":       "https://www.airbnb.com/s/{q}/homes",

    # News
    "news":         "https://news.google.com/search?q={q}",
    "google news":  "https://news.google.com/search?q={q}",
    "bbc":          "https://www.bbc.co.uk/search?q={q}",
    "cnn":          "https://www.cnn.com/search?q={q}",

    # Images
    "images":       "https://www.google.com/search?tbm=isch&q={q}",
    "google images":"https://www.google.com/search?tbm=isch&q={q}",
    "unsplash":     "https://unsplash.com/s/photos/{q}",
    "pexels":       "https://www.pexels.com/search/{q}/",
    "giphy":        "https://giphy.com/search/{q}",

    # AI
    "chatgpt":      "https://chatgpt.com/?q={q}",
    "perplexity":   "https://www.perplexity.ai/search?q={q}",
    "claude":       "https://claude.ai/new",
    "gemini":       "https://gemini.google.com/app",

    # Translation
    "translate":    "https://translate.google.com/?sl=auto&tl=en&text={q}",
    "deepl":        "https://www.deepl.com/translator#auto/en/{q}",
}

# Direct URL patterns for specific content (not searches)
DIRECT_URLS = {
    "gmail":        "https://mail.google.com",
    "google mail":  "https://mail.google.com",
    "google drive": "https://drive.google.com",
    "gdrive":       "https://drive.google.com",
    "google docs":  "https://docs.google.com",
    "google sheets":"https://sheets.google.com",
    "google calendar": "https://calendar.google.com",
    "gcal":         "https://calendar.google.com",
    "google meet":  "https://meet.google.com",
    "outlook":      "https://outlook.live.com",
    "onedrive":     "https://onedrive.live.com",
    "dropbox":      "https://www.dropbox.com/home",
    "notion":       "https://www.notion.so",
    "slack":        "https://app.slack.com",
    "discord":      "https://discord.com/app",
    "teams":        "https://teams.microsoft.com",
    "zoom":         "https://zoom.us/join",
    "whatsapp":     "https://web.whatsapp.com",
    "telegram":     "https://web.telegram.org",
    "netflix":      "https://www.netflix.com",
    "hulu":         "https://www.hulu.com",
    "disney+":      "https://www.disneyplus.com",
    "disneyplus":   "https://www.disneyplus.com",
    "prime video":  "https://www.primevideo.com",
    "primevideo":   "https://www.primevideo.com",
    "hbo":          "https://www.max.com",
    "hbo max":      "https://www.max.com",
    "twitch":       "https://www.twitch.tv",
    "github":       "https://github.com",
    "gitlab":       "https://gitlab.com",
    "stackoverflow":"https://stackoverflow.com",
    "reddit":       "https://www.reddit.com",
    "twitter":      "https://twitter.com",
    "x":            "https://x.com",
    "instagram":    "https://www.instagram.com",
    "facebook":     "https://www.facebook.com",
    "linkedin":     "https://www.linkedin.com",
    "pinterest":    "https://www.pinterest.com",
    "tiktok":       "https://www.tiktok.com",
}


def _open_url(url: str) -> str:
    """Open a URL in the default browser, cross-platform."""
    try:
        webbrowser.open(url)
        return f"Opened: {url}"
    except Exception as e:
        return f"Error opening URL: {e}"


def web_search(service: str, query: str) -> str:
    """Search a specific web service with the given query.

    Args:
        service: Service name (google, youtube, spotify, amazon, etc.)
        query: The search query text

    Returns:
        Status message
    """
    service_lower = service.lower().strip()
    query_encoded = urllib.parse.quote_plus(query)

    # Check if it's a known service
    url_template = WEB_SERVICES.get(service_lower)
    if url_template:
        url = url_template.replace("{q}", query_encoded)
        return _open_url(url)

    # Fuzzy match: try partial match
    for key, tmpl in WEB_SERVICES.items():
        if key in service_lower or service_lower in key:
            url = tmpl.replace("{q}", query_encoded)
            return _open_url(url)

    # Unknown service — fall back to Google with "site:" prefix
    url = f"https://www.google.com/search?q=site:{service_lower}+{query_encoded}"
    return _open_url(url)


def open_website(site: str) -> str:
    """Open a website/service directly (no search query).

    Args:
        site: Service name (gmail, discord, netflix, etc.) or a URL

    Returns:
        Status message
    """
    site_lower = site.lower().strip()

    # Direct URL?
    if site_lower.startswith(("http://", "https://", "www.")):
        url = site if "://" in site else f"https://{site}"
        return _open_url(url)

    # Known direct URL?
    url = DIRECT_URLS.get(site_lower)
    if url:
        return _open_url(url)

    # Fuzzy match direct URLs
    for key, u in DIRECT_URLS.items():
        if key in site_lower or site_lower in key:
            return _open_url(u)

    # Guess: prepend https://www. and .com
    clean = site_lower.replace(" ", "")
    url = f"https://www.{clean}.com"
    return _open_url(url)


def multi_search(queries: list) -> str:
    """Execute multiple searches in parallel (opens multiple tabs).

    Args:
        queries: List of dicts with 'service' and 'query' keys

    Returns:
        Combined status message
    """
    results = []
    for item in queries:
        svc = item.get("service", "google")
        q = item.get("query", "")
        if q:
            results.append(web_search(svc, q))
    return " | ".join(results) if results else "No valid queries provided"


def smart_open(target: str) -> str:
    """Intelligently open a target — could be a URL, website name, or app.

    Args:
        target: URL, website name, app name, or file path

    Returns:
        Status message
    """
    target = target.strip()

    # URL
    if target.startswith(("http://", "https://", "ftp://")):
        return _open_url(target)

    # Email address
    if "@" in target and "." in target:
        return _open_url(f"mailto:{target}")

    # Known website
    target_lower = target.lower()
    if target_lower in DIRECT_URLS:
        return _open_url(DIRECT_URLS[target_lower])

    # File path
    expanded = os.path.expanduser(os.path.expandvars(target))
    if os.path.exists(expanded):
        if SYSTEM == "Windows":
            os.startfile(expanded)
        elif SYSTEM == "Darwin":
            subprocess.Popen(["open", expanded])
        else:
            subprocess.Popen(["xdg-open", expanded])
        return f"Opened: {expanded}"

    # Assume it's a website name
    return open_website(target)


def download_url(url: str, save_path: str = "") -> str:
    """Download a file from a URL.

    Args:
        url: The URL to download from
        save_path: Where to save (default: ~/Downloads/<filename>)

    Returns:
        Status message with file path
    """
    try:
        import urllib.request

        if not save_path:
            filename = url.split("/")[-1].split("?")[0] or "download"
            downloads = os.path.join(os.path.expanduser("~"), "Downloads")
            os.makedirs(downloads, exist_ok=True)
            save_path = os.path.join(downloads, filename)

        save_path = os.path.expanduser(os.path.expandvars(save_path))
        urllib.request.urlretrieve(url, save_path)
        return f"Downloaded to: {save_path}"
    except Exception as e:
        return f"Download failed: {e}"


def web_scrape_text(url: str) -> str:
    """Fetch the text content of a web page (lightweight, no browser).

    Args:
        url: The URL to fetch

    Returns:
        Plain text content (truncated to 2000 chars)
    """
    try:
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": "NEXA/2.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="replace")

        # Strip HTML tags (simple approach)
        import re
        text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) > 2000:
            text = text[:2000] + "..."
        return text or "No readable content found"
    except Exception as e:
        return f"Fetch failed: {e}"


def chain_actions(steps: list) -> str:
    """Execute a sequence of actions in order.

    Each step is a dict that will be dispatched. Steps are executed
    sequentially; if one fails, the chain continues but notes the error.

    Args:
        steps: List of command dicts (each with module/action/parameters)

    Returns:
        Combined results
    """
    # Import dispatch here to avoid circular import
    from nexa_dispatcher import dispatch

    results = []
    for i, step in enumerate(steps, 1):
        try:
            result = dispatch(step)
            results.append(f"Step {i}: {result}")
        except Exception as e:
            results.append(f"Step {i} FAILED: {e}")
    return "\n".join(results)


def list_web_services() -> list:
    """Return all available web services for search."""
    return sorted(set(WEB_SERVICES.keys()))


def list_direct_sites() -> list:
    """Return all known websites that can be opened directly."""
    return sorted(set(DIRECT_URLS.keys()))
