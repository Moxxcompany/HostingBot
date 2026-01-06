"""
Supported TLD list for OpenProvider API validation
Prevents API calls with unsupported domain extensions
"""

import logging

logger = logging.getLogger(__name__)

# Comprehensive list of TLDs supported by OpenProvider
# This prevents API errors from invalid extensions like .sms
SUPPORTED_TLDS = {
    # Generic TLDs
    'com', 'net', 'org', 'info', 'biz', 'name', 'pro', 'mobi', 'tel', 'travel',
    'jobs', 'cat', 'asia', 'aero', 'coop', 'museum', 'post', 'xxx', 'edu',
    
    # New Generic TLDs (gTLDs)
    'app', 'blog', 'shop', 'store', 'online', 'site', 'website', 'tech', 'cloud',
    'digital', 'email', 'host', 'hosting', 'server', 'web', 'www', 'dev', 'ai',
    'io', 'co', 'me', 'tv', 'cc', 'tk', 'ml', 'ga', 'cf', 'top', 'click',
    'link', 'download', 'zip', 'review', 'group', 'team', 'company', 'business',
    'solutions', 'services', 'consulting', 'agency', 'marketing', 'media',
    'design', 'graphics', 'photo', 'photography', 'art', 'gallery', 'studio',
    'music', 'band', 'radio', 'tv', 'film', 'video', 'news', 'press',
    'magazine', 'blog', 'social', 'community', 'forum', 'chat', 'network',
    'live', 'stream', 'game', 'games', 'casino', 'bet', 'poker', 'sport',
    'sports', 'football', 'soccer', 'tennis', 'golf', 'fitness', 'gym',
    'health', 'medical', 'doctor', 'clinic', 'hospital', 'pharmacy', 'care',
    'dental', 'beauty', 'spa', 'wellness', 'yoga', 'diet', 'nutrition',
    'food', 'restaurant', 'cafe', 'bar', 'pub', 'wine', 'beer', 'pizza',
    'coffee', 'kitchen', 'recipes', 'cooking', 'chef', 'catering', 'delivery',
    'fashion', 'style', 'clothing', 'shoes', 'jewelry', 'watches', 'luxury',
    'boutique', 'shopping', 'sale', 'discount', 'deals', 'coupons', 'gift',
    'toys', 'kids', 'baby', 'family', 'wedding', 'love', 'dating', 'singles',
    'travel', 'hotel', 'vacation', 'holiday', 'flight', 'cruise', 'tour',
    'guide', 'city', 'country', 'world', 'global', 'international', 'local',
    'home', 'house', 'property', 'real', 'estate', 'rent', 'mortgage', 'loan',
    'bank', 'finance', 'money', 'credit', 'insurance', 'tax', 'accounting',
    'legal', 'law', 'lawyer', 'attorney', 'court', 'justice', 'government',
    'vote', 'election', 'democrat', 'republican', 'green', 'party', 'politics',
    'school', 'university', 'college', 'education', 'training', 'course',
    'degree', 'mba', 'phd', 'study', 'learn', 'teach', 'academic', 'science',
    'technology', 'software', 'hardware', 'computer', 'laptop', 'mobile',
    'phone', 'tablet', 'internet', 'wifi', 'data', 'cloud', 'security',
    'auto', 'car', 'cars', 'truck', 'bike', 'motorcycle', 'parts', 'repair',
    'garage', 'dealer', 'driving', 'taxi', 'uber', 'transport', 'logistics',
    'energy', 'solar', 'green', 'eco', 'organic', 'bio', 'nature', 'garden',
    'farm', 'agriculture', 'fishing', 'hunting', 'outdoor', 'camping', 'hiking',
    
    # Country Code TLDs (ccTLDs) - Major ones
    'us', 'uk', 'ca', 'au', 'de', 'fr', 'it', 'es', 'nl', 'be', 'ch', 'at',
    'se', 'no', 'dk', 'fi', 'is', 'ie', 'pt', 'gr', 'pl', 'cz', 'sk', 'hu',
    'ro', 'bg', 'hr', 'si', 'ee', 'lv', 'lt', 'mt', 'cy', 'lu', 'li', 'ad',
    'mc', 'sm', 'va', 'rs', 'ba', 'mk', 'al', 'me', 'md', 'ua', 'by', 'ru',
    'kz', 'kg', 'tj', 'tm', 'uz', 'mn', 'cn', 'jp', 'kr', 'tw', 'hk', 'mo',
    'sg', 'my', 'th', 'vn', 'ph', 'id', 'bn', 'in', 'pk', 'bd', 'lk', 'mv',
    'np', 'bt', 'mm', 'la', 'kh', 'af', 'ir', 'iq', 'sy', 'jo', 'lb', 'il',
    'ps', 'sa', 'ae', 'om', 'ye', 'kw', 'qa', 'bh', 'tr', 'am', 'az', 'ge',
    'eg', 'ly', 'tn', 'dz', 'ma', 'eh', 'sd', 'ss', 'et', 'er', 'dj', 'so',
    'ke', 'ug', 'tz', 'rw', 'bi', 'mw', 'zm', 'zw', 'bw', 'na', 'za', 'ls',
    'sz', 'mg', 'mu', 'sc', 'km', 're', 'yt', 'mz', 'ao', 'cd', 'cg', 'cf',
    'cm', 'eq', 'ga', 'st', 'td', 'ne', 'ng', 'bj', 'tg', 'gh', 'ci', 'lr',
    'sl', 'gn', 'gw', 'sn', 'gm', 'ml', 'bf', 'mr', 'cv', 'br', 'ar', 'cl',
    'pe', 'ec', 'co', 've', 'gy', 'sr', 'uy', 'py', 'bo', 'mx', 'gt', 'bz',
    'sv', 'hn', 'ni', 'cr', 'pa', 'cu', 'jm', 'ht', 'do', 'pr', 'vi', 'bb',
    'tt', 'gd', 'lc', 'vc', 'ag', 'dm', 'kn', 'bs', 'tc', 'vg', 'ai', 'ms',
    'ky', 'bm', 'gl', 'fo', 'sj', 'aq', 'fj', 'sb', 'vu', 'nc', 'pf', 'wf',
    'ws', 'as', 'gu', 'mp', 'pw', 'fm', 'mh', 'ki', 'nr', 'tv', 'to', 'nu',
    'ck', 'pn', 'tk', 'nz',
    
    # Special domains
    'int', 'arpa', 'onion', 'localhost', 'local', 'test', 'invalid', 'example',
    
    # Business/Industry specific
    'academy', 'accountant', 'accountants', 'actor', 'adult', 'africa', 'agency',
    'airforce', 'amsterdam', 'analytics', 'apartments', 'app', 'architect',
    'army', 'associates', 'attorney', 'auction', 'audio', 'auto', 'autos',
    'baby', 'band', 'bank', 'bar', 'barcelona', 'bargains', 'baseball',
    'basketball', 'beauty', 'beer', 'berlin', 'best', 'bet', 'bible', 'bid',
    'bike', 'bingo', 'bio', 'black', 'blackfriday', 'blog', 'blue', 'boats',
    'boston', 'boutique', 'box', 'broker', 'brussels', 'build', 'builders',
    'business', 'buy', 'buzz', 'cab', 'cafe', 'cam', 'camera', 'camp',
    'capital', 'car', 'cards', 'care', 'career', 'careers', 'cars', 'casa',
    'cash', 'casino', 'catering', 'center', 'ceo', 'charity', 'chat', 'cheap',
    'christmas', 'church', 'city', 'claims', 'cleaning', 'click', 'clinic',
    'clothing', 'cloud', 'club', 'coach', 'codes', 'coffee', 'college',
    'cologne', 'community', 'company', 'compare', 'computer', 'condos',
    'construction', 'consulting', 'contact', 'contractors', 'cooking', 'cool',
    'country', 'coupon', 'coupons', 'courses', 'credit', 'creditcard', 'cricket',
    'cruise', 'crypto', 'dance', 'data', 'date', 'dating', 'day', 'deal',
    'deals', 'degree', 'delivery', 'democrat', 'dental', 'dentist', 'design',
    'dev', 'diamond', 'diet', 'digital', 'direct', 'directory', 'discount',
    'doctor', 'dog', 'domains', 'download', 'drive', 'duck', 'earth', 'eat',
    'eco', 'education', 'email', 'energy', 'engineer', 'engineering', 'enterprises',
    'equipment', 'estate', 'eurovision', 'events', 'exchange', 'expert',
    'exposed', 'express', 'fail', 'faith', 'family', 'fan', 'fans', 'farm',
    'fashion', 'fast', 'feedback', 'film', 'finance', 'financial', 'fire',
    'fish', 'fishing', 'fit', 'fitness', 'flights', 'florist', 'flowers',
    'fly', 'foo', 'food', 'football', 'forex', 'forsale', 'forum', 'foundation',
    'free', 'fun', 'fund', 'furniture', 'futbol', 'fyi', 'gallery', 'game',
    'games', 'garden', 'gay', 'gift', 'gifts', 'gives', 'giving', 'glass',
    'global', 'gmbh', 'gold', 'golf', 'graphics', 'gratis', 'green', 'gripe',
    'grocery', 'group', 'guide', 'guitars', 'guru', 'hair', 'hamburg',
    'haus', 'health', 'healthcare', 'help', 'helsinki', 'here', 'hiphop',
    'hockey', 'holdings', 'holiday', 'home', 'horse', 'hospital', 'host',
    'hosting', 'hot', 'hotel', 'house', 'how', 'icu', 'immo', 'immobilien',
    'inc', 'industries', 'ink', 'institute', 'insurance', 'insure', 'international',
    'investments', 'irish', 'istanbul', 'jetzt', 'jewelry', 'juegos', 'kaufen',
    'kim', 'kitchen', 'kiwi', 'koeln', 'land', 'latino', 'law', 'lawyer',
    'lease', 'legal', 'lgbt', 'life', 'lifestyle', 'lighting', 'like', 'limited',
    'limo', 'live', 'living', 'loan', 'loans', 'local', 'lol', 'london',
    'love', 'ltd', 'ltda', 'luxury', 'macau', 'madrid', 'maison', 'make',
    'makeup', 'management', 'manager', 'market', 'marketing', 'markets',
    'mba', 'media', 'meet', 'meme', 'memorial', 'men', 'menu', 'miami',
    'mil', 'mini', 'mma', 'mobile', 'moda', 'moe', 'mom', 'money', 'monster',
    'mortgage', 'moscow', 'moto', 'motorcycles', 'mov', 'movie', 'music',
    'navy', 'network', 'new', 'news', 'ngo', 'ninja', 'now', 'nyc', 'okinawa',
    'one', 'ong', 'online', 'ooo', 'organic', 'osaka', 'page', 'paris',
    'partners', 'parts', 'party', 'pay', 'pccw', 'pet', 'pharmacy', 'phone',
    'photo', 'photography', 'photos', 'physio', 'pics', 'pictures', 'pink',
    'pizza', 'place', 'play', 'plumbing', 'plus', 'poker', 'porn', 'press',
    'productions', 'promo', 'properties', 'property', 'protection', 'pub',
    'qpon', 'quebec', 'racing', 'radio', 'realestate', 'realtor', 'realty',
    'recipes', 'red', 'rehab', 'reise', 'reisen', 'rent', 'rentals', 'repair',
    'report', 'republican', 'rest', 'restaurant', 'review', 'reviews', 'rich',
    'ride', 'ring', 'rip', 'rocks', 'rodeo', 'room', 'rugby', 'run', 'safe',
    'sale', 'salon', 'sarl', 'sbs', 'school', 'schule', 'science', 'scot',
    'search', 'secure', 'security', 'select', 'services', 'sex', 'sexy',
    'shiksha', 'shoes', 'shop', 'shopping', 'show', 'singles', 'site',
    'ski', 'skin', 'sky', 'soccer', 'social', 'software', 'solar',
    'solutions', 'soy', 'spa', 'space', 'sport', 'sports', 'spot', 'stream',
    'studio', 'study', 'style', 'sucks', 'supplies', 'supply', 'support',
    'surf', 'surgery', 'swiss', 'sydney', 'systems', 'taipei', 'talk',
    'tattoo', 'tax', 'taxi', 'team', 'tech', 'technology', 'tennis', 'theater',
    'theatre', 'tienda', 'tips', 'tires', 'today', 'tokyo', 'tools', 'top',
    'tours', 'town', 'toys', 'trade', 'trading', 'training', 'tube', 'tv',
    'uol', 'vacations', 'vegas', 'ventures', 'vet', 'viajes', 'video',
    'villas', 'vin', 'vip', 'vision', 'vodka', 'vote', 'voting', 'voyage',
    'wang', 'watch', 'watches', 'water', 'wave', 'waves', 'waw', 'webcam',
    'website', 'wedding', 'whoswho', 'wiki', 'win', 'wine', 'winners',
    'work', 'works', 'world', 'wow', 'wtf', 'xyz', 'yachts', 'yoga', 'yokohama',
    'zone', 'zuerich'
}

