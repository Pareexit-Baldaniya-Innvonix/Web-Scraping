from typing import Dict, Tuple

SELECTORS: Dict[str, Tuple[str, dict]] = {
    # ----- product title -----
    "title": ("span", {"id": "productTitle"}),
    
    # ----- price -----
    "price_whole": ("span", {"class": "a-price-whole"}),
    "price_fraction": ("span", {"class": "a-price-fraction"}),
    "price_symbol": ("span", {"class": "a-price-symbol"}),
    
    # ----- ratings -----
    "ratings_alt": ("span", {"class": "a-icon-alt"}),
    "ratings_popover": ("span", {"id": "acrPopover"}),
    
    # ----- reviews -----
    "reviews_text": ("span", {"id": "acrCustomerReviewText"}),
    
    # ----- description -----
    "product_description": ("div", {"id": "productDescription"}),
    
    # ----- feature bullets -----
    "feature_bullets": ("div", {"id": "feature-bullets"}),
    
    # ----- variants container -----
    "variants_container": ("div", {"id": "twister_feature_div"}),
}
