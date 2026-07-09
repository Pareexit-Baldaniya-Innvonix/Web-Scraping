SELECTORS = {
    # ----- product title -----
    "title": ("div", {"id": "title_feature_div"}),
    
    # ----- image -----
    "images": ("div", {"id": "altImages"}),
    
    # ----- price -----
    "price_whole": ("span", {"class": "a-price-whole"}),
    "price_fraction": ("span", {"class": "a-price-fraction"}),
    "price_offscreen": ("span", {"class": "a-price a-offscreen"}),
    
    # ----- ratings -----
    "ratings_alt": ("span", {"class": "a-icon-alt"}),
    "ratings_popover": ("span", {"id": "acrPopover"}),
    
    # ----- reviews -----
    "reviews_text": ("span", {"id": "acrCustomerReviewText"}),
    "review_container": ("div", {"data-hook": "review"}),
    "reviewer": ("span", {"class": "a-profile-name"}),
    "review_rating": ("i", {"data-hook": "review-star-rating"}),
    "review_title": ("h5", {"data-hook": "reviewTitle"}),
    "review_date": ("span", {"data-hook": "review-date"}),
    "review_body": ("div", {"data-hook": "reviewRichContentContainer"}),
    "review_helpful": ("span", {"data-hook": "helpful-vote-statement"}),
    
    # ----- description -----
    "product_description": ("div", {"id": "productDescription"}),
    
    # ----- feature bullets -----
    "feature_bullets": ("div", {"id": "feature-bullets"}),
    
    # ----- variants container -----
    "variants_container": ("div", {"id": "twister_feature_div"}),
    
    # ----- email -----
    "email": ("input", {"id": "ap_email_login"}),

    # ----- continue -----
    "continue": ("span", {"id": "continue"}),

    # ----- password -----
    "password": ("input", {"id": "ap_password"}),

    # ----- login -----
    "login": ("input", {"id": "signInSubmit"}),

    # ----- otp / mfa -----
    "otp_input": ("input", {"id": "auth-mfa-otpcode"}),
    "otp_submit": ("input", {"id": "auth-signin-button"}),
}

# ----- css selectors for otp -----
OTP_INPUT_FALLBACKS = [
    "input#auth-mfa-otpcode",
    "input#cvf-input-code",
    "input[name='otpCode']",
    "input[name='code']",
    "input[name='otc']",
    "input[autocomplete='one-time-code']",
    "input[type='tel']",
]
OTP_SUBMIT_FALLBACKS = [
    "input#auth-signin-button",
    "input#cvf-submit-otp-button",
    "#auth-mfa-otpcode-form input[type='submit']",
    "#cvf-page-content input[type='submit']",
    "button[type='submit']",
]

# ----- otp buttons -----
OTP_SEND_BUTTON_FALLBACKS = [
    "input#cvf-widget-btn-verify-otp-button",
    "input#cvf-widget-btn-send-otp-button",
    "button#cvf-widget-btn-send-otp-button",
    "#cvf-page-content input[type='submit']",
    "#cvf-page-content button[type='submit']",
    "input[aria-labelledby*='send-otp']",
]

# ----- css selectors for next page button -----
NEXT_PAGE_SELECTORS = [
    "li.a-last a",
    "ul.a-pagination li.a-last a",
    "a.s-pagination-next",
    "[data-hook='show-more-button']",
]

# ----- search scraper constants -----
SEARCH_NEXT_PAGE_SELECTORS = [
    "a.s-pagination-next",
    "span.s-pagination-strip a.s-pagination-next",
    "ul.a-pagination li.a-last a",
    "li.a-last a",
    "a[aria-label='Go to next page']",
]