def is_supported_tld(domain_name: str) -> bool:
    """
    Check if a domain uses a supported TLD
    
    Args:
        domain_name: Domain name to check (e.g., "example.com")
        
    Returns:
        True if TLD is supported, False otherwise
    """
    if not domain_name or '.' not in domain_name:
        return False
    
    # Extract TLD (last part after the last dot)
    tld = domain_name.split('.')[-1].lower().strip()
    
    # Check against our supported TLD list
    is_supported = tld in SUPPORTED_TLDS
    
    if not is_supported:
        logger.warning(f"🚫 Unsupported TLD: .{tld} for domain {domain_name}")
    else:
        logger.debug(f"✅ Supported TLD: .{tld} for domain {domain_name}")
    
    return is_supported

def get_tld_from_domain(domain_name: str) -> str:
    """
    Extract TLD from domain name
    
    Args:
        domain_name: Domain name (e.g., "example.com")
        
    Returns:
        TLD without dot (e.g., "com")
    """
    if not domain_name or '.' not in domain_name:
        return ""
    
    return domain_name.split('.')[-1].lower().strip()

def get_supported_tlds_list() -> list:
    """
    Get list of all supported TLDs
    
    Returns:
        Sorted list of supported TLDs
    """
    return sorted(list(SUPPORTED_TLDS))

def get_unsupported_tld_message(domain_name: str) -> str:
    """
    Get user-friendly error message for unsupported TLD
    
    Args:
        domain_name: Domain name with unsupported TLD
        
    Returns:
        Error message string
    """
    tld = get_tld_from_domain(domain_name)
    
    if not tld:
        return f"Invalid domain format: {domain_name}"
    
    # Suggest similar supported TLDs
    common_suggestions = ['com', 'net', 'org', 'io', 'co', 'app', 'dev']
    available_suggestions = [f".{tld}" for tld in common_suggestions if tld in SUPPORTED_TLDS]
    
    suggestions_text = f"\n\nTry these popular extensions:\n{', '.join(available_suggestions)}" if available_suggestions else ""
    
    return f"❌ Unsupported Extension: .{tld}\n\nThe .{tld} extension is not available for registration.{suggestions_text}"